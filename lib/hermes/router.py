"""Model router with capability-aware fallback.

Two rules drive this module:

- No task fails permanently because one provider is unavailable. The router walks
  preferred -> secondary -> local before giving up.
- A model is never silently substituted when it lacks a required capability. If
  nothing in the chain can do the job, the task is BLOCKED with the exact reason
  instead of being handed to a model that will produce plausible garbage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config as config_module

TASK_CLASSES = (
    "FAST_CLASSIFICATION",
    "CODE_GENERATION",
    "CODE_REVIEW",
    "DEEP_REASONING",
    "RESEARCH",
    "CONTENT",
    "VISION",
    "LONG_CONTEXT",
    "LOCAL_PRIVATE",
    "FALLBACK",
)

HEALTH_STATUSES = ("HEALTHY", "DEGRADED", "DOWN")


@dataclass
class ProviderHealth:
    provider: str
    model: str
    status: str = "HEALTHY"
    last_check: str = ""
    latency_ms: int = 0
    recent_failures: int = 0
    supported_capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "last_check": self.last_check,
            "latency_ms": self.latency_ms,
            "recent_failures": self.recent_failures,
            "supported_capabilities": self.supported_capabilities,
        }


@dataclass
class RoutingDecision:
    task_class: str
    selected: str | None
    provider: str | None
    status: str
    reason: str
    considered: list[str] = field(default_factory=list)
    rejected: dict[str, str] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return self.status == "BLOCKED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_class": self.task_class,
            "selected": self.selected,
            "provider": self.provider,
            "status": self.status,
            "reason": self.reason,
            "considered": self.considered,
            "rejected": self.rejected,
        }


class HealthTable:
    """Provider health, persisted as JSON so a restart does not lose the picture."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else config_module.state_dir() / "model-health.json"
        self.entries: dict[str, ProviderHealth] = {}
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return
        for key, value in raw.items():
            self.entries[key] = ProviderHealth(**value)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: entry.to_dict() for key, entry in self.entries.items()}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def set(self, entry: ProviderHealth) -> None:
        if entry.status not in HEALTH_STATUSES:
            raise ValueError(f"invalid status: {entry.status}")
        entry.last_check = entry.last_check or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.entries[entry.model] = entry

    def get(self, model: str) -> ProviderHealth | None:
        return self.entries.get(model)

    def status_of(self, model: str) -> str:
        entry = self.entries.get(model)
        return entry.status if entry else "DOWN"

    def as_list(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in sorted(self.entries.values(), key=lambda e: e.model)]


class ModelRouter:
    def __init__(
        self,
        catalog: dict[str, Any] | None = None,
        health: HealthTable | None = None,
    ) -> None:
        self.catalog = catalog if catalog is not None else config_module.load_models()
        self.models: dict[str, Any] = self.catalog.get("models", {})
        self.routes: dict[str, Any] = self.catalog.get("routes", {})
        self.health = health if health is not None else HealthTable()

    def _capabilities(self, model: str) -> set[str]:
        entry = self.health.get(model)
        if entry and entry.supported_capabilities:
            return set(entry.supported_capabilities)
        return set(self.models.get(model, {}).get("capabilities", []))

    def _context_window(self, model: str) -> int:
        return int(self.models.get(model, {}).get("context_window", 0))

    def chain_for(self, task_class: str) -> list[str]:
        if task_class not in TASK_CLASSES:
            raise ValueError(f"unknown task class: {task_class}")
        route = self.routes.get(task_class, {})
        chain = [route.get("preferred")] + list(route.get("fallback", []))
        local = route.get("local")
        if local:
            chain.append(local)
        return [model for model in chain if model]

    def select(
        self,
        task_class: str,
        *,
        required_capabilities: list[str] | None = None,
        context_tokens: int = 0,
        private: bool = False,
        exclude: list[str] | None = None,
    ) -> RoutingDecision:
        required = set(required_capabilities or [])
        excluded = set(exclude or [])
        chain = self.chain_for(task_class)
        considered: list[str] = []
        rejected: dict[str, str] = {}

        for model in chain:
            considered.append(model)
            spec = self.models.get(model)
            if spec is None:
                rejected[model] = "not in the model catalog"
                continue
            if model in excluded:
                rejected[model] = "excluded after a previous failure on this task"
                continue
            if private and not spec.get("local", False):
                rejected[model] = "task requires a local/private model"
                continue
            missing = required - self._capabilities(model)
            if missing:
                rejected[model] = f"missing capabilities: {', '.join(sorted(missing))}"
                continue
            window = self._context_window(model)
            if context_tokens and window and context_tokens > window:
                rejected[model] = f"context {context_tokens} exceeds window {window}"
                continue
            status = self.health.status_of(model)
            if status == "DOWN":
                rejected[model] = "provider health is DOWN"
                continue
            return RoutingDecision(
                task_class=task_class,
                selected=model,
                provider=spec.get("provider", "unknown"),
                status="DEGRADED" if status == "DEGRADED" else "ROUTED",
                reason=(
                    f"selected {model} for {task_class}"
                    + ("; provider is DEGRADED but usable" if status == "DEGRADED" else "")
                ),
                considered=considered,
                rejected=rejected,
            )

        return RoutingDecision(
            task_class=task_class,
            selected=None,
            provider=None,
            status="BLOCKED",
            reason=(
                f"no model in the {task_class} chain satisfies the requirements; "
                "task blocked rather than routed to an unsuitable model"
            ),
            considered=considered,
            rejected=rejected,
        )
