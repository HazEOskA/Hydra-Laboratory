"""Mission orchestration, approvals, retry, recovery and APR evidence binding."""

from __future__ import annotations

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from hermes.redact import excerpt, redact

from .backend import BACKEND_ID, SAFE_REPOSITORY, DeterministicLocalBackend, ExecutionBackend
from .compiler import DeterministicMissionCompiler, MissionCompiler
from .models import (
    CheckStatus,
    ConflictError,
    CreateSessionInput,
    ExecuteTaskInput,
    ExecutionResult,
    MissionState,
    NodeState,
    NotFoundError,
    ValidationError,
)
from .store import ControlPlaneStore, utc_now


ALLOWED_CREATE_FIELDS = frozenset(
    {"title", "request", "repository", "backend", "failureMode"}
)
ALLOWED_FAILURE_MODES = frozenset({"none", "tests_once"})
ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._@-]{0,79}$")

NODE_MISSION_STATES = {
    "mission-intake": MissionState.QUEUED,
    "repository-fact-load": MissionState.FACT_LOADING,
    "feasibility-analysis": MissionState.PLANNING,
    "implementation-plan": MissionState.PLANNING,
    "sandbox-provisioning": MissionState.PROVISIONING,
    "agent-execution": MissionState.RUNNING,
    "quality-checks": MissionState.VALIDATING,
    "targeted-tests": MissionState.VALIDATING,
    "runtime-verification": MissionState.VALIDATING,
    "independent-review": MissionState.REVIEWING,
    "apr-evidence": MissionState.BUILDING_EVIDENCE,
    "draft-pull-request": MissionState.PR_READY,
}

GATES = {
    "architecture-gate": (
        "architecture",
        MissionState.AWAITING_ARCHITECTURE_APPROVAL,
    ),
    "human-approval": ("human", MissionState.AWAITING_HUMAN_APPROVAL),
}


