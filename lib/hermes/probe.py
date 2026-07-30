"""Live runtime probe.

The health table starts empty, and an unknown model reads as DOWN — so without
this module the router blocks forever. This is the piece that turns the live
sandbox state into provider health.

It reads, it never repairs. A sandbox that is not ready produces a DOWN entry and
an explicit reason, not an optimistic HEALTHY.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from . import config as config_module
from .router import HealthTable, ProviderHealth

# Phases in which inference is actually reachable. Anything else — Provisioning,
# Pending, Error, Terminating — means the model cannot serve a request.
READY_PHASES = frozenset({"ready", "running"})
DEGRADED_PHASES = frozenset({"degraded", "updating"})


class ProbeError(RuntimeError):
    """Raised when the runtime status could not be read at all."""


def extract_json(output: str) -> dict[str, Any]:
    """Pull the JSON object out of CLI output.

    `nemohermes` prefixes status output with human lines such as
    "✓ Active gateway set to 'nemoclaw'", so the payload does not start at byte
    zero. Scan to the first brace and decode from there.
    """
    start = output.find("{")
    if start < 0:
        raise ProbeError(f"no JSON object in runtime output: {output[:200]!r}")
    decoder = json.JSONDecoder()
    try:
        payload, _ = decoder.raw_decode(output[start:])
    except ValueError as error:
        raise ProbeError(f"runtime output is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ProbeError("runtime status is not a JSON object")
    return payload


@dataclass
class RuntimeStatus:
    sandbox: str
    found: bool
    agent: str
    phase: str
    provider: str
    model: str
    route_drift: Any
    raw: dict[str, Any]

    @property
    def ready(self) -> bool:
        return self.found and self.phase.lower() in READY_PHASES

    def health_status(self) -> str:
        if not self.found:
            return "DOWN"
        phase = self.phase.lower()
        if phase in READY_PHASES:
            return "HEALTHY"
        if phase in DEGRADED_PHASES:
            return "DEGRADED"
        return "DOWN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sandbox": self.sandbox,
            "found": self.found,
            "agent": self.agent,
            "phase": self.phase,
            "provider": self.provider,
            "model": self.model,
            "route_drift": self.route_drift,
            "ready": self.ready,
            "health_status": self.health_status(),
        }


def status_command(sandbox: str) -> str:
    """The command used to read runtime status.

    `HERMES_STATUS_CMD` exists so the probe can be tested offline against a stub.
    It is not a production hook: the default is the real CLI.
    """
    override = os.environ.get("HERMES_STATUS_CMD")
    if override:
        return override
    return f"nemohermes {shlex.quote(sandbox)} status --json"


def read_status(sandbox: str, timeout: int = 60) -> RuntimeStatus:
    command = status_command(sandbox)
    try:
        completed = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as error:
        raise ProbeError(f"runtime status timed out after {timeout}s") from error
    except OSError as error:
        raise ProbeError(f"could not run runtime status: {error}") from error

    # The CLI can report a usable payload on a non-zero exit, so parse whatever
    # it produced before judging it by its exit status.
    payload = extract_json(completed.stdout or completed.stderr or "")

    live = payload.get("liveRoute") or payload.get("recordedRoute") or {}
    return RuntimeStatus(
        sandbox=str(payload.get("name", sandbox)),
        found=bool(payload.get("found", False)),
        agent=str(payload.get("agent", "")),
        phase=str(payload.get("phase", "")),
        provider=str(live.get("provider") or payload.get("provider") or ""),
        model=str(live.get("model") or payload.get("model") or ""),
        route_drift=payload.get("routeDrift"),
        raw=payload,
    )


def probe(sandbox: str | None = None, health: HealthTable | None = None) -> dict[str, Any]:
    """Read the live route and write it into the health table.

    Capabilities come from the model catalogue. An unlisted model gets an empty
    capability set on purpose: the router will then block a task that requires a
    capability nobody has verified, rather than assume it.
    """
    sandbox = sandbox or os.environ.get("NEMOCLAW_SANDBOX_NAME", "hydra-hermes-lab")
    table = health if health is not None else HealthTable()

    started = time.monotonic()
    status = read_status(sandbox)
    latency_ms = int((time.monotonic() - started) * 1000)

    if not status.model:
        raise ProbeError("runtime status carries no model; cannot record health")

    catalogue = config_module.load_models().get("models", {})
    known = catalogue.get(status.model, {})
    capabilities = list(known.get("capabilities", []))

    previous = table.get(status.model)
    health_status = status.health_status()
    recent_failures = 0 if health_status == "HEALTHY" else (
        (previous.recent_failures + 1) if previous else 1
    )

    table.set(
        ProviderHealth(
            provider=status.provider or known.get("provider", "unknown"),
            model=status.model,
            status=health_status,
            latency_ms=latency_ms,
            recent_failures=recent_failures,
            supported_capabilities=capabilities,
        )
    )
    table.save()

    result = status.to_dict()
    result.update(
        {
            "latency_ms": latency_ms,
            "recorded_capabilities": capabilities,
            "in_catalogue": bool(known),
            "health_table": str(table.path),
        }
    )
    if not known:
        result["warning"] = (
            f"model {status.model!r} is not in config/models.yaml; no capabilities "
            "were recorded, so capability-requiring tasks will block"
        )
    return result
