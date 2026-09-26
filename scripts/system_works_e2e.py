#!/usr/bin/env python3
"""Resume one approved Hydra SYSTEM_WORKS mission through live RuntimeV2.

This is an operator entry point, not another runtime.  It opens Hydra's durable
state, records the already-authorized exact Zgredek packet SHA, retrieves the
existing OSA API key from Google Secret Manager using an already-available
Cloud SDK, Application Default, or metadata-server credential, and drives only
the existing Hydra approval gates.

It deliberately never invokes ``gcloud auth login``.  Missing or expired
cached credentials are reported as BLOCKED without terminating the caller's
interactive shell and without losing the persisted context approval.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from hydra_control.models import MissionState  # noqa: E402
from hydra_control.service import MissionService  # noqa: E402


DEFAULT_PROJECT = "fluid-fiber-477010-a8"
DEFAULT_SECRET = "osa-execution-force-api-key"
DEFAULT_RUNTIME_URL = "https://osa-execution-force-api-bmnzqzarxa-ew.a.run.app"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MISSION_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
PROJECT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{4,62}$")
SECRET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,255}$")
METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/"
    "service-accounts/default/token"
)
TERMINAL_STATES = {
    MissionState.COMPLETED,
    MissionState.BLOCKED,
    MissionState.FAILED,
    MissionState.CANCELLED,
}


class EntryPointBlocked(RuntimeError):
    """A fail-closed operational blocker with no claim of execution."""


def _gcloud(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("gcloud")
    if executable is None:
        raise EntryPointBlocked("gcloud is unavailable; no login was attempted")
    try:
        return subprocess.run(
            [executable, *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as error:
        raise EntryPointBlocked("gcloud credential lookup timed out") from error


def cached_gcloud_accounts() -> list[str]:
    """Return cached accounts without requiring one to be active."""

    result = _gcloud(["auth", "list", "--format=value(account)"])
    if result.returncode != 0:
        raise EntryPointBlocked("cached gcloud accounts cannot be listed")
    accounts: list[str] = []
    for raw in result.stdout.splitlines():
        account = raw.strip()
        if account and account not in accounts:
            accounts.append(account)
    if not accounts:
        raise EntryPointBlocked(
            "no cached gcloud account can access Secret Manager; no login was attempted"
        )
    return accounts


def secret_from_cached_account(*, project: str, secret: str) -> tuple[str, str]:
    """Read one secret with an existing account, never an interactive login."""

    for account in cached_gcloud_accounts():
        result = _gcloud(
            [
                "secrets",
                "versions",
                "access",
                "latest",
                f"--secret={secret}",
                f"--project={project}",
                f"--account={account}",
                "--quiet",
            ]
        )
        value = result.stdout.strip()
        if result.returncode == 0 and value:
            return value, account
    raise EntryPointBlocked(
        f"cached gcloud accounts cannot access secret {secret}; no login was attempted"
    )


def application_default_token() -> str:
    """Return an existing ADC token; never start an authorization flow."""

    try:
        result = _gcloud(["auth", "application-default", "print-access-token"])
    except EntryPointBlocked:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def metadata_access_token() -> str:
    """Return the ambient VM service-account token when one is attached."""

    request = Request(METADATA_TOKEN_URL, headers={"Metadata-Flavor": "Google"})
    try:
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read(65537).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, UnicodeError):
        return ""
    token = payload.get("access_token") if isinstance(payload, dict) else None
    return token.strip() if isinstance(token, str) else ""


def secret_from_access_token(*, token: str, project: str, secret: str) -> str:
    """Read Secret Manager through REST without exposing the bearer token."""

    if not token:
        raise EntryPointBlocked("empty ambient access token")
    if not PROJECT_PATTERN.fullmatch(project):
        raise EntryPointBlocked("invalid Google Cloud project identifier")
    if not SECRET_PATTERN.fullmatch(secret):
        raise EntryPointBlocked("invalid Secret Manager secret identifier")
    endpoint = (
        "https://secretmanager.googleapis.com/v1/projects/"
        f"{quote(project, safe='')}/secrets/{quote(secret, safe='')}/"
        "versions/latest:access"
    )
    request = Request(
        endpoint,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read(1048577)
        if len(body) > 1048576:
            raise EntryPointBlocked("Secret Manager response exceeded size limit")
        document = json.loads(body.decode("utf-8"))
        encoded = document["payload"]["data"]
        value = base64.b64decode(encoded, validate=True).decode("utf-8").strip()
    except EntryPointBlocked:
        raise
    except (
        HTTPError,
        URLError,
        TimeoutError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        UnicodeError,
        binascii.Error,
    ) as error:
        raise EntryPointBlocked("ambient credential cannot access Secret Manager") from error
    if not value:
        raise EntryPointBlocked("Secret Manager returned an empty secret")
    return value


def secret_from_ambient_credentials(*, project: str, secret: str) -> tuple[str, str]:
    """Try every non-interactive credential already present in Cloud Shell."""

    try:
        return secret_from_cached_account(project=project, secret=secret)
    except EntryPointBlocked:
        pass

    adc_token = application_default_token()
    if adc_token:
        try:
            return (
                secret_from_access_token(
                    token=adc_token,
                    project=project,
                    secret=secret,
                ),
                "application-default",
            )
        except EntryPointBlocked:
            pass

    metadata_token = metadata_access_token()
    if metadata_token:
        try:
            return (
                secret_from_access_token(
                    token=metadata_token,
                    project=project,
                    secret=secret,
                ),
                "metadata-default-service-account",
            )
        except EntryPointBlocked:
            pass

    raise EntryPointBlocked(
        "no cached, Application Default, or metadata credential can access "
        "Secret Manager; no login was attempted"
    )


def approve_exact_context(
    *, state_root: Path, mission_id: str, packet_sha256: str
) -> dict[str, Any]:
    """Persist exact-SHA approval before any runtime credential is requested."""

    os.environ["HYDRA_EXECUTION_BACKEND"] = "osa-execution-force"
    service = MissionService.configured(state_root)
    try:
        return service.approve_context_packet(
            mission_id,
            actor="OSA",
            packet_sha256=packet_sha256,
        )
    finally:
        service.store.close()


def drive_existing_mission(
    *, state_root: Path, mission_id: str, approved_gates: frozenset[str]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Run synchronously until completion or the first truthful pause."""

    service = MissionService.configured(state_root)
    try:
        for _ in range(4):
            mission = service.mission(mission_id)
            state = MissionState(mission["state"])
            if state in TERMINAL_STATES:
                break
            if state == MissionState.DRAFT:
                service.start(mission_id, actor="OSA", asynchronous=False)
                continue
            if state == MissionState.AWAITING_ARCHITECTURE_APPROVAL:
                if "architecture" not in approved_gates:
                    break
                service.approve(
                    mission_id,
                    gate="architecture",
                    actor="OSA",
                    asynchronous=False,
                )
                continue
            if state == MissionState.AWAITING_HUMAN_APPROVAL:
                if "human" not in approved_gates:
                    break
                service.approve(
                    mission_id,
                    gate="human",
                    actor="OSA",
                    asynchronous=False,
                )
                continue
            break

        mission = service.mission(mission_id)
        evidence = (
            service.evidence(mission_id)
            if mission["state"] == MissionState.COMPLETED
            else None
        )
        return mission, evidence
    finally:
        service.store.close()


