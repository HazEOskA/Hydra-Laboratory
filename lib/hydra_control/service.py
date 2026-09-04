"""Mission orchestration, approvals, retry, recovery and APR evidence binding."""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from hermes.redact import excerpt, redact

from .adapters import describe_workers, resolve_worker
from .backend import BACKEND_ID, SAFE_REPOSITORY, DeterministicLocalBackend, ExecutionBackend
from .compiler import DeterministicMissionCompiler, MissionCompiler
from .models import (
    AuthorizationError,
    BackendError,
    CheckStatus,
    ConflictError,
    CreateSessionInput,
    ExecuteTaskInput,
    ExecutionResult,
    MissionState,
    NodeState,
    NotFoundError,
    RiskLevel,
    ValidationError,
)
from .store import ControlPlaneStore, utc_now
from .zgredek import (
    STATUS_APPROVED,
    ContextAuthority,
    ContextPacket,
    DeterministicZgredek,
)


ALLOWED_CREATE_FIELDS = frozenset(
    {
        "title",
        "request",
        "repository",
        "backend",
        "failureMode",
        # Canonical Michael Angelo coding-mission intake.
        "baseBranch",
        "acceptanceCriteria",
        "requiredTests",
        "riskLevel",
        "budgetLimit",
        "budgetScope",
        "worker",
        "timeoutSeconds",
        "blueprint",
        "priority",
        "baseCommit",
        "allowedScope",
        "testCommand",
        "environment",
    }
)
ALLOWED_FAILURE_MODES = frozenset({"none", "tests_once"})
ALLOWED_BLUEPRINTS = frozenset({"standard-coding-mission", "quality-only"})
BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
MAX_TIMEOUT_SECONDS = 3600
MAX_BUDGET_LIMIT = 1000.0
OSA_EXECUTION_FORCE_BACKEND_ID = "osa-execution-force"
COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
CANONICAL_REPOSITORY_PATTERN = re.compile(
    r"^github://[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$"
)
ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._@-]{0,79}$")
SCOPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,59}$")

# Declared model routes. Availability is probed from the host at read time; a
# route is never reported AVAILABLE just because it is declared here.
MODEL_ROUTES = (
    ("claude-opus-4", "anthropic", "coding"),
    ("claude-sonnet-4", "anthropic", "review"),
    ("gpt-codex", "openai", "coding"),
    ("local-deterministic", "local", "deterministic"),
)
MODEL_PROVIDER_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "local": "",
}
# Compute-time billing rate for workers that spend no model tokens.
COMPUTE_RATE_PER_SECOND = 0.001

