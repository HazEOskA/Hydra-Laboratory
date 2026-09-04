"""Strongly typed control-plane contracts shared by the API and backends."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class MissionState(StrEnum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    FACT_LOADING = "FACT_LOADING"
    PLANNING = "PLANNING"
    AWAITING_ARCHITECTURE_APPROVAL = "AWAITING_ARCHITECTURE_APPROVAL"
    PROVISIONING = "PROVISIONING"
    RUNNING = "RUNNING"
    VALIDATING = "VALIDATING"
    REVIEWING = "REVIEWING"
    BUILDING_EVIDENCE = "BUILDING_EVIDENCE"
    AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
    PR_READY = "PR_READY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class NodeState(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_REQUIRED = "NOT_REQUIRED"


TERMINAL_MISSION_STATES = frozenset(
    {MissionState.COMPLETED, MissionState.CANCELLED}
)

TERMINAL_NODE_STATES = frozenset(
    {
        NodeState.PASSED,
        NodeState.FAILED,
        NodeState.SKIPPED,
        NodeState.CANCELLED,
        NodeState.UNKNOWN,
    }
)


@dataclass(frozen=True)
class PipelineNodeSpec:
    node_id: str
    name: str
    dependencies: tuple[str, ...] = ()
    backend: str = "deterministic-local"


@dataclass(frozen=True)
class MissionManifest:
    schema_version: str
    mission_id: str
    title: str
    request: str
    repository: str
    branch: str
    risk_level: RiskLevel
    execution_backend: str
    compiler: str
    validation_requirements: tuple[str, ...]
    execution_contract: dict[str, Any]
    nodes: tuple[PipelineNodeSpec, ...]
    failure_mode: str = "none"
    base_branch: str = "main"
    acceptance_criteria: tuple[str, ...] = ()
    required_tests: tuple[str, ...] = ()
    budget_limit: float = 0.0
    budget_scope: str = "global"
    requested_worker: str = "AUTO"
    timeout_seconds: int = 900
    blueprint: str = "standard-coding-mission"
    base_commit: str = ""
    allowed_scope: tuple[str, ...] = ()
    test_command: tuple[str, ...] = ()
    environment: str = "development"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risk_level"] = str(self.risk_level)
        payload["acceptance_criteria"] = list(self.acceptance_criteria)
        payload["required_tests"] = list(self.required_tests)
        payload["allowed_scope"] = list(self.allowed_scope)
        payload["test_command"] = list(self.test_command)
        payload["nodes"] = [
            {
                "node_id": node.node_id,
                "name": node.name,
                "dependencies": list(node.dependencies),
                "backend": node.backend,
            }
            for node in self.nodes
        ]
        payload["validation_requirements"] = list(self.validation_requirements)
        return payload


@dataclass(frozen=True)
class CreateSessionInput:
    mission_id: str
    repository: str
    branch: str
    failure_mode: str = "none"


@dataclass
class ExecutionSession:
    session_id: str
    mission_id: str
    backend: str
    workspace: Path
    status: str = "CREATED"
    base_commit: str = ""
    result_commit: str = ""


@dataclass(frozen=True)
class ExecuteTaskInput:
    session_id: str
    mission_id: str
    node_id: str
    attempt: int
    manifest: dict[str, Any]
    base_commit: str = ""
    result_commit: str = ""


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    display: str
    started_at: str
    finished_at: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    cancelled: bool = False


@dataclass(frozen=True)
class ExecutionArtifact:
    artifact_id: str
    mission_id: str
    node_id: str
    kind: str
    name: str
    path: Path
    sha256: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return payload


@dataclass(frozen=True)
class ExecutionEvent:
    event_id: str
    session_id: str
    node_id: str
    event_type: str
    timestamp: str
    message: str = ""


@dataclass(frozen=True)
class ExecutionStatus:
    session_id: str
    status: str
    current_node_id: str = ""
    commit_sha: str = ""
    detail: str = ""


@dataclass
class ExecutionResult:
    success: bool
    summary: str
    commands: list[CommandResult] = field(default_factory=list)
    artifacts: list[ExecutionArtifact] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""


class ControlPlaneError(RuntimeError):
    code = "CONTROL_PLANE_ERROR"
    status = 400


class ValidationError(ControlPlaneError):
    code = "VALIDATION_ERROR"
    status = 422


class NotFoundError(ControlPlaneError):
    code = "NOT_FOUND"
    status = 404


class ConflictError(ControlPlaneError):
    code = "CONFLICT"
    status = 409


class AuthorizationError(ControlPlaneError):
    """The actor is known but not permitted to take this action."""

    code = "NOT_AUTHORIZED"
    status = 403


class BackendError(ControlPlaneError):
    code = "BACKEND_ERROR"
    status = 500
