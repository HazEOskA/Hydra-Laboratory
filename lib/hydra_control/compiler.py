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
    ) -> MissionManifest:
        nodes: list[PipelineNodeSpec] = []
        previous = ""
        for node_id, name in PIPELINE:
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
            risk_level=self._risk(request),
            execution_backend=backend,
            compiler=self.compiler_id,
            validation_requirements=(
                "format",
                "lint",
                "targeted-tests",
                "runtime-verification",
                "independent-review",
                "apr-commit-binding",
            ),
            execution_contract={
                "repositoryPolicy": "built-in-fixture-only",
                "workspacePolicy": "dedicated-root",
                "commands": "internal-allowlist-only",
                "productionCredentials": False,
                "network": False,
                "draftPullRequest": "local-descriptor-only",
            },
            nodes=tuple(nodes),
            failure_mode=failure_mode,
        )