class MissionService:
    def __init__(
        self,
        store: ControlPlaneStore,
        backend: ExecutionBackend,
        compiler: MissionCompiler | None = None,
    ) -> None:
        self.store = store
        self.backend = backend
        self.compiler = compiler or DeterministicMissionCompiler()
        self._locks: dict[str, threading.Lock] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._guard = threading.RLock()

    @classmethod
    def local(cls, state_root: str | Path) -> "MissionService":
        repo_root = Path(__file__).resolve().parents[2]
        store = ControlPlaneStore(state_root)
        backend = DeterministicLocalBackend(
            store.workspace_root,
            store.artifact_root,
            repo_root / "tests" / "fixtures" / "hydra-safe-demo",
        )
        return cls(store, backend)

    def create_mission(self, payload: dict[str, Any], actor: str = "OSA") -> dict[str, Any]:
        self._validate_actor(actor)
        if not isinstance(payload, dict):
            raise ValidationError("request body must be a JSON object")
        unknown = sorted(set(payload) - ALLOWED_CREATE_FIELDS)
        if unknown:
            raise ValidationError(f"unknown fields: {', '.join(unknown)}")
        title = self._required_string(payload, "title", 120)
        request = self._required_string(payload, "request", 5000)
        repository = payload.get("repository", SAFE_REPOSITORY)
        backend_id = payload.get("backend", BACKEND_ID)
        failure_mode = payload.get("failureMode", "none")
        if repository != SAFE_REPOSITORY:
            raise ValidationError(
                "initial backend accepts only fixture://hydra-safe-demo; host paths and URLs are forbidden"
            )
        if backend_id != BACKEND_ID:
            raise ValidationError(f"unsupported execution backend: {backend_id}")
        if failure_mode not in ALLOWED_FAILURE_MODES:
            raise ValidationError(
                f"failureMode must be one of: {', '.join(sorted(ALLOWED_FAILURE_MODES))}"
            )
        mission_id = str(uuid.uuid4())
        manifest = self.compiler.compile(
            mission_id=mission_id,
            title=title,
            request=request,
            repository=repository,
            backend=backend_id,
            failure_mode=failure_mode,
        )
        return self.store.create_mission(manifest, actor)

    def list_missions(self) -> list[dict[str, Any]]:
        return self.store.list_missions()

    def mission(self, mission_id: str) -> dict[str, Any]:
        return self.store.get_mission(mission_id)

    def start(self, mission_id: str, actor: str = "OSA", *, asynchronous: bool = True) -> dict[str, Any]:
        self._validate_actor(actor)
        mission = self.store.get_mission(mission_id)
        if mission["state"] != MissionState.DRAFT:
            raise ConflictError(f"mission cannot start from {mission['state']}")
        self._ensure_session(mission)
        self.store.set_mission_state(
            mission_id,
            MissionState.QUEUED,
            actor=actor,
            node_id="mission-intake",
            message="mission queued for deterministic execution",
        )
        self._dispatch(mission_id, asynchronous=asynchronous)
        return self.store.get_mission(mission_id)

    def approve(
        self,
        mission_id: str,
        *,
        gate: str,
        actor: str,
        asynchronous: bool = True,
    ) -> dict[str, Any]:
        self._validate_actor(actor)
        node_id = {"architecture": "architecture-gate", "human": "human-approval"}.get(gate)
        if node_id is None:
            raise ValidationError("gate must be 'architecture' or 'human'")
        mission = self.store.get_mission(mission_id)
        node = next(node for node in mission["nodes"] if node["node_id"] == node_id)
        expected_state = (
            MissionState.AWAITING_ARCHITECTURE_APPROVAL
            if gate == "architecture"
            else MissionState.AWAITING_HUMAN_APPROVAL
        )
        if mission["state"] != expected_state or node["state"] != NodeState.BLOCKED:
            raise ConflictError(
                f"{gate} approval is not pending (mission={mission['state']}, node={node['state']})"
            )
        approval = self.store.approve(mission_id, node_id, gate, actor)
        self.store.transition_node(
            mission_id,
            node_id,
            NodeState.READY,
            actor=actor,
            message=f"{gate} gate released by scoped approval",
            validation_result="UNKNOWN",
        )
        self.store.set_mission_state(
            mission_id,
            MissionState.QUEUED,
            actor=actor,
            node_id=node_id,
            message=f"resuming after {gate} approval",
        )
        self._ensure_session(self.store.get_mission(mission_id))
        self._dispatch(mission_id, asynchronous=asynchronous)
        return {"approval": approval, "mission": self.store.get_mission(mission_id)}

    def retry(
        self,
        mission_id: str,
        node_id: str,
        actor: str = "OSA",
        *,
        asynchronous: bool = True,
    ) -> dict[str, Any]:
        self._validate_actor(actor)
        mission = self.store.get_mission(mission_id)
        node = next((item for item in mission["nodes"] if item["node_id"] == node_id), None)
        if node is None:
            raise NotFoundError(f"unknown node: {mission_id}/{node_id}")
        if mission["state"] != MissionState.FAILED or node["state"] != NodeState.FAILED:
            raise ConflictError("retry requires the selected node and mission to be FAILED")
        self.store.transition_node(
            mission_id,
            node_id,
            NodeState.READY,
            actor=actor,
            message="scoped single-node retry requested",
            validation_result="UNKNOWN",
        )
        self.store.set_mission_state(
            mission_id,
            MissionState.QUEUED,
            actor=actor,
            node_id=node_id,
            message="failed node queued without restarting passed nodes",
        )
        self._ensure_session(self.store.get_mission(mission_id))
        self._dispatch(mission_id, asynchronous=asynchronous)
        return self.store.get_mission(mission_id)

    def cancel(self, mission_id: str, actor: str = "OSA") -> dict[str, Any]:
        self._validate_actor(actor)
        self.store.get_mission(mission_id)
        try:
            self.backend.cancel(mission_id)
        except Exception:
            # A draft mission may not have an execution session yet. The durable
            # cancellation still wins and no backend work has started.
            pass
        self.store.cancel_mission(mission_id, actor, "cancelled by human operator")
        return self.store.get_mission(mission_id)

    def recover(self, *, asynchronous: bool = True) -> list[str]:
        recovered = self.store.recover_interrupted()
        for mission_id in recovered:
            mission = self.store.get_mission(mission_id)
            self._ensure_session(mission)
            self._dispatch(mission_id, asynchronous=asynchronous)
        return recovered

    def events(self, mission_id: str) -> list[dict[str, Any]]:
        return self.store.events(mission_id)

    def logs(self, mission_id: str) -> list[dict[str, Any]]:
        return self.store.logs(mission_id)

    def artifacts(self, mission_id: str) -> list[dict[str, Any]]:
        return self.store.artifacts(mission_id)

    def artifact_bytes(self, artifact_id: str) -> bytes:
        return self.store.read_artifact(artifact_id)

    def evidence(self, mission_id: str) -> dict[str, Any]:
        bundle = self.store.evidence(mission_id)
        if bundle is None:
            return {"available": False, "valid": False, "invalidReasons": ["evidence not generated"]}
        reasons: list[str] = []
        mission = self.store.get_mission(mission_id)
        self._ensure_session(mission)
        status = self.backend.get_status(mission_id)
        if status.commit_sha != bundle["resultCommit"]:
            reasons.append(
                f"workspace HEAD {status.commit_sha or 'UNKNOWN'} does not match resultCommit {bundle['resultCommit']}"
            )
        chain_ok, chain_detail = self.store.verify_event_chain(mission_id)
        if not chain_ok:
            reasons.append(chain_detail)
        for artifact in bundle.get("artifacts", []):
            try:
                self.store.read_artifact(artifact["artifactId"])
            except Exception:
                reasons.append(f"artifact invalid: {artifact['artifactId']}")
        required_checks = bundle.get("checks", {})
        for name, value in required_checks.items():
            if value in (CheckStatus.FAIL, CheckStatus.UNKNOWN):
                reasons.append(f"check {name} is {value}")
        if mission["result_commit"] != bundle["resultCommit"]:
            reasons.append("stored mission result commit no longer matches the evidence bundle")
        return {
            "available": True,
            "valid": not reasons,
            "invalidReasons": reasons,
            "eventChain": chain_detail,
            "bundle": bundle,
        }

    def backends(self) -> list[dict[str, Any]]:
        return [
            {
                "id": BACKEND_ID,
                "name": "Deterministic Local Worker",
                "available": True,
                "isolated": "dedicated fixture workspace",
                "network": False,
                "productionCredentials": False,
                "capabilities": [
                    "real-git-worktree",
                    "controlled-change",
                    "allowlisted-commands",
                    "artifacts",
                    "cancellation",
                    "commit-bound-evidence",
                ],
            }
        ]

    def _dispatch(self, mission_id: str, *, asynchronous: bool) -> None:
        if not asynchronous:
            self._run_until_pause(mission_id)
            return
        with self._guard:
            thread = self._threads.get(mission_id)
            if thread and thread.is_alive():
                raise ConflictError("mission runner is already active")
            thread = threading.Thread(
                target=self._run_until_pause,
                args=(mission_id,),
                name=f"hydra-{mission_id[:8]}",
                daemon=True,
            )
            self._threads[mission_id] = thread
            thread.start()

    def wait(self, mission_id: str, timeout: float = 30.0) -> None:
        thread = self._threads.get(mission_id)
        if thread:
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError(f"mission runner did not pause within {timeout}s")

    def _run_until_pause(self, mission_id: str) -> None:
        with self._mission_lock(mission_id):
            mission = self.store.get_mission(mission_id)
            session = self._ensure_session(mission)
            for node in mission["nodes"]:
                current = self.store.get_mission(mission_id)
                if current["state"] == MissionState.CANCELLED:
                    return
                fresh = next(item for item in current["nodes"] if item["node_id"] == node["node_id"])
                if fresh["state"] in (NodeState.PASSED, NodeState.SKIPPED):
                    continue
                if fresh["state"] in (NodeState.FAILED, NodeState.CANCELLED, NodeState.UNKNOWN):
                    return
                dependencies = fresh["dependencies"]
                if any(
                    next(item for item in current["nodes"] if item["node_id"] == dependency)["state"]
                    != NodeState.PASSED
                    for dependency in dependencies
                ):
                    self.store.set_mission_state(
                        mission_id,
                        MissionState.BLOCKED,
                        actor="hydra-orchestrator",
                        node_id=fresh["node_id"],
                        message="node dependency is not satisfied",
                        failure_reason="dependency gate failed",
                    )
                    return
                if fresh["state"] == NodeState.PENDING:
                    fresh = self.store.transition_node(
                        mission_id,
                        fresh["node_id"],
                        NodeState.READY,
                        actor="hydra-orchestrator",
                        message="dependencies satisfied",
                    )
                if fresh["node_id"] in GATES:
                    gate, waiting_state = GATES[fresh["node_id"]]
                    if not self.store.has_approval(mission_id, gate):
                        self.store.transition_node(
                            mission_id,
                            fresh["node_id"],
                            NodeState.BLOCKED,
                            actor="hydra-orchestrator",
                            message=f"waiting for scoped {gate} approval",
                            summary=f"{gate} approval required",
                            validation_result="UNKNOWN",
                        )
                        self.store.set_mission_state(
                            mission_id,
                            waiting_state,
                            actor="hydra-orchestrator",
                            node_id=fresh["node_id"],
                            message=f"pipeline paused at {gate} gate",
                        )
                        return
                    self.store.transition_node(
                        mission_id,
                        fresh["node_id"],
                        NodeState.RUNNING,
                        actor="hydra-orchestrator",
                        message=f"scoped {gate} approval verified",
                    )
                    self.store.transition_node(
                        mission_id,
                        fresh["node_id"],
                        NodeState.PASSED,
                        actor="hydra-orchestrator",
                        message=f"{gate} gate passed",
                        summary=f"approved by scoped {gate} approval",
                        validation_result="PASS",
                    )
                    continue
                state = NODE_MISSION_STATES[fresh["node_id"]]
                self.store.set_mission_state(
                    mission_id,
                    state,
                    actor="hydra-orchestrator",
                    node_id=fresh["node_id"],
                    message=f"executing {fresh['name']}",
                )
                fresh = self.store.transition_node(
                    mission_id,
                    fresh["node_id"],
                    NodeState.RUNNING,
                    actor="hydra-orchestrator",
                    message="backend execution started",
                )
                current = self.store.get_mission(mission_id)
                result = self.backend.execute_task(
                    ExecuteTaskInput(
                        session_id=session.session_id,
                        mission_id=mission_id,
                        node_id=fresh["node_id"],
                        attempt=fresh["attempt"],
                        manifest=current["manifest"],
                        base_commit=current["base_commit"],
                        result_commit=current["result_commit"],
                    )
                )
                if self.store.get_mission(mission_id)["state"] == MissionState.CANCELLED:
                    return
                artifact_refs, command_summary = self._persist_result(
                    mission_id, fresh["node_id"], result
                )
                if result.metadata.get("baseCommit") or result.metadata.get("resultCommit"):
                    self.store.set_commits(
                        mission_id,
                        base_commit=result.metadata.get("baseCommit"),
                        result_commit=result.metadata.get("resultCommit"),
                        workspace=session.workspace,
                    )
                if result.success and fresh["node_id"] == "apr-evidence":
                    bundle = self._build_evidence(mission_id, result.metadata)
                    evidence_artifact = self.backend.evidence_artifact(
                        session.session_id, fresh["node_id"], bundle
                    )
                    self.store.register_artifact(evidence_artifact)
                    artifact_refs.append(evidence_artifact.artifact_id)
                    self.store.save_evidence(mission_id, bundle)
                if result.success:
                    commit_sha = self.store.get_mission(mission_id)["result_commit"]
                    self.store.transition_node(
                        mission_id,
                        fresh["node_id"],
                        NodeState.PASSED,
                        actor=self.backend.backend_id,
                        message="backend returned verified success",
                        summary=result.summary,
                        validation_result="PASS",
                        artifact_refs=artifact_refs,
                        command_result=command_summary,
                        commit_sha=commit_sha,
                    )
                else:
                    detail = result.metadata.get("detail", result.summary)
                    self.store.transition_node(
                        mission_id,
                        fresh["node_id"],
                        NodeState.FAILED,
                        actor=self.backend.backend_id,
                        message=result.error_code or "backend execution failed",
                        summary=redact(detail)[:500],
                        validation_result="FAIL",
                        artifact_refs=artifact_refs,
                        command_result=command_summary,
                    )
                    self.store.set_mission_state(
                        mission_id,
                        MissionState.FAILED,
                        actor="hydra-orchestrator",
                        node_id=fresh["node_id"],
                        message="mission stopped at failed node",
                        failure_reason=f"{fresh['name']}: {result.error_code or result.summary}",
                    )
                    return
            evidence = self.evidence(mission_id)
            if not evidence.get("valid"):
                self.store.set_mission_state(
                    mission_id,
                    MissionState.BLOCKED,
                    actor="hydra-orchestrator",
                    node_id="apr-evidence",
                    message="completion refused because APR evidence is invalid",
                    failure_reason="; ".join(evidence.get("invalidReasons", []))[:500],
                )
                return
            self.store.set_mission_state(
                mission_id,
                MissionState.COMPLETED,
                actor="hydra-orchestrator",
                node_id="draft-pull-request",
                message="all required pipeline gates passed",
                final_outcome="DRAFT_READY_LOCAL",
                commit_sha=self.store.get_mission(mission_id)["result_commit"],
            )

    def _persist_result(
        self, mission_id: str, node_id: str, result: ExecutionResult
    ) -> tuple[list[str], dict[str, Any] | None]:
        refs: list[str] = []
        for artifact in result.artifacts:
            self.store.register_artifact(artifact)
            refs.append(artifact.artifact_id)
        current_commit = self.backend.get_status(mission_id).commit_sha
        last_command: dict[str, Any] | None = None
        for index, command in enumerate(result.commands, start=1):
            stdout, stderr = self.backend.command_artifacts(
                mission_id, node_id, command, index
            )
            self.store.register_artifact(stdout)
            self.store.register_artifact(stderr)
            refs.extend([stdout.artifact_id, stderr.artifact_id])
            command_id = str(uuid.uuid4())
            self.store.record_command(
                command_id=command_id,
                mission_id=mission_id,
                node_id=node_id,
                command=list(command.command),
                display=command.display,
                started_at=command.started_at,
                finished_at=command.finished_at,
                exit_code=command.exit_code,
                stdout_artifact_id=stdout.artifact_id,
                stderr_artifact_id=stderr.artifact_id,
                timed_out=command.timed_out,
                cancelled=command.cancelled,
                commit_sha=current_commit,
            )
            self.store.append_log(
                mission_id,
                node_id,
                "command",
                f"$ {command.display}\nexit={command.exit_code}",
            )
            if command.stdout:
                self.store.append_log(
                    mission_id, node_id, "stdout", excerpt(command.stdout, 1000)
                )
            if command.stderr:
                self.store.append_log(
                    mission_id, node_id, "stderr", excerpt(command.stderr, 1000)
                )
            last_command = {
                "commandId": command_id,
                "command": command.display,
                "exitCode": command.exit_code,
                "stdoutArtifactId": stdout.artifact_id,
                "stderrArtifactId": stderr.artifact_id,
            }
        self.store.append_log(mission_id, node_id, "system", result.summary)
        return refs, last_command

    def _build_evidence(
        self, mission_id: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        mission = self.store.get_mission(mission_id)
        node_states = {node["node_id"]: node["state"] for node in mission["nodes"]}

        def outcome(node_id: str) -> str:
            state = node_states.get(node_id, NodeState.UNKNOWN)
            if state == NodeState.PASSED:
                return str(CheckStatus.PASS)
            if state == NodeState.FAILED:
                return str(CheckStatus.FAIL)
            return str(CheckStatus.UNKNOWN)

        checks = {
            "format": outcome("quality-checks"),
            "lint": outcome("quality-checks"),
            "typecheck": str(CheckStatus.NOT_REQUIRED),
            "tests": outcome("targeted-tests"),
            "build": str(CheckStatus.NOT_REQUIRED),
            "runtimeVerification": outcome("runtime-verification"),
            "review": outcome("independent-review"),
        }
        command_entries = []
        for command in self.store.commands(mission_id):
            command_entries.append(
                {
                    "command": command["display"],
                    "argv": command["command"],
                    "startedAt": command["started_at"],
                    "finishedAt": command["finished_at"],
                    "exitCode": command["exit_code"],
                    "stdoutArtifactId": command["stdout_artifact_id"],
                    "stderrArtifactId": command["stderr_artifact_id"],
                }
            )
        artifacts = [
            {
                "artifactId": artifact["artifact_id"],
                "nodeId": artifact["node_id"],
                "kind": artifact["kind"],
                "name": artifact["name"],
                "sha256": artifact["sha256"],
                "size": artifact["size"],
            }
            for artifact in self.store.artifacts(mission_id)
        ]
        bundle = {
            "schemaVersion": "1.0",
            "missionId": mission_id,
            "repository": mission["repository"],
            "baseCommit": mission["base_commit"],
            "resultCommit": mission["result_commit"],
            "branch": mission["branch"],
            "changedFiles": metadata.get("changedFiles", []),
            "diffSummary": metadata.get("diffSummary", ""),
            "commands": command_entries,
            "checks": checks,
            "artifacts": artifacts,
            "risks": [
                {
                    "level": mission["risk_level"],
                    "description": "controlled code modification in a fixture-only workspace",
                    "productionImpact": False,
                }
            ],
            "generatedAt": utc_now(),
        }
        if metadata.get("currentCommit") != mission["result_commit"]:
            raise ConflictError("APR evidence cannot bind to a stale result commit")
        if any(value in (CheckStatus.FAIL, CheckStatus.UNKNOWN) for value in checks.values()):
            raise ConflictError("APR evidence contains a failed or unknown required check")
        return bundle

    def _ensure_session(self, mission: dict[str, Any]):
        return self.backend.create_session(
            CreateSessionInput(
                mission_id=mission["mission_id"],
                repository=mission["repository"],
                branch=mission["branch"],
                failure_mode=mission["failureMode"],
            )
        )

    def _mission_lock(self, mission_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(mission_id, threading.Lock())

    @staticmethod
    def _required_string(payload: dict[str, Any], key: str, maximum: int) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{key} must be a non-empty string")
        value = value.strip()
        if len(value) > maximum:
            raise ValidationError(f"{key} exceeds {maximum} characters")
        if "\x00" in value:
            raise ValidationError(f"{key} contains a null byte")
        return value

    @staticmethod
    def _validate_actor(actor: str) -> None:
        if not isinstance(actor, str) or not ACTOR_PATTERN.fullmatch(actor):
            raise ValidationError("actor must be 1-80 safe display characters")
