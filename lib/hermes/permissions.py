"""Permission classifier for the Hermes trust plane.

Every executable tool call is classified GREEN / YELLOW / RED before dispatch.
The classifier is data-driven: `config/tools.yaml` supplies per-tool defaults and
per-action overrides, so the policy is reviewable in Git rather than buried in code.

Design rule taken from SOUL.md: security must prevent unauthorized actions without
turning routine diagnostics, builds, drafts and local commits into approval gates.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from enum import StrEnum
from typing import Any

from . import config as config_module


class PermissionLevel(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


ORDER = {PermissionLevel.GREEN: 0, PermissionLevel.YELLOW: 1, PermissionLevel.RED: 2}


def escalate(*levels: PermissionLevel) -> PermissionLevel:
    """The strictest level always wins. Nothing may de-escalate a RED signal."""
    return max(levels, key=lambda level: ORDER[level])


class UnknownToolError(KeyError):
    """Raised when a call names a tool absent from the registry."""


class ToolDisabledError(RuntimeError):
    """Raised when a call names a tool the registry marks disabled."""


@dataclass(frozen=True)
class Decision:
    tool: str
    action: str
    permission: PermissionLevel
    reason: str
    requires_approval: bool
    rollback_available: bool
    idempotency_key: str
    matched_rule: str
    audit_required: bool
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["permission"] = str(self.permission)
        return data


def idempotency_key(tool: str, action: str, payload: dict[str, Any] | None = None) -> str:
    """Stable key for duplicate suppression: same tool+action+payload, same key."""
    material = json.dumps(
        {"tool": tool, "action": action, "payload": payload or {}},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


class PermissionClassifier:
    """Classifies (tool, action, payload) triples against the tool registry."""

    def __init__(self, registry: dict[str, Any] | None = None) -> None:
        self.registry = registry if registry is not None else config_module.load_tools()
        self.tools: dict[str, Any] = self.registry.get("tools", {})
        self.red_patterns: list[dict[str, Any]] = self.registry.get("red_patterns", [])

    # -- registry helpers -------------------------------------------------

    def known_tools(self) -> list[str]:
        return sorted(self.tools)

    def enabled_tools(self) -> list[str]:
        return sorted(name for name, spec in self.tools.items() if spec.get("enabled", False))

    def tool_spec(self, tool: str) -> dict[str, Any]:
        try:
            return self.tools[tool]
        except KeyError as error:
            raise UnknownToolError(
                f"tool {tool!r} is not in the registry; known tools: {', '.join(self.known_tools())}"
            ) from error

    # -- classification ---------------------------------------------------

    def _default_level(self, tool: str, spec: dict[str, Any], action: str) -> tuple[PermissionLevel, str]:
        """Resolve the level before pattern escalation, most specific rule first."""
        actions = spec.get("actions", {}) or {}
        if action in actions:
            return PermissionLevel(actions[action]), f"tools.{tool}.actions.{action}"

        # Some tools split a verb into two levels, e.g. email draft vs send.
        for key, value in spec.items():
            if not key.endswith("_permission"):
                continue
            verb = key[: -len("_permission")]
            if verb and (action == verb or action.startswith(f"{verb}_") or action.endswith(f"_{verb}")):
                return PermissionLevel(value), f"tools.{tool}.{key}"

        if "permission_default" in spec:
            return PermissionLevel(spec["permission_default"]), f"tools.{tool}.permission_default"

        # A tool that declares only split verbs and no default is RED for
        # anything unrecognised: an unclassified action is never assumed safe.
        return PermissionLevel.RED, f"tools.{tool}.unclassified"

    def _pattern_escalation(
        self, tool: str, action: str, payload: dict[str, Any]
    ) -> tuple[PermissionLevel, str] | None:
        """SOUL.md's RED list, expressed as reviewable patterns over the call."""
        haystack = " ".join(
            [tool, action, json.dumps(payload, sort_keys=True, default=str)]
        ).lower()
        for rule in self.red_patterns:
            pattern = rule.get("pattern", "")
            if not pattern:
                continue
            scope = rule.get("tools")
            if scope and tool not in scope:
                continue
            if re.search(pattern, haystack):
                return PermissionLevel(rule.get("permission", "RED")), rule.get("id", pattern)
        return None

    def classify(
        self,
        tool: str,
        action: str,
        payload: dict[str, Any] | None = None,
        *,
        rollback_available: bool = False,
    ) -> Decision:
        payload = payload or {}
        spec = self.tool_spec(tool)

        if not spec.get("enabled", False):
            # A disabled tool is not silently downgraded; the call is refused so
            # nothing can report success against a tool that is switched off.
            raise ToolDisabledError(f"tool {tool!r} is disabled in the registry")

        level, rule = self._default_level(tool, spec, action)
        reason = f"registry rule {rule}"

        escalation = self._pattern_escalation(tool, action, payload)
        if escalation is not None:
            escalated_level, escalated_rule = escalation
            if ORDER[escalated_level] > ORDER[level]:
                level = escalated_level
                rule = escalated_rule
                reason = f"SOUL.md RED pattern {escalated_rule}"
            elif escalated_level == PermissionLevel.RED:
                rule = escalated_rule
                reason = f"SOUL.md RED pattern {escalated_rule}"

        if level is PermissionLevel.YELLOW and not rollback_available:
            reason += "; YELLOW requires a rollback path"

        return Decision(
            tool=tool,
            action=action,
            permission=level,
            reason=reason,
            requires_approval=level is PermissionLevel.RED,
            rollback_available=rollback_available,
            idempotency_key=idempotency_key(tool, action, payload),
            matched_rule=rule,
            audit_required=level in (PermissionLevel.YELLOW, PermissionLevel.RED),
        )


def dispatch_plan(decision: Decision) -> str:
    """What the dispatcher must do with a classified call.

    GREEN dispatches immediately. YELLOW checkpoints, audits, then dispatches.
    RED blocks only its own task — unrelated GREEN work keeps moving.
    """
    if decision.permission is PermissionLevel.GREEN:
        return "DISPATCH"
    if decision.permission is PermissionLevel.YELLOW:
        return "CHECKPOINT_AUDIT_DISPATCH"
    return "REQUEST_APPROVAL_BLOCK_TASK"
