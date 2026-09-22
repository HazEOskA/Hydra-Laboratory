"""Hydra Laboratory <-> Hydra World glue.

This adapter is intentionally narrow. It can record observations and read
snapshots/recent observations. It has no mission, approval, queue, dispatch,
execution, credential, or deployment methods.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from hydra_world import WorldKernel, WorldObservation


@runtime_checkable
class WorldPort(Protocol):
    """Observed-state port consumed by Hydra Laboratory."""

    def observe(
        self,
        *,
        source: str,
        kind: str,
        payload: dict[str, Any],
        recorded_at: float | None = None,
    ) -> dict[str, Any]: ...

    def snapshot(self) -> dict[str, Any]: ...

    def recent(
        self,
        *,
        limit: int = 50,
        source: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]: ...


class HydraWorldAdapter:
    """Local adapter that binds Laboratory to the separate World state root."""

    adapter_id = "hydra-world-local-adapter-v0.1"

    def __init__(self, state_root: str | Path) -> None:
        root = Path(state_root).resolve()
        self.world_root = root / "world"
        self.kernel = WorldKernel(self.world_root)

    @staticmethod
    def _observation_payload(observation: WorldObservation) -> dict[str, Any]:
        return {
            "source": observation.source,
            "kind": observation.kind,
            "payload": observation.payload,
            "recordedAt": observation.recorded_at,
            "sha256": observation.sha256,
        }

    def observe(
        self,
        *,
        source: str,
        kind: str,
        payload: dict[str, Any],
        recorded_at: float | None = None,
    ) -> dict[str, Any]:
        observation = self.kernel.record(
            WorldObservation(
                source=source,
                kind=kind,
                payload=payload,
                recorded_at=time.time() if recorded_at is None else recorded_at,
            )
        )
        return self._observation_payload(observation)

    def observe_health(
        self,
        *,
        source: str,
        status: str,
        details: dict[str, Any] | None = None,
        recorded_at: float | None = None,
    ) -> dict[str, Any]:
        observation = self.kernel.record_health(
            source,
            status,
            details,
            recorded_at=recorded_at,
        )
        return self._observation_payload(observation)

    def snapshot(self) -> dict[str, Any]:
        snapshot = self.kernel.snapshot()
        return {
            "adapter": self.adapter_id,
            "kernelId": snapshot.kernel_id,
            "schemaVersion": snapshot.schema_version,
            "observationCount": snapshot.observation_count,
            "lastObservationAt": snapshot.last_observation_at,
            "health": snapshot.health,
            "sha256": snapshot.sha256,
        }

    def recent(
        self,
        *,
        limit: int = 50,
        source: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            self._observation_payload(observation)
            for observation in self.kernel.recent(
                limit=limit,
                source=source,
                kind=kind,
            )
        ]