def report(
    *,
    mission: dict[str, Any],
    packet_sha256: str,
    account: str,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    bundle = (evidence or {}).get("bundle", {})
    return {
        "systemWorks": "PASS" if mission["state"] == MissionState.COMPLETED else "BLOCKED",
        "hydraMissionId": mission["mission_id"],
        "missionState": mission["state"],
        "currentNode": mission.get("current_node_id", ""),
        "failureReason": mission.get("failure_reason", ""),
        "approvedPacketSha256": packet_sha256,
        "gcpAccount": account,
        "runtimeV2MissionId": bundle.get("runtimeV2MissionId", "UNKNOWN"),
        "worker": bundle.get("executionWorker", "UNKNOWN"),
        "baseSha": mission.get("base_commit", "UNKNOWN"),
        "resultSha": mission.get("result_commit", "UNKNOWN"),
        "evidenceValid": bool(evidence and evidence.get("valid")),
        "rollback": bundle.get("rollbackPlan", "UNKNOWN"),
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--mission-id", required=True)
    value.add_argument("--packet-sha256", required=True)
    value.add_argument("--state-root", type=Path, required=True)
    value.add_argument("--project", default=DEFAULT_PROJECT)
    value.add_argument("--secret", default=DEFAULT_SECRET)
    value.add_argument("--runtime-url", default=DEFAULT_RUNTIME_URL)
    value.add_argument(
        "--approve-gates",
        default="",
        help="Comma-separated Hydra gates explicitly approved by this invocation.",
    )
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    state_root = args.state_root.expanduser().resolve()
    if not MISSION_ID_PATTERN.fullmatch(args.mission_id):
        parser().error("--mission-id must be a canonical UUID")
    if not SHA256_PATTERN.fullmatch(args.packet_sha256):
        parser().error("--packet-sha256 must be 64 lowercase hexadecimal characters")
    if not state_root.is_dir():
        parser().error("--state-root must be the existing Hydra state directory")

    approved_gates = frozenset(
        item.strip() for item in args.approve_gates.split(",") if item.strip()
    )
    unknown_gates = approved_gates - {"architecture", "human"}
    if unknown_gates:
        parser().error(f"unknown gate approval: {', '.join(sorted(unknown_gates))}")

    os.environ["HYDRA_OSA_EXECUTION_FORCE_URL"] = args.runtime_url
    os.environ.pop("OSA_ACTIONS_API_KEY", None)
    try:
        approval = approve_exact_context(
            state_root=state_root,
            mission_id=args.mission_id,
            packet_sha256=args.packet_sha256,
        )
        key, account = secret_from_ambient_credentials(
            project=args.project,
            secret=args.secret,
        )
        os.environ["OSA_ACTIONS_API_KEY"] = key
        mission, evidence = drive_existing_mission(
            state_root=state_root,
            mission_id=args.mission_id,
            approved_gates=approved_gates,
        )
    except EntryPointBlocked as error:
        print(
            json.dumps(
                {
                    "systemWorks": "BLOCKED",
                    "hydraMissionId": args.mission_id,
                    "approvedPacketSha256": args.packet_sha256,
                    "contextApprovalPersisted": bool(
                        "approval" in locals() and approval.get("approved")
                    ),
                    "workerDispatched": False,
                    "reason": str(error),
                },
                indent=2,
            )
        )
        return 20
    except Exception as error:  # noqa: BLE001 - bounded operator report
        print(
            json.dumps(
                {
                    "systemWorks": "FAIL",
                    "hydraMissionId": args.mission_id,
                    "errorType": type(error).__name__,
                    "reason": str(error),
                },
                indent=2,
            )
        )
        return 1
    finally:
        os.environ.pop("OSA_ACTIONS_API_KEY", None)

    print(
        json.dumps(
            report(
                mission=mission,
                packet_sha256=args.packet_sha256,
                account=account,
                evidence=evidence,
            ),
            indent=2,
            default=str,
        )
    )
    return 0 if mission["state"] == MissionState.COMPLETED else 2


if __name__ == "__main__":
    raise SystemExit(main())
