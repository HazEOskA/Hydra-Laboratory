"""Michael Angelo worker adapter registry.

Every worker Hydra can address is declared here exactly once. An adapter whose
runtime is not reachable reports ``UNAVAILABLE`` and *refuses* to execute; it is
never simulated and never silently downgraded to another worker. That refusal is
the contract: a mission routed to an unreachable worker fails loudly instead of
producing evidence that describes work nobody did.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Any, Callable

from .models import BackendError, ExecutionResult


AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"

# Minions are single-task workers *inside* Michael Angelo. They are not a new
# top-level control plane and never own a queue, schedule, or shared state.
KIND_LOCAL = "local-deterministic"
KIND_CLI = "external-cli"
KIND_SERVICE = "external-service"
KIND_MINION = "ephemeral-minion"


@dataclass(frozen=True)
class WorkerAdapter:
    """Declared worker. ``probe`` decides availability from the live host only."""

    worker_id: str
    name: str
    kind: str
    capabilities: tuple[str, ...]
    probe: Callable[[], tuple[str, str]]
    ephemeral: bool = False

    def status(self) -> tuple[str, str]:
        try:
            return self.probe()
        except Exception as error:  # a probe must never break the control plane
            return UNAVAILABLE, f"probe failed: {type(error).__name__}"

    def to_dict(self) -> dict[str, Any]:
        availability, reason = self.status()
        return {
            "workerId": self.worker_id,
            "name": self.name,
            "kind": self.kind,
            "availability": availability,
            "reason": reason,
            "capabilities": list(self.capabilities),
            "ephemeral": self.ephemeral,
        }


def _probe_local() -> tuple[str, str]:
    return AVAILABLE, "wbudowany worker deterministyczny; sandbox fixture-only"


def _probe_cli(binary: str, env_hint: str) -> Callable[[], tuple[str, str]]:
    def probe() -> tuple[str, str]:
        if shutil.which(binary) is None:
            return UNAVAILABLE, f"brak binarki '{binary}' w PATH"
        if env_hint and not os.environ.get(env_hint):
            return UNAVAILABLE, f"binarka '{binary}' obecna, brak {env_hint}"
        return AVAILABLE, f"wykryto '{binary}'"

    return probe


def _probe_service(env_var: str, label: str) -> Callable[[], tuple[str, str]]:
    def probe() -> tuple[str, str]:
        if not os.environ.get(env_var):
            return UNAVAILABLE, f"brak {env_var}; endpoint {label} nieskonfigurowany"
        return AVAILABLE, f"skonfigurowany endpoint {label}"

    return probe


def _probe_osa_execution_force() -> tuple[str, str]:
    if not os.environ.get("HYDRA_OSA_EXECUTION_FORCE_URL"):
        return UNAVAILABLE, "brak HYDRA_OSA_EXECUTION_FORCE_URL"
    if not os.environ.get("OSA_ACTIONS_API_KEY"):
        return UNAVAILABLE, "brak OSA_ACTIONS_API_KEY; RuntimeV2 nie jest autoryzowany"
    return AVAILABLE, "skonfigurowany oficjalny endpoint OSA Execution Force RuntimeV2"


def _probe_generic() -> tuple[str, str]:
    # The generic slot exists so a future Minion registers without a schema
    # change. It is deliberately never AVAILABLE until a concrete adapter binds.
    return UNAVAILABLE, "slot generyczny; brak powiązanego runtime'u Miniona"


REGISTRY: tuple[WorkerAdapter, ...] = (
    WorkerAdapter(
        worker_id="deterministic-local",
        name="Deterministic Local Worker",
        kind=KIND_LOCAL,
        capabilities=(
            "real-git-worktree",
            "controlled-change",
            "allowlisted-commands",
            "artifacts",
            "cancellation",
            "commit-bound-evidence",
        ),
        probe=_probe_local,
    ),
    WorkerAdapter(
        worker_id="osa-execution-force",
        name="OSA Execution Force RuntimeV2",
        kind=KIND_SERVICE,
        capabilities=(
            "skill-resolution",
            "execution-governance",
            "host-action-requests",
            "mechanical-verification",
            "verified-evidence",
        ),
        probe=_probe_osa_execution_force,
    ),
    WorkerAdapter(
        worker_id="codex",
        name="Codex Worker",
        kind=KIND_CLI,
        capabilities=("code-generation", "repo-edit"),
        probe=_probe_cli("codex", "HYDRA_CODEX_TOKEN"),
    ),
    WorkerAdapter(
        worker_id="openhands",
        name="OpenHands Worker",
        kind=KIND_SERVICE,
        capabilities=("code-generation", "repo-edit", "shell"),
        probe=_probe_service("HYDRA_OPENHANDS_URL", "OpenHands"),
    ),
    WorkerAdapter(
        worker_id="claude-worker",
        name="Claude Worker",
        kind=KIND_CLI,
        capabilities=("code-generation", "repo-edit", "review"),
        probe=_probe_cli("claude", "HYDRA_CLAUDE_WORKER_TOKEN"),
    ),
    WorkerAdapter(
        worker_id="generic-minion",
        name="Generic Minion Adapter",
        kind=KIND_MINION,
        capabilities=("single-task", "isolated-sandbox", "auto-terminate"),
        probe=_probe_generic,
        ephemeral=True,
    ),
)

REGISTRY_BY_ID = {adapter.worker_id: adapter for adapter in REGISTRY}


class UnavailableBackend:
    """Stands in for a declared-but-unreachable worker.

    It satisfies the ExecutionBackend shape so routing and storage stay uniform,
    but every operation raises. Nothing here fabricates a session, a commit, or
    a result.
    """

    def __init__(self, adapter: WorkerAdapter) -> None:
        self.backend_id = adapter.worker_id
        self.adapter = adapter

    def _refuse(self) -> ExecutionResult:
        _, reason = self.adapter.status()
        raise BackendError(
            f"worker '{self.adapter.worker_id}' is UNAVAILABLE: {reason}"
        )

    def create_session(self, input: Any) -> Any:
        self._refuse()

    def execute_task(self, input: Any) -> ExecutionResult:
        self._refuse()

    def get_status(self, session_id: str) -> Any:
        self._refuse()

    def stream_events(self, session_id: str) -> Any:
        self._refuse()

    def cancel(self, session_id: str) -> None:
        self._refuse()

    def collect_artifacts(self, session_id: str) -> list[Any]:
        self._refuse()


def describe_workers() -> list[dict[str, Any]]:
    return [adapter.to_dict() for adapter in REGISTRY]


def available_worker_ids() -> list[str]:
    return [
        adapter.worker_id
        for adapter in REGISTRY
        if adapter.status()[0] == AVAILABLE
    ]


def resolve_worker(requested: str) -> str:
    """Resolve a requested worker id, honouring AUTO.

    AUTO picks the first AVAILABLE adapter in declaration order. An explicitly
    requested worker is never substituted — asking for an unreachable worker is
    an error, not an invitation to run something else.
    """
    if requested == "AUTO":
        candidates = available_worker_ids()
        if not candidates:
            raise BackendError("AUTO routing found no AVAILABLE worker")
        return candidates[0]
    adapter = REGISTRY_BY_ID.get(requested)
    if adapter is None:
        raise BackendError(f"unknown worker: {requested}")
    availability, reason = adapter.status()
    if availability != AVAILABLE:
        raise BackendError(f"worker '{requested}' is UNAVAILABLE: {reason}")
    return requested
