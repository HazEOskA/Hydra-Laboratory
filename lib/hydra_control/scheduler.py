"""Durable-queue scheduler for the Hydra control plane.

The queue lives in SQLite, not in memory, so a restart never loses mission
intent. On boot the scheduler returns every LEASED entry to WAITING: a lease
that outlived its process was never completed, and re-running from a recorded
mission state is safe because every node transition is idempotent.

The scheduler decides *when* a mission runs. It never decides what a mission
does, and it never bypasses an approval gate.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from .models import MissionState


if TYPE_CHECKING:  # pragma: no cover - typing only
    from .service import MissionService


DEFAULT_INTERVAL_SECONDS = 1.0
# Concurrency is bounded so a burst of missions cannot exhaust the host. Each
# mission still runs in its own sandbox with its own timeout and cost ceiling.
DEFAULT_MAX_CONCURRENT = 2


class MissionScheduler:
    def __init__(
        self,
        service: "MissionService",
        *,
        interval: float = DEFAULT_INTERVAL_SECONDS,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ) -> None:
        self.service = service
        self.interval = interval
        self.max_concurrent = max_concurrent
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._active: set[str] = set()

    # -- lifecycle ----------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, name="hydra-scheduler", daemon=True
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def recover(self) -> list[str]:
        """Restart-recovery: reclaim leases orphaned by a stopped process."""
        return self.service.store.requeue_leased()

    # -- pump ---------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as error:  # the pump must survive a bad mission
                print(f"hydra-scheduler error: {type(error).__name__}: {error}")
            self._stop.wait(self.interval)

    def tick(self) -> int:
        """Lease and dispatch as many missions as the concurrency budget allows.

        Returns the number of missions dispatched in this tick.
        """
        dispatched = 0
        while True:
            with self._lock:
                if len(self._active) >= self.max_concurrent:
                    return dispatched
            entry = self.service.store.lease_next()
            if entry is None:
                return dispatched
            mission_id = entry["mission_id"]
            if not self._claim(mission_id):
                continue
            try:
                mission = self.service.store.get_mission(mission_id)
            except Exception as error:
                self.service.store.finish_queue_entry(
                    mission_id, "FAILED", f"mission unreadable: {error}"
                )
                self._release(mission_id)
                continue
            if mission["state"] != MissionState.DRAFT:
                # Anything already past DRAFT is driven by its own runner or is
                # parked on a gate; the queue has nothing left to do for it.
                self.service.store.finish_queue_entry(
                    mission_id, "DONE", f"already in state {mission['state']}"
                )
                self._release(mission_id)
                continue
            try:
                self.service.start(mission_id, actor="hydra-scheduler")
                dispatched += 1
            except Exception as error:
                self.service.store.finish_queue_entry(
                    mission_id, "FAILED", f"{type(error).__name__}: {error}"
                )
                self._release(mission_id)
                continue
            self._watch(mission_id)

    def _watch(self, mission_id: str) -> None:
        """Release the concurrency slot once the mission runner pauses."""

        def waiter() -> None:
            try:
                self.service.wait(mission_id, timeout=3600)
            except Exception:
                pass
            finally:
                try:
                    state = self.service.store.get_mission(mission_id)["state"]
                    self.service.store.finish_queue_entry(mission_id, "DONE", state)
                except Exception:
                    pass
                self._release(mission_id)

        threading.Thread(
            target=waiter, name=f"hydra-queue-{mission_id[:8]}", daemon=True
        ).start()

    def _claim(self, mission_id: str) -> bool:
        with self._lock:
            if mission_id in self._active:
                return False
            self._active.add(mission_id)
            return True

    def _release(self, mission_id: str) -> None:
        with self._lock:
            self._active.discard(mission_id)

    # -- observability ------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            active = sorted(self._active)
        entries = self.service.store.queue()
        return {
            "running": self.running,
            "intervalSeconds": self.interval,
            "maxConcurrent": self.max_concurrent,
            "activeMissions": active,
            "waiting": sum(1 for e in entries if e["status"] == "WAITING"),
            "leased": sum(1 for e in entries if e["status"] == "LEASED"),
            "done": sum(1 for e in entries if e["status"] == "DONE"),
            "failed": sum(1 for e in entries if e["status"] == "FAILED"),
        }
