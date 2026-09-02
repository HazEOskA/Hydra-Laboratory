"""Michael Angelo mission/blueprint contract and deterministic first adapter."""

from __future__ import annotations

import re
from typing import Protocol

from .models import MissionManifest, PipelineNodeSpec, RiskLevel


PIPELINE = (
    ("mission-intake", "Mission Intake"),
    ("repository-fact-load", "Repository Fact Load"),
    ("feasibility-analysis", "Feasibility Analysis"),
    ("implementation-plan", "Implementation Plan"),
    ("architecture-gate", "Architecture Gate"),
    ("sandbox-provisioning", "Sandbox Provisioning"),
    ("agent-execution", "Agent Execution"),
    ("quality-checks", "Formatting / Lint / Typecheck"),
    ("targeted-tests", "Targeted Tests"),
    ("runtime-verification", "Runtime Verification"),
    ("independent-review", "Independent Review"),
    ("apr-evidence", "APR Evidence Bundle"),
    ("human-approval", "Human Approval"),
    ("draft-pull-request", "Draft Pull Request"),
)

OSA_EXECUTION_FORCE_BACKEND_ID = "osa-execution-force"
OSA_EXECUTION_FORCE_PIPELINE = tuple(
    node for node in PIPELINE if node[0] != "sandbox-provisioning"
)


RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class MissionCompiler(Protocol):
    """Production boundary for Michael Angelo mission compilation."""

    compiler_id: str

    def compile(
        self,
        *,
        mission_id: str,
        title: str,
        request: str,
        repository: str,
        backend: str,
        failure_mode: str,
        base_branch: str = "main",
        acceptance_criteria: tuple[str, ...] = (),
        required_tests: tuple[str, ...] = (),
        budget_limit: float = 0.0,
        budget_scope: str = "global",
        requested_worker: str = "AUTO",
        timeout_seconds: int = 900,
        blueprint: str = "standard-coding-mission",
        risk_override: RiskLevel | None = None,
        base_commit: str = "",
        allowed_scope: tuple[str, ...] = (),
        test_command: tuple[str, ...] = (),
        environment: str = "development",
    ) -> MissionManifest: ...


class DeterministicMissionCompiler:
    """Local contract adapter used while the real Michael Angelo API is UNKNOWN."""

    compiler_id = "michael-angelo-local-contract-v1"

    @staticmethod
    def _risk(request: str) -> RiskLevel:
        text = request.lower()
        if re.search(r"\b(payment|money movement|delete production|rotate secret)\b", text):
            return RiskLevel.CRITICAL
        if re.search(
            r"\b(deploy|production|push|force[- ]?push|migration|infrastructure|auth|secret)\b",
            text,
        ):
            return RiskLevel.HIGH
        if re.search(r"\b(change|implement|build|write|fix|edit|code)\b", text):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def compile(
        self,
        *,
        mission_id: str,
        title: str,
        request: str,
        repository: str,
        backend: str,
        failure_mode: str,
        base_branch: str = "main",
        acceptance_criteria: tuple[str, ...] = (),
        required_tests: tuple[str, ...] = (),
        budget_limit: float = 0.0,
        budget_scope: str = "global",
        requested_worker: str = "AUTO",
        timeout_seconds: int = 900,
        blueprint: str = "standard-coding-mission",
        risk_override: RiskLevel | None = None,
        base_commit: str = "",
        allowed_scope: tuple[str, ...] = (),
        test_command: tuple[str, ...] = (),
        environment: str = "development",
    ) -> MissionManifest:
        nodes: list[PipelineNodeSpec] = []
        previous = ""
        pipeline = (
            OSA_EXECUTION_FORCE_PIPELINE
            if backend == OSA_EXECUTION_FORCE_BACKEND_ID
            else PIPELINE
        )
        for node_id, name in pipeline:
            dependencies = (previous,) if previous else ()
            nodes.append(
                PipelineNodeSpec(
                    node_id=node_id,
                    name=name,
                    dependencies=dependencies,
                    backend=backend,
                )
            )
            previous = node_id
        return MissionManifest(
            schema_version="1.0",
            mission_id=mission_id,
            title=title,
            request=request,
            repository=repository,
            branch=f"hydra/mission-{mission_id[:8]}",
            # An operator may raise the risk level but never lower what the
            # request text itself implies.
            risk_level=max(
                self._risk(request),
                risk_override or RiskLevel.LOW,
                key=lambda level: RISK_ORDER[level],
            ),
            execution_backend=backend,
            compiler=self.compiler_id,
            validation_requirements=(
                "format",
                "lint",
                "targeted-tests",
                "runtime-verification",
                "independent-review",
                "apr-commit-binding",
                "rollback-plan",
            ),
            execution_contract=(
                {
                    "authority": "OSA Execution Force RuntimeV2",
                    "transport": "official-api-v2",
                    "executionBypass": False,
                    "fallback": "forbidden",
                    "completion": "mechanically-verified-evidence-only",
                    "productionCredentials": False,
                }
                if backend == OSA_EXECUTION_FORCE_BACKEND_ID
                else {
                    "repositoryPolicy": "built-in-fixture-only",
                    "workspacePolicy": "dedicated-root",
                    "commands": "internal-allowlist-only",
                    "productionCredentials": False,
                    "network": False,
                    "draftPullRequest": "local-descriptor-only",
                }
            ),
            nodes=tuple(nodes),
            failure_mode=failure_mode,
            base_branch=base_branch,
            acceptance_criteria=tuple(acceptance_criteria),
            required_tests=tuple(required_tests),
            budget_limit=budget_limit,
            budget_scope=budget_scope,
            requested_worker=requested_worker,
            timeout_seconds=timeout_seconds,
            blueprint=blueprint,
            base_commit=base_commit,
            allowed_scope=tuple(allowed_scope),
            test_command=tuple(test_command),
            environment=environment,
        )