# The node Zgredek's context packet gates. Fact loading is the first step that
# reads the repository, so it is the right place to require approved context.
CONTEXT_GATED_NODE = "repository-fact-load"

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
        zgredek: ContextAuthority | None = None,
    ) -> None:
        self.store = store
        self.backend = backend
        self.compiler = compiler or DeterministicMissionCompiler()
        self.zgredek = zgredek or DeterministicZgredek(
            Path(__file__).resolve().parents[2]
        )
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

    @classmethod
    def configured(cls, state_root: str | Path) -> "MissionService":
        """Build the single execution authority selected by host configuration."""
        backend_id = os.environ.get("HYDRA_EXECUTION_BACKEND", BACKEND_ID)
        if backend_id == BACKEND_ID:
            return cls.local(state_root)
        if backend_id == OSA_EXECUTION_FORCE_BACKEND_ID:
            from .osa_execution_force import OsaExecutionForceBackend

            store = ControlPlaneStore(state_root)
            try:
                backend = OsaExecutionForceBackend.from_environment(store.artifact_root)
            except Exception:
                store.close()
                raise
            return cls(store, backend)
        raise BackendError(f"unsupported configured execution backend: {backend_id}")

    def create_mission(self, payload: dict[str, Any], actor: str = "OSA") -> dict[str, Any]:
        self._validate_actor(actor)
        if not isinstance(payload, dict):
            raise ValidationError("request body must be a JSON object")
        unknown = sorted(set(payload) - ALLOWED_CREATE_FIELDS)
        if unknown:
            raise ValidationError(f"unknown fields: {', '.join(unknown)}")
        title = self._required_string(payload, "title", 120)
        request = self._required_string(payload, "request", 5000)
        backend_id = payload.get("backend", self.backend.backend_id)
        repository = payload.get(
            "repository", SAFE_REPOSITORY if backend_id == BACKEND_ID else ""
        )
        failure_mode = payload.get("failureMode", "none")
        if backend_id != self.backend.backend_id:
            raise ValidationError(
                f"backend '{backend_id}' is not the configured execution authority"
            )
        if backend_id == BACKEND_ID and repository != SAFE_REPOSITORY:
            raise ValidationError(
                "initial backend accepts only fixture://hydra-safe-demo; host paths and URLs are forbidden"
            )
        if backend_id == OSA_EXECUTION_FORCE_BACKEND_ID and (
            not isinstance(repository, str)
            or not CANONICAL_REPOSITORY_PATTERN.fullmatch(repository)
        ):
            raise ValidationError(
                "OSA Execution Force requires repository=github://owner/repository"
            )
        if failure_mode not in ALLOWED_FAILURE_MODES:
            raise ValidationError(
                f"failureMode must be one of: {', '.join(sorted(ALLOWED_FAILURE_MODES))}"
            )

        base_branch = payload.get("baseBranch", "main")
        if not isinstance(base_branch, str) or not BRANCH_PATTERN.fullmatch(base_branch):
            raise ValidationError("baseBranch must be a safe branch name")
        acceptance = self._string_list(payload, "acceptanceCriteria", 20, 400)
        required_tests = self._string_list(payload, "requiredTests", 20, 200)
        blueprint = payload.get("blueprint", "standard-coding-mission")
        if blueprint not in ALLOWED_BLUEPRINTS:
            raise ValidationError(
                f"blueprint must be one of: {', '.join(sorted(ALLOWED_BLUEPRINTS))}"
            )
        risk_override = payload.get("riskLevel")
        if risk_override is not None:
            if risk_override not in set(RiskLevel):
                raise ValidationError(
                    f"riskLevel must be one of: {', '.join(sorted(str(r) for r in RiskLevel))}"
                )
            risk_override = RiskLevel(risk_override)
        timeout_seconds = self._bounded_int(payload, "timeoutSeconds", 900, 30, MAX_TIMEOUT_SECONDS)
        priority = self._bounded_int(payload, "priority", 100, 1, 1000)
        budget_limit = self._bounded_float(payload, "budgetLimit", 0.0, 0.0, MAX_BUDGET_LIMIT)
        budget_scope = payload.get("budgetScope", "global")
        if not isinstance(budget_scope, str) or not SCOPE_PATTERN.fullmatch(budget_scope):
            raise ValidationError("budgetScope must be 1-60 safe identifier characters")

        base_commit = payload.get("baseCommit", "")
        allowed_scope = self._string_list(payload, "allowedScope", 50, 240)
        test_command = self._string_list(payload, "testCommand", 30, 500)
        environment = payload.get("environment", "development")
        if backend_id == OSA_EXECUTION_FORCE_BACKEND_ID:
            if not isinstance(base_commit, str) or not COMMIT_SHA_PATTERN.fullmatch(base_commit):
                raise ValidationError(
                    "baseCommit must be an exact lowercase 40-character Git SHA"
                )
            if not allowed_scope:
                raise ValidationError("allowedScope is required for OSA Execution Force")
            if not test_command:
                raise ValidationError("testCommand is required for OSA Execution Force")
            for path in allowed_scope:
                if path.startswith(("/", "~")) or ".." in Path(path).parts:
                    raise ValidationError(
                        "allowedScope entries must be repository-relative"
                    )
            if environment != "development":
                raise ValidationError(
                    "P0 OSA Execution Force missions require environment=development"
                )
            if failure_mode != "none":
                raise ValidationError(
                    "OSA Execution Force does not accept fixture failure modes"
                )
        elif base_commit or allowed_scope or test_command or "environment" in payload:
            raise ValidationError(
                "baseCommit, allowedScope, testCommand and environment belong to OSA Execution Force"
            )

        # Worker routing resolves before anything is stored. An unreachable
        # worker fails intake instead of producing a mission that cannot run.
        requested_worker = payload.get("worker", "AUTO")
        if not isinstance(requested_worker, str):
            raise ValidationError("worker must be a string")
        try:
            resolved_worker = resolve_worker(
                backend_id if requested_worker == "AUTO" else requested_worker
            )
        except BackendError as error:
            raise ValidationError(str(error)) from error
        if resolved_worker != backend_id:
            raise ValidationError(
                f"worker '{resolved_worker}' has no registered execution backend"
            )
        availability = getattr(self.backend, "availability", None)
        if callable(availability):
            status, reason = availability()
            if status != "AVAILABLE":
                raise ValidationError(
                    f"worker '{backend_id}' is UNAVAILABLE: {reason}"
                )

        mission_id = str(uuid.uuid4())
        manifest = self.compiler.compile(
            mission_id=mission_id,
            title=title,
            request=request,
            repository=repository,
            backend=backend_id,
            failure_mode=failure_mode,
            base_branch=base_branch,
            acceptance_criteria=acceptance,
            required_tests=required_tests,
            budget_limit=budget_limit,
            budget_scope=budget_scope,
            requested_worker=requested_worker,
            timeout_seconds=timeout_seconds,
            blueprint=blueprint,
            risk_override=risk_override,
            base_commit=base_commit,
            allowed_scope=allowed_scope,
            test_command=test_command,
            environment=environment,
        )
        mission = self.store.create_mission(manifest, actor)
        if base_commit:
            self.store.set_commits(mission_id, base_commit=base_commit)
            mission = self.store.get_mission(mission_id)

        # Zgredek prepares and approves the context before the mission may run.
        # It does not execute anything; Hydra enforces the packet at dispatch.
        packet = self.zgredek.prepare(
            mission_id=mission_id,
            repository=repository,
            base_branch=base_branch,
            now=utc_now(),
        ).to_dict()
        self.store.save_context_packet(mission_id, packet)
        self.store.append_context_event(
            mission_id,
            event_type="CONTEXT_PACKET_PREPARED",
            actor=self.zgredek.adapter_id,
            verdict="PREPARED",
            message=(
                f"context packet {packet['sha256'][:12]} prepared and pending approval; "
                f"{len(packet['architectureLocks'])} locks, "
                f"{len(packet['acceptedDecisions'])} decisions"
            ),
        )

        self.store.enqueue(mission_id, priority=priority)
        return mission

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
        # A node may be retried after it failed, and after a gate refused it.
        # Both are already legal BLOCKED/FAILED -> READY transitions, and a
        # mission stopped by Zgredek or the budget would otherwise have no way
        # back once the operator resolves the cause.
        retryable = {
            (MissionState.FAILED, NodeState.FAILED),
            (MissionState.BLOCKED, NodeState.BLOCKED),
        }
        if (mission["state"], node["state"]) not in retryable:
            raise ConflictError(
                "retry requires the selected node and mission to be FAILED or BLOCKED"
            )
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
        mission = self.store.get_mission(mission_id)
        if mission["state"] != MissionState.DRAFT:
            self.backend.cancel(mission_id)
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
        if mission["backend"] == OSA_EXECUTION_FORCE_BACKEND_ID:
            if not bundle.get("runtimeV2MissionId"):
                reasons.append("RuntimeV2 mission identity is missing")
            if not bundle.get("runtimeV2ExecutionId"):
                reasons.append("RuntimeV2 execution identity is missing")
            if not bundle.get("runtimeV2ResolvedSkills"):
                reasons.append("RuntimeV2 resolved capability is missing")
            if not bundle.get("runtimeV2EventChainVerified"):
                reasons.append("RuntimeV2 event chain is not verified")
            if len(bundle.get("mechanicalEvidenceIds", [])) < 2:
                reasons.append("RuntimeV2 mechanical evidence references are incomplete")

        # Canonical completion gates. Each is checked against what the bundle
        # actually recorded, so a mission cannot reach COMPLETED on a bundle that
        # merely exists.
        if not bundle.get("changedFiles"):
            reasons.append("no git diff recorded for this mission")
        rollback_plan = bundle.get("rollbackPlan") or {}
        if not rollback_plan.get("verified"):
            reasons.append("no verified rollback plan")
        for entry in bundle.get("acceptanceCriteria", []):
            if entry.get("status") in (CheckStatus.FAIL, CheckStatus.UNKNOWN):
                reasons.append(
                    f"acceptance criterion not verified: {entry.get('criterion', '')[:80]}"
                )
        for entry in bundle.get("requiredTests", []):
            if entry.get("status") in (CheckStatus.FAIL, CheckStatus.UNKNOWN):
                reasons.append(f"required test has no PASS result: {entry.get('test', '')[:80]}")
        if not any(node["node_id"] == "targeted-tests" for node in mission["nodes"]):
            reasons.append("blueprint has no test node")
        return {
            "available": True,
            "valid": not reasons,
            "invalidReasons": reasons,
            "eventChain": chain_detail,
            "bundle": bundle,
        }

    def backends(self) -> list[dict[str, Any]]:
        worker = next(
            item
            for item in describe_workers()
            if item["workerId"] == self.backend.backend_id
        )
        availability = getattr(self.backend, "availability", None)
        if callable(availability):
            live_status, live_reason = availability()
        else:
            live_status, live_reason = worker["availability"], worker["reason"]
        return [
            {
                "id": worker["workerId"],
                "name": worker["name"],
                "available": live_status == "AVAILABLE",
                "reason": live_reason,
                "isolated": (
                    "dedicated fixture workspace"
                    if self.backend.backend_id == BACKEND_ID
                    else "owned by OSA Execution Force RuntimeV2"
                ),
                "network": self.backend.backend_id == OSA_EXECUTION_FORCE_BACKEND_ID,
                "productionCredentials": False,
                "capabilities": worker["capabilities"],
            }
        ]

    # ------------------------------------------------------------------
    # Registries, budgets, queue, models, health
    # ------------------------------------------------------------------

    def seed_registries(self) -> None:
        """Declare the canonical surfaces once. Idempotent; safe on every boot."""
        self.store.upsert_project(
            key="michael-angelo",
            name="Michael Angelo",
            description="Coding missions: OpenHands, Codex, Claude workers, Minions",
            surface="MICHAEL_ANGELO",
            permission="GREEN",
        )
        self.store.upsert_project(
            key="genkit-lab",
            name="Genkit Lab",
            description="Eksperymenty AI i prototypy",
            surface="GENKIT_LAB",
            permission="YELLOW",
        )
        self.store.upsert_project(
            key="windows-rtx",
            name="Windows / RTX",
            description="Blender, modele, obraz, wideo, 3D",
            surface="WINDOWS",
            permission="YELLOW",
        )
        # Web3 Lab stays isolated from the standard execution plane. It is
        # registered so it is visible and governed, never so it can be executed
        # by a Michael Angelo worker.
        self.store.upsert_project(
            key="web3-lab",
            name="Web3 Lab",
            description="Odseparowany research, scraping, symulacje, paper trading",
            surface="WEB3_LAB",
            permission="RED",
        )
        self.store.upsert_repository(
            project_key="michael-angelo",
            slug="hydra-safe-demo",
            uri=SAFE_REPOSITORY,
            default_branch="main",
            executable=True,
            permission="GREEN",
        )
        self.store.upsert_repository(
            project_key="michael-angelo",
            slug="hydra-hermes-lab",
            uri="github://HazEOskA/hydra-hermes-lab",
            default_branch="main",
            executable=False,
            permission="RED",
        )
        bound_backend = self.backends()[0]
        for worker in describe_workers():
            if worker["workerId"] == bound_backend["id"]:
                worker = {
                    **worker,
                    "availability": (
                        "AVAILABLE" if bound_backend["available"] else "UNAVAILABLE"
                    ),
                    "reason": bound_backend["reason"],
                }
            self.store.upsert_worker(
                worker_id=worker["workerId"],
                name=worker["name"],
                kind=worker["kind"],
                availability=worker["availability"],
                reason=worker["reason"],
                capabilities=tuple(worker["capabilities"]),
                ephemeral=worker["ephemeral"],
            )
        for model_id, provider, role in MODEL_ROUTES:
            availability, reason = self._model_availability(provider)
            self.store.upsert_model(
                model_id=model_id,
                provider=provider,
                role=role,
                availability=availability,
                reason=reason,
            )
        if self.store.budget("global") is None:
            self.store.set_budget("global", 25.0)

    @staticmethod
    def _model_availability(provider: str) -> tuple[str, str]:
        """Model availability is read from the host, never assumed."""
        if provider == "local":
            # The deterministic route needs no credential; it is the worker itself.
            return "AVAILABLE", "worker deterministyczny, bez zewnętrznego dostawcy"
        env_var = MODEL_PROVIDER_ENV.get(provider)
        if not env_var:
            return "UNKNOWN", "brak zdefiniowanej sondy dostawcy"
        if os.environ.get(env_var):
            return "AVAILABLE", f"skonfigurowano {env_var}"
        return "UNAVAILABLE", f"brak {env_var}"

    def registry_snapshot(self) -> dict[str, Any]:
        return {
            "projects": self.store.projects(),
            "repositories": self.store.repositories(),
            "workers": describe_workers(),
            "models": self.store.models(),
        }

    def route_model(self, role: str) -> dict[str, Any]:
        """Pick the first AVAILABLE model for a role; otherwise report UNAVAILABLE."""
        candidates = [m for m in self.store.models() if m["role"] == role]
        for model in candidates:
            if model["availability"] == "AVAILABLE":
                return {"role": role, "selected": model["model_id"], "status": "AVAILABLE"}
        return {
            "role": role,
            "selected": None,
            "status": "UNAVAILABLE",
            "reason": "brak dostępnego modelu dla tej roli",
            "candidates": [m["model_id"] for m in candidates],
        }

    def health(self) -> dict[str, Any]:
        workers = describe_workers()
        missions = self.store.list_missions()
        queue = self.store.queue()
        budgets = self.store.budgets()
        degraded: list[str] = []
        if not any(w["availability"] == "AVAILABLE" for w in workers):
            degraded.append("brak dostępnego workera")
        for budget in budgets:
            if budget["remaining_amount"] <= 0:
                degraded.append(f"budżet '{budget['scope']}' wyczerpany")
        blocked = [m for m in missions if m["state"] == MissionState.BLOCKED]
        if blocked:
            degraded.append(f"{len(blocked)} misji w stanie BLOCKED")
        return {
            "status": "DEGRADED" if degraded else "OK",
            "issues": degraded,
            "schemaVersions": self.store.schema_versions(),
            "missions": {
                "total": len(missions),
                "active": sum(
                    1
                    for m in missions
                    if m["state"] not in {MissionState.COMPLETED, MissionState.CANCELLED}
                ),
                "completed": sum(1 for m in missions if m["state"] == MissionState.COMPLETED),
                "failed": sum(1 for m in missions if m["state"] == MissionState.FAILED),
            },
            "queue": {
                "waiting": sum(1 for e in queue if e["status"] == "WAITING"),
                "leased": sum(1 for e in queue if e["status"] == "LEASED"),
            },
            "workers": {
                "available": sum(1 for w in workers if w["availability"] == "AVAILABLE"),
                "unavailable": sum(1 for w in workers if w["availability"] == "UNAVAILABLE"),
            },
            "budgets": budgets,
            # Zgredek is the drift/context authority. The local deterministic
            # adapter is connected; the separate Zgredek product remains UNKNOWN.
            "zgredek": {
                "connected": True,
                "adapter": self.zgredek.adapter_id,
                "contextPacket": "ACTIVE",
                "driftDetection": "ACTIVE",
                "packets": len(
                    [m for m in missions if self.store.context_packet(m["mission_id"])]
                ),
                "reason": "lokalny deterministyczny adapter Zgredka; zewnętrzny produkt Zgredek pozostaje UNKNOWN",
            },
        }

    def _charge_node(self, mission_id: str, node_id: str, result: ExecutionResult) -> None:
        """Charge measured compute time against the mission's budget scope.

        The deterministic worker spends no model tokens, so billing it by token
        count would be fiction. What it genuinely consumes is wall-clock compute,
        which every CommandResult already records, so that is what the ledger
        charges. A model-backed worker would add its own token cost here.
        """
        seconds = 0.0
        for command in result.commands:
            try:
                started = datetime.fromisoformat(command.started_at.replace("Z", "+00:00"))
                finished = datetime.fromisoformat(command.finished_at.replace("Z", "+00:00"))
                seconds += max((finished - started).total_seconds(), 0.0)
            except (ValueError, AttributeError):
                continue
        if seconds <= 0:
            return
        amount = round(seconds * COMPUTE_RATE_PER_SECOND, 6)
        mission = self.store.get_mission(mission_id)
        scope = mission.get("manifest", {}).get("budget_scope", "global")
        try:
            self.store.charge_budget(
                scope, amount, mission_id=mission_id, reason=f"compute:{node_id}"
            )
        except (NotFoundError, ConflictError) as error:
            # A ledger problem must not corrupt mission state; it surfaces as a
            # log line and the pre-flight check blocks the next node.
            self.store.append_log(mission_id, node_id, "system", f"budget: {error}")

    def _budget_blocked(self, mission: dict[str, Any]) -> str:
        manifest = mission.get("manifest", {})
        scope = manifest.get("budget_scope", "global")
        budget = self.store.budget(scope)
        if budget and budget["remaining_amount"] <= 0:
            return f"budżet '{scope}' wyczerpany ({budget['spent_amount']:.4f}/{budget['limit_amount']:.4f})"
        limit = float(manifest.get("budget_limit", 0.0) or 0.0)
        if limit <= 0:
            return ""
        spent = sum(
            float(entry["amount"])
            for entry in self.store.budget_entries(scope)
            if entry["mission_id"] == mission["mission_id"]
        )
        if spent >= limit:
            return f"limit misji wyczerpany ({spent:.4f}/{limit:.4f})"
        return ""

    # ------------------------------------------------------------------
    # Zgredek context packet
    # ------------------------------------------------------------------

    def context_packet(self, mission_id: str) -> dict[str, Any]:
        """Packet, its validation verdict and its drift status for one mission."""
        mission = self.store.get_mission(mission_id)
        stored = self.store.context_packet(mission_id)
        base_branch = mission.get("manifest", {}).get("base_branch", "main")
        if stored is None:
            return {
                "available": False,
                "valid": False,
                "drift": {"status": "UNKNOWN", "findings": [], "reason": "brak packetu"},
                "invalidReasons": ["brak context packetu dla tej misji"],
                "missionId": mission_id,
            }
        packet = ContextPacket.from_dict(stored)
        reasons = self.zgredek.verify(
            packet,
            mission_id=mission_id,
            repository=mission["repository"],
            base_branch=base_branch,
        )
        # A drift verdict computed from an untrusted packet is worthless: the
        # recorded hashes it compares against are exactly what may have been
        # tampered with. An invalid packet therefore yields UNKNOWN drift, never
        # PASS, so the UI cannot show a reassuring verdict beside a refusal.
        drift = (
            self.zgredek.drift_report(packet)
            if not reasons
            else {
                "status": "UNKNOWN",
                "findings": [],
                "reason": "packet nieważny; werdykt driftu nieoznaczalny",
            }
        )
        approval_reasons = self.zgredek.approval_reasons(packet)
        return {
            "available": True,
            "valid": not reasons,
            "invalidReasons": reasons,
            "drift": drift,
            "approval": {
                "status": packet.status,
                "approved": not reasons and not approval_reasons,
                "reasons": approval_reasons,
                "approvedBy": packet.approved_by,
                "approvedAt": packet.approved_at,
                "approvedPacketSha256": packet.approved_packet_sha256,
            },
            "packet": stored,
        }

    def approve_context_packet(
        self, mission_id: str, *, actor: str, packet_sha256: str
    ) -> dict[str, Any]:
        """Accept a context packet for one exact content hash.

        Approving a missing, invalid or tampered packet is refused. Re-approving
        the identical hash is idempotent and appends no duplicate ledger entry.
        """
        self._validate_actor(actor)
        mission = self.store.get_mission(mission_id)
        stored = self.store.context_packet(mission_id)
        if stored is None:
            raise NotFoundError(f"brak context packetu dla misji: {mission_id}")

        blocked = self.zgredek.can_approve(actor)
        if blocked:
            raise AuthorizationError("; ".join(blocked))

        packet = ContextPacket.from_dict(stored)
        base_branch = mission.get("manifest", {}).get("base_branch", "main")
        invalid = self.zgredek.verify(
            packet,
            mission_id=mission_id,
            repository=mission["repository"],
            base_branch=base_branch,
        )
        if invalid:
            raise ConflictError(
                "nie można zatwierdzić nieważnego packetu: " + "; ".join(invalid)
            )
        if not isinstance(packet_sha256, str) or packet_sha256 != packet.sha256:
            raise ConflictError(
                "approval musi wskazywać dokładny SHA-256 bieżącego packetu"
            )

        if (
            packet.status == STATUS_APPROVED
            and packet.approved_packet_sha256 == packet.sha256
        ):
            return {
                "approved": True,
                "idempotent": True,
                "approvedBy": packet.approved_by,
                "approvedAt": packet.approved_at,
                "approvedPacketSha256": packet.approved_packet_sha256,
            }

        now = utc_now()
        approved = {
            **stored,
            "status": STATUS_APPROVED,
            "approvedBy": actor,
            "approvedAt": now,
            "approvedPacketSha256": packet.sha256,
        }
        self.store.save_context_packet(mission_id, approved)
        self.store.append_context_event(
            mission_id,
            event_type="CONTEXT_PACKET_APPROVED",
            actor=actor,
            verdict="APPROVED",
            message=f"context packet {packet.sha256[:12]} approved by {actor}",
        )
        return {
            "approved": True,
            "idempotent": False,
            "approvedBy": actor,
            "approvedAt": now,
            "approvedPacketSha256": packet.sha256,
        }

    def _refuse_without_context(self, mission: dict[str, Any]) -> str:
        """Return a refusal reason, or empty when the packet may be used.

        Drift is reported but does not by itself refuse: a changed lock is a
        finding for OSA, while a missing, tampered or mismatched packet is a
        hard stop. An UNKNOWN drift verdict is treated as a stop, because
        UNKNOWN never satisfies a gate.
        """
        report = self.context_packet(mission["mission_id"])
        verdict = "PASS"
        refusal = ""
        if not report["available"] or not report["valid"]:
            refusal = "; ".join(report["invalidReasons"]) or "context packet nieważny"
            verdict = "REFUSED"
        elif not report["approval"]["approved"]:
            # An unapproved packet is context nobody accepted. It refuses just
            # as hard as a tampered one.
            refusal = "; ".join(report["approval"]["reasons"]) or "brak zatwierdzenia packetu"
            verdict = "UNAPPROVED"
        elif report["drift"]["status"] == "UNKNOWN":
            refusal = f"drift nieoznaczalny: {report['drift'].get('reason', '')}"
            verdict = "UNKNOWN"
        else:
            verdict = report["drift"]["status"]

        self.store.append_context_event(
            mission["mission_id"],
            event_type="CONTEXT_PACKET_VALIDATED",
            actor=self.zgredek.adapter_id,
            verdict=verdict,
            message=(
                refusal
                if refusal
                else f"context packet valid; drift {report['drift']['status']}"
            ),
        )
        return refusal

    def pending_approvals(self) -> list[dict[str, Any]]:
        """Every mission parked on a gate, with the permission colour it needs."""
        payload = []
        for mission in self.store.list_missions():
            state = mission["state"]
            if state not in {
                MissionState.AWAITING_ARCHITECTURE_APPROVAL,
                MissionState.AWAITING_HUMAN_APPROVAL,
            }:
                continue
            gate = (
                "architecture"
                if state == MissionState.AWAITING_ARCHITECTURE_APPROVAL
                else "human"
            )
            payload.append(
                {
                    "missionId": mission["mission_id"],
                    "title": mission["title"],
                    "gate": gate,
                    "state": state,
                    "riskLevel": mission["risk_level"],
                    # RED gates block only themselves: other missions keep running.
                    "permission": "RED"
                    if mission["risk_level"] in (RiskLevel.HIGH, RiskLevel.CRITICAL)
                    else "YELLOW",
                }
            )
        return payload

    def mission_diff(self, mission_id: str) -> dict[str, Any]:
        """Return the recorded unified diff from the mission's evidence bundle."""
        bundle = self.store.evidence(mission_id)
        if bundle is None:
            return {"available": False, "reason": "brak evidence bundle dla tej misji"}
        return {
            "available": True,
            "baseCommit": bundle.get("baseCommit", ""),
            "resultCommit": bundle.get("resultCommit", ""),
            "changedFiles": bundle.get("changedFiles", []),
            "diffSummary": bundle.get("diffSummary", ""),
            "diff": bundle.get("gitDiff", ""),
        }

    def rollback_manifest(self, mission_id: str) -> dict[str, Any]:
        bundle = self.store.evidence(mission_id)
        if bundle is None:
            return {"available": False, "reason": "brak evidence bundle dla tej misji"}
        plan = bundle.get("rollbackPlan")
        if not plan:
            return {"available": False, "reason": "bundle nie zawiera planu rollback"}
        return {"available": True, "rollbackPlan": plan}

    def pull_request(self, mission_id: str) -> dict[str, Any]:
        """Local draft PR descriptor.

        This deliberately does not push a branch or call the GitHub API: the
        worker holds no production credentials and has no network. The descriptor
        is what a reviewer would open, reported as LOCAL_DESCRIPTOR so nobody
        mistakes it for an opened pull request.
        """
        mission = self.store.get_mission(mission_id)
        bundle = self.store.evidence(mission_id)
        if bundle is None:
            return {"available": False, "reason": "brak evidence bundle dla tej misji"}
        return {
            "available": True,
            "status": "LOCAL_DESCRIPTOR",
            "note": "Brak pushu i brak wywołania GitHub API; worker nie ma sieci ani credentiali.",
            "title": mission["title"],
            "sourceBranch": mission["branch"],
            "targetBranch": bundle.get("baseBranch", "main"),
            "repository": mission["repository"],
            "changedFiles": bundle.get("changedFiles", []),
            "diffSummary": bundle.get("diffSummary", ""),
            "riskLevel": mission["risk_level"],
            "reviewers": ["OSA"],
            "productionMerge": "RED",
        }

    def sandboxes(self) -> list[dict[str, Any]]:
        """One sandbox per mission, reported from what is actually on disk."""
        payload = []
        for mission in self.store.list_missions():
            workspace = self.store.workspace_root / mission["mission_id"]
            exists = workspace.is_dir()
            payload.append(
                {
                    "missionId": mission["mission_id"],
                    "title": mission["title"],
                    "state": mission["state"],
                    "worker": mission["backend"],
                    "exists": exists,
                    "path": str(workspace) if exists else "",
                    "isolated": True,
                    "network": False,
                    "productionCredentials": False,
                }
            )
        return payload

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
                # Zgredek's context packet gates fact loading. A missing,
                # invalid or mission-mismatched packet refuses execution before
                # the node ever starts, so the worker is demonstrably never
                # dispatched and the node's attempt counter stays untouched.
                if fresh["node_id"] == CONTEXT_GATED_NODE:
                    refusal = self._refuse_without_context(
                        self.store.get_mission(mission_id)
                    )
                    if refusal:
                        self.store.transition_node(
                            mission_id,
                            fresh["node_id"],
                            NodeState.BLOCKED,
                            actor="zgredek",
                            message="context packet refused",
                            summary=refusal[:500],
                            validation_result="UNKNOWN",
                        )
                        self.store.set_mission_state(
                            mission_id,
                            MissionState.BLOCKED,
                            actor="zgredek",
                            node_id=fresh["node_id"],
                            message="mission refused by Zgredek context validation",
                            failure_reason=refusal[:500],
                        )
                        return

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

                # Budget is checked before the node runs, not after. A mission
                # that would overrun its ceiling is blocked with its spend intact.
                over_budget = self._budget_blocked(current)
                if over_budget:
                    self.store.transition_node(
                        mission_id,
                        fresh["node_id"],
                        NodeState.BLOCKED,
                        actor="hydra-budget",
                        message="budget ceiling reached",
                        summary=over_budget,
                        validation_result="UNKNOWN",
                    )
                    self.store.set_mission_state(
                        mission_id,
                        MissionState.BLOCKED,
                        actor="hydra-budget",
                        node_id=fresh["node_id"],
                        message="mission paused by budget control",
                        failure_reason=over_budget[:500],
                    )
                    return

                backend_manifest = dict(current["manifest"])
                context_packet = self.store.context_packet(mission_id)
                if context_packet is not None:
                    backend_manifest["hydra_context"] = {
                        "packetSha256": context_packet.get("sha256", ""),
                        "status": context_packet.get("status", ""),
                        "approvedBy": context_packet.get("approvedBy", ""),
                        "approvedPacketSha256": context_packet.get(
                            "approvedPacketSha256", ""
                        ),
                    }
                result = self.backend.execute_task(
                    ExecuteTaskInput(
                        session_id=session.session_id,
                        mission_id=mission_id,
                        node_id=fresh["node_id"],
                        attempt=fresh["attempt"],
                        manifest=backend_manifest,
                        base_commit=current["base_commit"],
                        result_commit=current["result_commit"],
                    )
                )
                self._charge_node(mission_id, fresh["node_id"], result)
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
                elif result.metadata.get("hydraDisposition") == "BLOCKED":
                    detail = result.metadata.get("detail", result.summary)
                    self.store.transition_node(
                        mission_id,
                        fresh["node_id"],
                        NodeState.BLOCKED,
                        actor=self.backend.backend_id,
                        message=result.error_code or "execution authority blocked",
                        summary=redact(detail)[:500],
                        validation_result="UNKNOWN",
                        artifact_refs=artifact_refs,
                        command_result=command_summary,
                    )
                    self.store.set_mission_state(
                        mission_id,
                        MissionState.BLOCKED,
                        actor="hydra-orchestrator",
                        node_id=fresh["node_id"],
                        message="mission blocked by execution authority",
                        failure_reason=redact(detail)[:500],
                    )
                    return
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
        manifest = mission.get("manifest", {})
        changed_files = metadata.get("changedFiles", [])

        # Acceptance criteria are evidence, not decoration: each one is recorded
        # with the state that actually justified it. Criteria a deterministic
        # backend cannot mechanically verify stay UNKNOWN and are surfaced to the
        # human reviewer rather than being quietly asserted as met.
        acceptance = [
            {
                "criterion": criterion,
                "status": str(
                    CheckStatus.PASS
                    if node_states.get("independent-review") == NodeState.PASSED
                    else CheckStatus.UNKNOWN
                ),
                "verifiedBy": "independent-review",
            }
            for criterion in manifest.get("acceptance_criteria", [])
        ]
        required_tests = [
            {
                "test": name,
                "status": outcome("targeted-tests"),
                "verifiedBy": "targeted-tests",
            }
            for name in manifest.get("required_tests", [])
        ]

        # A mission may not complete without a concrete way back. The plan binds
        # to the exact commits so it stays actionable after the run.
        rollback_plan = {
            "strategy": (
                "governed-git-revert"
                if mission["backend"] == OSA_EXECUTION_FORCE_BACKEND_ID
                else "git-revert-to-base-commit"
            ),
            "baseCommit": mission["base_commit"],
            "resultCommit": mission["result_commit"],
            "branch": mission["branch"],
            "changedFiles": changed_files,
            "steps": (
                [
                    "Utwórz nową misję Hydry przypiętą do resultCommit.",
                    f"Zleć RuntimeV2 mechanicznie weryfikowany git revert {mission['result_commit']}.",
                    "Uruchom ten sam wymagany zestaw testów przez OSA Execution Force.",
                    "Zatwierdź nowy evidence bundle w standardowych bramkach Hydry.",
                ]
                if mission["backend"] == OSA_EXECUTION_FORCE_BACKEND_ID
                else [
                    "Zatrzymaj lokalny proces Hydry (control plane).",
                    f"W workspace misji wykonaj: git reset --hard {mission['base_commit']}",
                    f"Zweryfikuj, że HEAD == {mission['base_commit']}.",
                    "Usuń wyłącznie dedykowany katalog stanu tej misji.",
                    "Nie dotykaj współdzielonego state rootu Hermesa ani produkcji.",
                ]
            ),
            "productionImpact": False,
            "verified": bool(mission["base_commit"]) and bool(mission["result_commit"]),
        }

        bundle = {
            "schemaVersion": "1.1",
            "missionId": mission_id,
            "repository": mission["repository"],
            "baseBranch": manifest.get("base_branch", "main"),
            "baseCommit": mission["base_commit"],
            "resultCommit": mission["result_commit"],
            "branch": mission["branch"],
            "blueprint": manifest.get("blueprint", "standard-coding-mission"),
            "worker": mission["backend"],
            "executionWorker": metadata.get("worker", mission["backend"]),
            "runtimeV2MissionId": metadata.get("runtimeMissionId", ""),
            "runtimeV2ExecutionId": metadata.get("runtimeExecutionId", ""),
            "runtimeV2ResolvedSkills": metadata.get("resolvedSkills", []),
            "runtimeV2EventChainVerified": metadata.get("eventChainVerified", False),
            "mechanicalEvidenceIds": metadata.get("mechanicalEvidenceIds", []),
            "changedFiles": changed_files,
            "diffSummary": metadata.get("diffSummary", ""),
            "gitDiff": metadata.get("diff", ""),
            "commands": command_entries,
            "checks": checks,
            "acceptanceCriteria": acceptance,
            "requiredTests": required_tests,
            "artifacts": artifacts,
            "rollbackPlan": rollback_plan,
            "risks": [
                {
                    "level": mission["risk_level"],
                    "description": (
                        "controlled code modification governed by OSA Execution Force RuntimeV2"
                        if mission["backend"] == OSA_EXECUTION_FORCE_BACKEND_ID
                        else "controlled code modification in a fixture-only workspace"
                    ),
                    "productionImpact": False,
                }
            ],
            "generatedAt": utc_now(),
        }
        if metadata.get("currentCommit") != mission["result_commit"]:
            raise ConflictError("APR evidence cannot bind to a stale result commit")
        if any(value in (CheckStatus.FAIL, CheckStatus.UNKNOWN) for value in checks.values()):
            raise ConflictError("APR evidence contains a failed or unknown required check")
        if not rollback_plan["verified"]:
            raise ConflictError("APR evidence requires a commit-bound rollback plan")
        if not changed_files:
            raise ConflictError("APR evidence requires a recorded git diff")
        if mission["backend"] == OSA_EXECUTION_FORCE_BACKEND_ID and (
            not bundle["runtimeV2MissionId"]
            or not bundle["runtimeV2ExecutionId"]
            or not bundle["runtimeV2ResolvedSkills"]
            or not bundle["runtimeV2EventChainVerified"]
            or len(bundle["mechanicalEvidenceIds"]) < 2
        ):
            raise ConflictError("APR evidence requires complete RuntimeV2 proof identity")
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
    def _string_list(
        payload: dict[str, Any], key: str, max_items: int, max_length: int
    ) -> tuple[str, ...]:
        raw = payload.get(key, [])
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise ValidationError(f"{key} must be a list of strings")
        if len(raw) > max_items:
            raise ValidationError(f"{key} accepts at most {max_items} entries")
        values: list[str] = []
        for item in raw:
            if not isinstance(item, str) or not item.strip():
                raise ValidationError(f"{key} entries must be non-empty strings")
            text = item.strip()
            if len(text) > max_length:
                raise ValidationError(f"{key} entry exceeds {max_length} characters")
            if "\x00" in text:
                raise ValidationError(f"{key} entry contains a null byte")
            values.append(text)
        return tuple(values)

    @staticmethod
    def _bounded_int(
        payload: dict[str, Any], key: str, default: int, minimum: int, maximum: int
    ) -> int:
        value = payload.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(f"{key} must be an integer")
        if value < minimum or value > maximum:
            raise ValidationError(f"{key} must be between {minimum} and {maximum}")
        return value

    @staticmethod
    def _bounded_float(
        payload: dict[str, Any], key: str, default: float, minimum: float, maximum: float
    ) -> float:
        value = payload.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(f"{key} must be a number")
        value = float(value)
        if value < minimum or value > maximum:
            raise ValidationError(f"{key} must be between {minimum} and {maximum}")
        return value

    @staticmethod
    def _validate_actor(actor: str) -> None:
        if not isinstance(actor, str) or not ACTOR_PATTERN.fullmatch(actor):
            raise ValidationError("actor must be 1-80 safe display characters")
