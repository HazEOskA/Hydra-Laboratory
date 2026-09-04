"""Thin ExecutionBackend adapter for the canonical OSA RuntimeV2 boundary.

Hydra keeps mission state and scheduling. This module only translates the
existing Hydra backend contract to OSA Execution Force's API v2 and refuses to
turn model claims, incomplete host actions, or unverifiable evidence into PASS.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import threading
import uuid
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from hermes.redact import redact

from .models import (
    BackendError,
    CommandResult,
    CreateSessionInput,
    ExecuteTaskInput,
    ExecutionArtifact,
    ExecutionEvent,
    ExecutionResult,
    ExecutionSession,
    ExecutionStatus,
)
from .store import utc_now


BACKEND_ID = "osa-execution-force"
API_URL_ENV = "HYDRA_OSA_EXECUTION_FORCE_URL"
API_KEY_ENV = "OSA_ACTIONS_API_KEY"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
GITHUB_SLUG = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BLOCKED_STATES = frozenset(
    {
        "BLOCKED",
        "HOST_ACTION_REQUIRED",
        "WAITING_FOR_APPROVAL",
        "WAITING_FOR_USER",
        "PAUSED",
        "QUEUED",
        "RUNNING",
    }
)
FAILED_STATES = frozenset({"FAILED", "CANCELLED", "REJECTED"})
PRE_EXECUTION_NODES = frozenset(
    {
        "mission-intake",
        "repository-fact-load",
        "feasibility-analysis",
        "implementation-plan",
    }
)
POST_EXECUTION_NODES = frozenset(
    {
        "quality-checks",
        "targeted-tests",
        "runtime-verification",
        "independent-review",
        "apr-evidence",
        "draft-pull-request",
    }
)


class JsonTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]: ...


class RuntimeV2HttpTransport:
    """Dependency-free authenticated transport for the official API v2."""

    def __init__(self, base_url: str, api_key: str, timeout_seconds: int = 900) -> None:
        parsed = urlparse(base_url)
        loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise BackendError("OSA Execution Force URL must use HTTPS (or loopback HTTP)")
        if (
            parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or not parsed.netloc
        ):
            raise BackendError("invalid OSA Execution Force base URL")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @property
    def authenticated(self) -> bool:
        """Whether this transport can cross the protected RuntimeV2 boundary.

        Construction is intentionally allowed without the key so Hydra can
        reopen durable control-plane state and record an exact-SHA Zgredek
        approval while execution access is unavailable.  Every execution
        method still fails closed before worker dispatch.
        """

        return bool(self.api_key)

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        if path != "/health" and not self.authenticated:
            raise BackendError(f"{API_KEY_ENV} is required; execution is UNAVAILABLE")
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if correlation_id:
            if not re.fullmatch(r"^[A-Za-z0-9._:-]{8,128}$", correlation_id):
                raise BackendError("invalid RuntimeV2 correlation ID")
            headers["X-Correlation-ID"] = correlation_id
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            detail = error.read(2048).decode("utf-8", errors="replace")
            raise BackendError(
                f"OSA Execution Force HTTP {error.code}: {redact(detail)[:500]}"
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise BackendError(
                f"OSA Execution Force UNAVAILABLE: {redact(str(error))[:500]}"
            ) from error
        if len(raw) > MAX_RESPONSE_BYTES:
            raise BackendError("OSA Execution Force response exceeds safety limit")
        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BackendError("OSA Execution Force returned invalid JSON") from error
        if not isinstance(decoded, dict):
            raise BackendError("OSA Execution Force response must be a JSON object")
        return decoded


class OsaExecutionForceBackend:
    """ExecutionBackend that delegates all code execution to RuntimeV2."""

    backend_id = BACKEND_ID

    def __init__(self, transport: JsonTransport, artifact_root: str | Path) -> None:
        self.transport = transport
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ExecutionSession] = {}
        self._runtime_ids: dict[str, str] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[ExecutionEvent]] = {}
        self._artifacts: dict[str, list[ExecutionArtifact]] = {}
        self._lock = threading.RLock()

    @classmethod
    def from_environment(cls, artifact_root: str | Path) -> "OsaExecutionForceBackend":
        url = os.environ.get(API_URL_ENV, "")
        key = os.environ.get(API_KEY_ENV, "")
        if not url:
            raise BackendError(f"{API_URL_ENV} is required; execution is UNAVAILABLE")
        return cls(RuntimeV2HttpTransport(url, key), artifact_root)

    def create_session(self, input: CreateSessionInput) -> ExecutionSession:
        if (
            isinstance(self.transport, RuntimeV2HttpTransport)
            and not self.transport.authenticated
        ):
            raise BackendError(f"{API_KEY_ENV} is required; execution is UNAVAILABLE")
        if not SAFE_SEGMENT.fullmatch(input.mission_id):
            raise BackendError("invalid Hydra mission correlation ID")
        with self._lock:
            existing = self._sessions.get(input.mission_id)
            if existing is not None:
                return existing
        health = self.transport.request("GET", "/health")
        if str(health.get("status", "")).lower() not in {"ok", "healthy", "pass"}:
            raise BackendError("OSA Execution Force health is not PASS")
        workspace = self.artifact_root / input.mission_id / "remote-session"
        workspace.mkdir(parents=True, exist_ok=True)
        session = ExecutionSession(
            session_id=input.mission_id,
            mission_id=input.mission_id,
            backend=self.backend_id,
            workspace=workspace,
            status="READY",
        )
        with self._lock:
            self._sessions[input.mission_id] = session
            self._events[input.mission_id] = []
            self._artifacts[input.mission_id] = []
            state_path = self._state_path(input.mission_id)
            if state_path.is_file():
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    raise BackendError("invalid persisted RuntimeV2 correlation state") from error
                runtime_id = state.get("runtimeMissionId", "")
                if isinstance(runtime_id, str) and runtime_id:
                    self._runtime_ids[input.mission_id] = runtime_id
        self._emit(session, "SESSION_READY", "", "RuntimeV2 health verified")
        return session

    def availability(self) -> tuple[str, str]:
        """Probe the live boundary; configuration alone is never ONLINE."""
        if (
            isinstance(self.transport, RuntimeV2HttpTransport)
            and not self.transport.authenticated
        ):
            return "UNAVAILABLE", f"{API_KEY_ENV} is required; execution is UNAVAILABLE"
        try:
            health = self.transport.request("GET", "/health")
        except BackendError as error:
            return "UNAVAILABLE", redact(str(error))[:500]
        status = str(health.get("status", "")).lower()
        if status not in {"ok", "healthy", "pass"}:
            return "UNAVAILABLE", f"RuntimeV2 health={status or 'UNKNOWN'}"
        return "AVAILABLE", "RuntimeV2 /health returned PASS"

    def execute_task(self, input: ExecuteTaskInput) -> ExecutionResult:
        session = self._session(input.session_id)
        try:
            if input.node_id in PRE_EXECUTION_NODES:
                return self._pre_execution(session, input)
            if input.node_id == "agent-execution":
                return self._execute_runtime(session, input)
            if input.node_id in POST_EXECUTION_NODES:
                return self._post_execution(session, input)
            return ExecutionResult(
                False,
                f"OSA Execution Force adapter has no handler for {input.node_id}",
                error_code="UNSUPPORTED_NODE",
            )
        except BackendError as error:
            session.status = "FAILED"
            self._emit(session, "TASK_REFUSED", input.node_id, str(error))
            return ExecutionResult(
                False,
                "RuntimeV2 result refused",
                error_code="RUNTIME_V2_VERIFICATION_FAILED",
                metadata={"detail": redact(str(error))[:500]},
            )

    def get_status(self, session_id: str) -> ExecutionStatus:
        session = self._session(session_id)
        runtime_id = self._runtime_ids.get(session_id)
        if runtime_id:
            snapshot = self._snapshot(
                self.transport.request(
                    "GET",
                    f"/api/v2/missions/{runtime_id}",
                    correlation_id=session_id,
                )
            )
            self._snapshots[session_id] = snapshot
            session.status = str(snapshot.get("state", "UNKNOWN"))
            result_commit = self._result_commit(snapshot)
            if result_commit:
                session.result_commit = result_commit
        return ExecutionStatus(
            session_id=session_id,
            status=session.status,
            current_node_id="agent-execution" if runtime_id else "",
            commit_sha=session.result_commit,
            detail=(
                f"RuntimeV2 mission {runtime_id}"
                if runtime_id
                else "RuntimeV2 mission not created"
            ),
        )

    async def stream_events(self, session_id: str) -> AsyncIterable[ExecutionEvent]:
        self.get_status(session_id)
        snapshot = self._snapshots.get(session_id, {})
        for raw in snapshot.get("events", []):
            if not isinstance(raw, dict):
                continue
            yield ExecutionEvent(
                event_id=str(raw.get("event_id", raw.get("id", uuid.uuid4()))),
                session_id=session_id,
                node_id="agent-execution",
                event_type=str(raw.get("event_type", "RUNTIME_EVENT")),
                timestamp=str(raw.get("created_at", utc_now())),
                message=redact(str(raw.get("state", "")))[:500],
            )
            await asyncio.sleep(0)

    def cancel(self, session_id: str) -> None:
        self._session(session_id)
        raise BackendError(
            "RuntimeV2 cancellation is UNSUPPORTED by the verified API boundary"
        )

    def collect_artifacts(self, session_id: str) -> list[ExecutionArtifact]:
        self._session(session_id)
        return list(self._artifacts.get(session_id, []))

    def command_artifacts(
        self,
        session_id: str,
        node_id: str,
        command: CommandResult,
        index: int,
    ) -> tuple[ExecutionArtifact, ExecutionArtifact]:
        session = self._session(session_id)
        return (
            self._artifact(
                session,
                node_id,
                "command-stdout",
                f"command-{index:02d}-stdout.txt",
                command.stdout,
            ),
            self._artifact(
                session,
                node_id,
                "command-stderr",
                f"command-{index:02d}-stderr.txt",
                command.stderr,
            ),
        )

    def evidence_artifact(
        self, session_id: str, node_id: str, bundle: dict[str, Any]
    ) -> ExecutionArtifact:
        return self._artifact(
            self._session(session_id),
            node_id,
            "apr-evidence",
            "apr-evidence.json",
            json.dumps(bundle, indent=2, sort_keys=True) + "\n",
        )

    def _pre_execution(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        manifest = input.manifest
        self._validate_manifest(
            manifest,
            input.mission_id,
            require_context=input.node_id != "mission-intake",
        )
        artifact = self._artifact(
            session,
            input.node_id,
            "runtime-boundary",
            f"{input.node_id}.json",
            json.dumps(
                {
                    "node": input.node_id,
                    "executionAuthority": "OSA Execution Force RuntimeV2",
                    "hydraMissionId": input.mission_id,
                    "repository": manifest.get("repository"),
                    "branch": manifest.get("branch"),
                    "baseCommit": manifest.get("base_commit"),
                    "executionPerformed": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        return ExecutionResult(
            True,
            f"{input.node_id} contract validated; execution remains delegated",
            artifacts=[artifact],
        )

    def _execute_runtime(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        self._validate_manifest(input.manifest, input.mission_id)
        runtime_id = self._runtime_ids.get(input.session_id)
        if runtime_id:
            raw = self.transport.request(
                "GET",
                f"/api/v2/missions/{runtime_id}",
                correlation_id=input.mission_id,
            )
        else:
            raw = self.transport.request(
                "POST",
                "/api/v2/missions/run",
                self._run_payload(input),
                correlation_id=input.mission_id,
            )
        snapshot = self._snapshot(raw)
        runtime_id = self._mission_id(snapshot)
        if not runtime_id:
            raise BackendError("RuntimeV2 response has no mission_id")
        if runtime_id != self._runtime_ids.get(input.session_id, runtime_id):
            raise BackendError("RuntimeV2 mission correlation changed")
        self._runtime_ids[input.session_id] = runtime_id
        self._persist_correlation(input.session_id, runtime_id)
        if str(snapshot.get("state", "")).upper() == "HOST_ACTION_REQUIRED":
            snapshot = self._execute_authorized_host_action(
                snapshot,
                runtime_id=runtime_id,
                correlation_id=input.mission_id,
            )
        self._snapshots[input.session_id] = snapshot
        artifact = self._artifact(
            session,
            input.node_id,
            "runtime-v2-snapshot",
            "runtime-v2-snapshot.json",
            json.dumps(snapshot, indent=2, sort_keys=True, default=str) + "\n",
        )
        state = str(snapshot.get("state", "UNKNOWN")).upper()
        session.status = state
        if state in BLOCKED_STATES:
            host_action = self._host_action_request(snapshot)
            return ExecutionResult(
                False,
                f"RuntimeV2 mission {runtime_id} is {state}",
                artifacts=[artifact],
                error_code=state,
                metadata={
                    "hydraDisposition": "BLOCKED",
                    "detail": self._blocker_detail(snapshot, state),
                    "runtimeMissionId": runtime_id,
                    "runtimeExecutionId": self._execution_id(snapshot),
                    "hostActionRequest": host_action,
                },
            )
        if state in FAILED_STATES:
            return ExecutionResult(
                False,
                f"RuntimeV2 mission {runtime_id} failed as {state}",
                artifacts=[artifact],
                error_code=state,
                metadata={"detail": self._blocker_detail(snapshot, state)},
            )
        if state != "COMPLETED":
            return ExecutionResult(
                False,
                f"RuntimeV2 mission state is not terminal: {state}",
                artifacts=[artifact],
                error_code="RUNTIME_STATE_UNKNOWN",
                metadata={
                    "hydraDisposition": "BLOCKED",
                    "detail": f"RuntimeV2 returned unrecognized state {state}",
                    "runtimeMissionId": runtime_id,
                },
            )
        proof = self._verify_completed(snapshot, input)
        session.base_commit = proof["baseCommit"]
        session.result_commit = proof["resultCommit"]
        session.status = "COMPLETED"
        self._emit(session, "RUNTIME_VERIFIED", input.node_id, "mechanical evidence verified")
        return ExecutionResult(
            True,
            f"RuntimeV2 mission {runtime_id} completed with verified evidence",
            commands=self._commands(snapshot),
            artifacts=[artifact],
            metadata=proof,
        )

    def _post_execution(
        self, session: ExecutionSession, input: ExecuteTaskInput
    ) -> ExecutionResult:
        runtime_id = self._runtime_ids.get(input.session_id)
        if not runtime_id:
            raise BackendError("no correlated RuntimeV2 mission")
        snapshot = self._snapshot(
            self.transport.request(
                "GET",
                f"/api/v2/missions/{runtime_id}",
                correlation_id=input.mission_id,
            )
        )
        self._snapshots[input.session_id] = snapshot
        proof = self._verify_completed(snapshot, input)
        commands = self._commands(snapshot) if input.node_id == "targeted-tests" else []
        return ExecutionResult(
            True,
            f"{input.node_id} verified from RuntimeV2 mechanical evidence",
            commands=commands,
            metadata=proof if input.node_id == "apr-evidence" else {
                "baseCommit": proof["baseCommit"],
                "resultCommit": proof["resultCommit"],
                "runtimeMissionId": proof["runtimeMissionId"],
                "runtimeExecutionId": proof["runtimeExecutionId"],
            },
        )

    def _run_payload(self, input: ExecuteTaskInput) -> dict[str, Any]:
        manifest = input.manifest
        context = manifest["hydra_context"]
        return {
            "task": manifest["request"],
            "goal": manifest["title"],
            "context": {
                "constraints": [
                    "Execute only through OSA Execution Force governance.",
                    "Confine changes to the Hydra-declared allowed scope.",
                    f"Hydra risk classification: {manifest['risk_level']}",
                ],
                "requirements": list(manifest.get("acceptance_criteria", [])),
                "decisions": [
                    f"Zgredek context {context['packetSha256']} approved by {context['approvedBy']}"
                ],
                "known_facts": {
                    "hydra.mission_id": input.mission_id,
                    "hydra.context_packet_sha256": context["packetSha256"],
                    "hydra.context_approved_by": context["approvedBy"],
                    "hydra.risk_level": manifest["risk_level"],
                    "backend.platform-engineering.test_command": list(
                        manifest["test_command"]
                    ),
                    "backend.platform-engineering.allowed_scope": list(
                        manifest["allowed_scope"]
                    ),
                    "backend.platform-engineering.test_timeout_seconds": manifest[
                        "timeout_seconds"
                    ],
                },
                "repository": self._runtime_repository(manifest["repository"]),
                "branch": manifest["branch"],
                "commit_sha": manifest["base_commit"],
                "budget": (
                    {"maximum_cost": manifest["budget_limit"]}
                    if manifest.get("budget_limit", 0.0) > 0
                    else {}
                ),
            },
            "environment": manifest["environment"],
            "requested_operation": None,
            "approvals": [],
        }

    def _execute_authorized_host_action(
        self,
        snapshot: dict[str, Any],
        *,
        runtime_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        request = self._host_action_request(snapshot)
        if not isinstance(request, dict) or not request.get("action_id"):
            raise BackendError("RuntimeV2 HOST_ACTION_REQUIRED has no bound action_id")
        version = snapshot.get("mission_version")
        execution_id = self._execution_id(snapshot)
        if isinstance(version, bool) or not isinstance(version, int) or not execution_id:
            raise BackendError("RuntimeV2 host action snapshot identity is incomplete")
        resumed = self._snapshot(
            self.transport.request(
                "POST",
                f"/api/v2/missions/{runtime_id}/execute-host-action",
                {
                    "expected_action_id": str(request["action_id"]),
                    "expected_mission_version": version,
                    "expected_execution_id": execution_id,
                },
                correlation_id=correlation_id,
            )
        )
        if self._mission_id(resumed) != runtime_id:
            raise BackendError("RuntimeV2 mission correlation changed after host action")
        return resumed

    @staticmethod
    def _runtime_repository(repository: Any) -> str:
        value = str(repository).strip()
        if not value.startswith("github://"):
            return value
        slug = value.removeprefix("github://").removesuffix(".git")
        if not GITHUB_SLUG.fullmatch(slug):
            raise BackendError("invalid github:// repository identifier")
        return slug

    def _validate_manifest(
        self,
        manifest: dict[str, Any],
        mission_id: str,
        *,
        require_context: bool = True,
    ) -> None:
        if manifest.get("mission_id") != mission_id:
            raise BackendError("Hydra mission correlation ID mismatch")
        if manifest.get("execution_backend") != self.backend_id:
            raise BackendError("manifest is not bound to OSA Execution Force")
        if not COMMIT_SHA.fullmatch(str(manifest.get("base_commit", ""))):
            raise BackendError("manifest has no exact base commit")
        if not manifest.get("allowed_scope") or not manifest.get("test_command"):
            raise BackendError("mechanical scope and test contract are required")
        if not require_context:
            return
        context = manifest.get("hydra_context")
        if not isinstance(context, dict):
            raise BackendError("approved Zgredek context is missing")
        packet_sha = str(context.get("packetSha256", ""))
        if (
            context.get("status") != "APPROVED"
            or not re.fullmatch(r"^[0-9a-f]{64}$", packet_sha)
            or context.get("approvedPacketSha256") != packet_sha
            or not context.get("approvedBy")
        ):
            raise BackendError("Zgredek exact-SHA approval is invalid")

    def _verify_completed(
        self, snapshot: dict[str, Any], input: ExecuteTaskInput
    ) -> dict[str, Any]:
        if str(snapshot.get("state", "")).upper() != "COMPLETED":
            raise BackendError("CLAIMED is not COMPLETED")
        runtime_id = self._mission_id(snapshot)
        execution_id = self._execution_id(snapshot)
        if not runtime_id or not execution_id:
            raise BackendError("RuntimeV2 result identity is incomplete")
        resolved_skills = self._resolved_skills(snapshot)
        chain_detail = self._verify_event_chain(snapshot)
        diff_evidence = self._mechanical_evidence(snapshot, "host_action.git_diff_scope")
        test_evidence = self._mechanical_evidence(snapshot, "host_action.tests_pass")
        diff_details = self._details(diff_evidence)
        test_details = self._details(test_evidence)
        if not self._diff_passed(diff_details):
            raise BackendError("git diff scope lacks mechanically verified PASS")
        if not self._test_passed(test_details):
            raise BackendError("required tests lack mechanically verified PASS")
        base_commit = self._base_commit(snapshot) or input.manifest["base_commit"]
        result_commit = self._result_commit(snapshot)
        if base_commit != input.manifest["base_commit"]:
            raise BackendError("RuntimeV2 base commit does not match Hydra manifest")
        if not COMMIT_SHA.fullmatch(result_commit) or result_commit == base_commit:
            raise BackendError("change mission has no distinct verified result commit")
        changed_files = self._changed_files(diff_details)
        if not changed_files:
            raise BackendError("mechanical evidence records no changed files")
        allowed = set(input.manifest["allowed_scope"])
        if not all(self._within_scope(path, allowed) for path in changed_files):
            raise BackendError("mechanical evidence contains an out-of-scope file")
        commands = self._commands(snapshot)
        if not commands:
            raise BackendError("RuntimeV2 has no executed command evidence")
        worker = self._worker(snapshot)
        if not worker:
            raise BackendError("RuntimeV2 worker identity is missing")
        if self._has_incomplete_required_check(snapshot):
            raise BackendError("RuntimeV2 contains a failed or UNKNOWN required check")
        return {
            "baseCommit": base_commit,
            "resultCommit": result_commit,
            "currentCommit": result_commit,
            "changedFiles": changed_files,
            "diffSummary": f"{len(changed_files)} mechanically verified changed file(s)",
            "diff": json.dumps(diff_details, sort_keys=True, default=str),
            "runtimeMissionId": runtime_id,
            "runtimeExecutionId": execution_id,
            "worker": worker,
            "resolvedSkills": resolved_skills,
            "eventChainVerified": True,
            "eventChainDetail": chain_detail,
            "mechanicalEvidenceIds": [
                self._evidence_id(diff_evidence),
                self._evidence_id(test_evidence),
            ],
        }

    def _verify_event_chain(self, snapshot: dict[str, Any]) -> str:
        events = snapshot.get("events")
        if not isinstance(events, list) or not events:
            raise BackendError("RuntimeV2 event chain is absent")
        previous = "0" * 64
        mission_id = self._mission_id(snapshot)
        execution_id = self._execution_id(snapshot)
        for expected, event in enumerate(events, start=1):
            if not isinstance(event, dict):
                raise BackendError("RuntimeV2 event chain contains an invalid event")
            sequence = event.get("sequence")
            if sequence != expected:
                raise BackendError("RuntimeV2 event sequence is not contiguous")
            if event.get("mission_id") != mission_id or event.get("execution_id") != execution_id:
                raise BackendError("RuntimeV2 event identity mismatch")
            if event.get("previous_hash") != previous:
                raise BackendError("RuntimeV2 event previous_hash mismatch")
            body = {
                "mission_id": event.get("mission_id"),
                "execution_id": event.get("execution_id"),
                "sequence": sequence,
                "event_type": event.get("event_type"),
                "state": event.get("state"),
                "payload": event.get("payload"),
                "previous_hash": event.get("previous_hash"),
                "created_at": self._hash_timestamp(event.get("created_at")),
            }
            calculated = hashlib.sha256(
                json.dumps(
                    body,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            event_hash = event.get("event_hash", event.get("hash"))
            if event_hash != calculated:
                raise BackendError("RuntimeV2 event hash mismatch")
            previous = calculated
        if str(events[-1].get("state", "")).upper() != str(
            snapshot.get("state", "")
        ).upper():
            raise BackendError("RuntimeV2 event tail does not match mission state")
        return f"PASS: {len(events)} RuntimeV2 event(s), tail={previous}"

    def _mechanical_evidence(
        self, snapshot: dict[str, Any], suffix: str
    ) -> dict[str, Any]:
        evidence = snapshot.get("evidence", snapshot.get("evidence_records", []))
        if not isinstance(evidence, list):
            raise BackendError("RuntimeV2 evidence collection is invalid")
        ids = {
            self._evidence_id(item)
            for item in evidence
            if isinstance(item, dict) and self._evidence_id(item)
        }
        listed_ids = [
            self._evidence_id(item)
            for item in evidence
            if isinstance(item, dict) and self._evidence_id(item)
        ]
        if len(listed_ids) != len(set(listed_ids)):
            raise BackendError("RuntimeV2 evidence IDs are not unique")
        for item in evidence:
            if not isinstance(item, dict):
                continue
            if item.get("mission_id") != self._mission_id(snapshot) or item.get(
                "execution_id"
            ) != self._execution_id(snapshot):
                raise BackendError("RuntimeV2 evidence identity mismatch")
            source = item.get("source_evidence_id")
            if source and source not in ids:
                raise BackendError("RuntimeV2 evidence provenance is broken")
            encoded = json.dumps(item, sort_keys=True, default=str)
            authority = str(item.get("authority", item.get("authority_level", ""))).upper()
            if suffix in encoded and authority == "MECHANICALLY_VERIFIED":
                artifact_sha = str(item.get("artifact_sha256", ""))
                if not item.get("artifact") or not re.fullmatch(
                    r"^[0-9a-f]{64}$", artifact_sha
                ):
                    raise BackendError(
                        f"mechanical evidence artifact binding is invalid: {suffix}"
                    )
                return item
        raise BackendError(f"required mechanical evidence is missing: {suffix}")

    @staticmethod
    def _details(evidence: dict[str, Any]) -> dict[str, Any]:
        details = evidence.get("verification_details", evidence.get("details", {}))
        return details if isinstance(details, dict) else {}

    @classmethod
    def _diff_passed(cls, details: dict[str, Any]) -> bool:
        flat = list(cls._walk_dicts(details))
        return any(
            item.get("passed") is True
            and item.get("claim_matches_reality") is True
            and item.get("scope_confined") is True
            for item in flat
        )

    @classmethod
    def _test_passed(cls, details: dict[str, Any]) -> bool:
        return any(
            item.get("passed") is True or str(item.get("status", "")).upper() == "PASS"
            for item in cls._walk_dicts(details)
        )

    @classmethod
    def _changed_files(cls, details: dict[str, Any]) -> list[str]:
        for item in cls._walk_dicts(details):
            files = item.get("actual_changed_files")
            if isinstance(files, list) and all(isinstance(path, str) for path in files):
                return sorted(set(files))
        return []

    @staticmethod
    def _within_scope(path: str, allowed: set[str]) -> bool:
        return any(path == scope or path.startswith(scope.rstrip("/") + "/") for scope in allowed)

    @classmethod
    def _commands(cls, snapshot: dict[str, Any]) -> list[CommandResult]:
        commands: list[CommandResult] = []
        started = cls._event_time(snapshot, first=True)
        finished = cls._event_time(snapshot, first=False)
        evidence = snapshot.get("evidence", [])
        for item in evidence if isinstance(evidence, list) else []:
            if not isinstance(item, dict):
                continue
            authority = str(item.get("authority", "")).upper()
            command = item.get("command")
            exit_code = item.get("exit_code")
            if (
                authority != "MECHANICALLY_VERIFIED"
                or not isinstance(command, str)
                or not command
                or isinstance(exit_code, bool)
                or not isinstance(exit_code, int)
            ):
                continue
            details = cls._details(item)
            stdout = cls._detail_text(details, ("stdout", "stdout_ref"))
            stderr = cls._detail_text(details, ("stderr", "stderr_ref"))
            commands.append(
                CommandResult(
                    command=(command,),
                    display=command,
                    started_at=started,
                    finished_at=finished,
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                )
            )
        return commands

    @classmethod
    def _detail_text(cls, details: dict[str, Any], keys: tuple[str, ...]) -> str:
        for item in cls._walk_dicts(details):
            for key in keys:
                value = item.get(key)
                if isinstance(value, str) and value:
                    return value
        return ""

    @staticmethod
    def _event_time(snapshot: dict[str, Any], *, first: bool) -> str:
        events = snapshot.get("events", [])
        if isinstance(events, list) and events:
            item = events[0] if first else events[-1]
            if isinstance(item, dict) and item.get("created_at"):
                return str(item["created_at"])
        return utc_now()

    @staticmethod
    def _hash_timestamp(value: Any) -> Any:
        if isinstance(value, str) and value.endswith("Z"):
            return value[:-1] + "+00:00"
        return value

    @classmethod
    def _base_commit(cls, snapshot: dict[str, Any]) -> str:
        for item in cls._ledger(snapshot):
            value = item.get("source_commit_before")
            if isinstance(value, str) and COMMIT_SHA.fullmatch(value):
                return value
        return ""

    @classmethod
    def _result_commit(cls, snapshot: dict[str, Any]) -> str:
        for item in reversed(cls._ledger(snapshot)):
            value = item.get("source_commit_after")
            if isinstance(value, str) and COMMIT_SHA.fullmatch(value):
                return value
        return ""

    @staticmethod
    def _ledger(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        context = snapshot.get("context", {})
        ledger = context.get("host_action_ledger", {}) if isinstance(context, dict) else {}
        if isinstance(ledger, dict):
            values = ledger.values()
        elif isinstance(ledger, list):
            values = ledger
        else:
            values = []
        return [item for item in values if isinstance(item, dict)]

    @classmethod
    def _has_incomplete_required_check(cls, snapshot: dict[str, Any]) -> bool:
        completion = snapshot.get("completion_checks")
        if not isinstance(completion, dict) or not completion:
            return True
        if any(value is not True for value in completion.values()):
            return True
        for item in cls._walk_dicts(snapshot):
            checks = item.get("required_checks")
            if isinstance(checks, dict) and any(
                str(value).upper() == "UNKNOWN" for value in checks.values()
            ):
                return True
            if isinstance(checks, list) and any(
                isinstance(check, dict)
                and str(check.get("status", "")).upper() == "UNKNOWN"
                for check in checks
            ):
                return True
        return False

    @classmethod
    def _worker(cls, snapshot: dict[str, Any]) -> str:
        for item in cls._walk_dicts(snapshot):
            for key in (
                "executor_identity",
                "host_identity",
                "worker",
                "worker_id",
                "selected_worker",
                "execution_host",
            ):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:120]
        return ""

    @staticmethod
    def _resolved_skills(snapshot: dict[str, Any]) -> list[str]:
        resolution = snapshot.get("resolution")
        if not isinstance(resolution, dict):
            raise BackendError("RuntimeV2 resolution is missing")
        skills = resolution.get("selected_starting_skills")
        if (
            resolution.get("abstain") is not False
            or str(resolution.get("routing_action", "")).upper() != "INVOKE"
            or not isinstance(skills, list)
            or not skills
            or not all(isinstance(skill, str) and skill for skill in skills)
        ):
            raise BackendError("RuntimeV2 did not resolve an executable capability")
        return skills

    @classmethod
    def _walk_dicts(cls, value: Any):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from cls._walk_dicts(child)
        elif isinstance(value, list):
            for child in value:
                yield from cls._walk_dicts(child)

    @staticmethod
    def _evidence_id(evidence: dict[str, Any]) -> str:
        return str(evidence.get("evidence_id", evidence.get("id", "")))

    @staticmethod
    def _snapshot(payload: dict[str, Any]) -> dict[str, Any]:
        for key in ("mission", "data"):
            nested = payload.get(key)
            if isinstance(nested, dict) and "mission_id" in nested:
                return nested
        return payload

    @staticmethod
    def _mission_id(snapshot: dict[str, Any]) -> str:
        context = snapshot.get("context", {})
        nested = context.get("mission_id", "") if isinstance(context, dict) else ""
        return str(snapshot.get("mission_id", nested))

    @staticmethod
    def _execution_id(snapshot: dict[str, Any]) -> str:
        context = snapshot.get("context", {})
        nested = context.get("execution_id", "") if isinstance(context, dict) else ""
        return str(snapshot.get("execution_id", nested))

    @staticmethod
    def _host_action_request(snapshot: dict[str, Any]) -> dict[str, Any] | None:
        direct = snapshot.get("host_action_request")
        if isinstance(direct, dict):
            return direct
        context = snapshot.get("context", {})
        nested = context.get("pending_host_action") if isinstance(context, dict) else None
        return nested if isinstance(nested, dict) else None

    @staticmethod
    def _blocker_detail(snapshot: dict[str, Any], state: str) -> str:
        for key in ("blocker", "reason", "required_user_question", "required_approval"):
            if snapshot.get(key):
                return f"RuntimeV2 {state}: {snapshot[key]}"
        request = OsaExecutionForceBackend._host_action_request(snapshot)
        if request:
            action_id = request.get("action_id", "") if isinstance(request, dict) else ""
            return f"RuntimeV2 {state}; host action required: {action_id or 'UNKNOWN'}"
        context = snapshot.get("context", {})
        blockers = context.get("blockers", []) if isinstance(context, dict) else []
        if blockers:
            return f"RuntimeV2 {state}: {redact(str(blockers))[:400]}"
        return f"RuntimeV2 {state}"

    def _artifact(
        self,
        session: ExecutionSession,
        node_id: str,
        kind: str,
        name: str,
        content: str,
    ) -> ExecutionArtifact:
        if not SAFE_SEGMENT.fullmatch(node_id):
            raise BackendError("unsafe artifact node")
        directory = self.artifact_root / session.mission_id / node_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{uuid.uuid4().hex[:8]}-{name}"
        data = redact(content).encode("utf-8")
        path.write_bytes(data)
        artifact = ExecutionArtifact(
            artifact_id=str(uuid.uuid4()),
            mission_id=session.mission_id,
            node_id=node_id,
            kind=kind,
            name=name,
            path=path,
            sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),
        )
        self._artifacts[session.session_id].append(artifact)
        return artifact

    def _persist_correlation(self, session_id: str, runtime_id: str) -> None:
        path = self._state_path(session_id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"hydraMissionId": session_id, "runtimeMissionId": runtime_id},
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _state_path(self, session_id: str) -> Path:
        return self.artifact_root / session_id / "remote-session" / "correlation.json"

    def _session(self, session_id: str) -> ExecutionSession:
        try:
            return self._sessions[session_id]
        except KeyError as error:
            raise BackendError(f"unknown OSA Execution Force session: {session_id}") from error

    def _emit(
        self, session: ExecutionSession, event_type: str, node_id: str, message: str
    ) -> None:
        self._events[session.session_id].append(
            ExecutionEvent(
                event_id=str(uuid.uuid4()),
                session_id=session.session_id,
                node_id=node_id,
                event_type=event_type,
                timestamp=utc_now(),
                message=redact(message)[:500],
            )
        )
