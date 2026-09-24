"""Hydra vertical slice: mission -> Michael Angelo -> worker -> evidence -> UI.

This module deliberately reuses the existing durable Ledger, TaskQueue and
PermissionClassifier. It does not execute arbitrary shell commands. Slice v1
runs one bounded GREEN control-plane inspection and produces a mechanically
verified evidence artifact.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from . import config as config_module
from .ledger import Ledger, utc_now
from .permissions import PermissionClassifier
from .queue import TaskQueue


class ControlPlaneService:
    """Small application service over the existing God-Layer primitives."""

    def __init__(self, state_root: str | Path | None = None) -> None:
        self.state_root = Path(state_root) if state_root else config_module.state_dir()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.state_root / "missions.db"
        self.queue_path = self.state_root / "queue.db"
        self.evidence_root = self.state_root / "evidence"
        self.evidence_root.mkdir(parents=True, exist_ok=True)

    def create_mission(self, title: str) -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("mission title is required")

        mission_id = "M-" + uuid.uuid4().hex[:8].upper()
        task_id = "T-" + uuid.uuid4().hex[:10].upper()
        payload = {
            "target": "hydra.control-plane",
            "mission_title": title,
            "operation": "bounded_read_only_inspection",
        }

        decision = PermissionClassifier().classify("shell", "inspect", payload)

        with Ledger(self.ledger_path) as ledger, TaskQueue(self.queue_path) as queue:
            ledger.create_mission(mission_id, title, actor="OSA")
            ledger.transition(
                mission_id,
                "INTAKE_VALIDATED",
                actor="UnderstandingGate",
                reason="Mission intake accepted for bounded vertical slice",
            )
            ledger.transition(
                mission_id,
                "PLANNED",
                actor="Michael Angelo",
                reason="Planned one read-only control-plane inspection task",
            )
            queue.enqueue(
                task_id,
                mission_id,
                "shell.inspect",
                payload=payload,
                permission=str(decision.permission),
                idempotency_key=decision.idempotency_key,
                timeout_seconds=120,
            )
            if decision.requires_approval:
                ledger.transition(
                    mission_id,
                    "WAITING_FOR_APPROVAL",
                    actor="Government",
                    reason=decision.reason,
                    task_id=task_id,
                )
            else:
                ledger.transition(
                    mission_id,
                    "QUEUED",
                    actor="Michael Angelo",
                    reason="GREEN task queued for Michael Angelo Work Cell",
                    task_id=task_id,
                )

        return {
            "mission_id": mission_id,
            "task_id": task_id,
            "permission": str(decision.permission),
            "snapshot": self.snapshot(),
        }

    def run_next(self) -> dict[str, Any]:
        with Ledger(self.ledger_path) as ledger, TaskQueue(self.queue_path) as queue:
            task = queue.claim("michael-angelo")
            if task is None:
                raise LookupError("no runnable GREEN/YELLOW task is queued")

            ledger.transition(
                task.mission_id,
                "DISPATCHED",
                actor="Michael Angelo",
                reason="Task leased to Michael Angelo Work Cell",
                task_id=task.task_id,
            )
            ledger.transition(
                task.mission_id,
                "RUNNING",
                actor="Michael Angelo",
                reason="Executing bounded control-plane inspection",
                task_id=task.task_id,
            )

            chain_ok, chain_detail = ledger.verify_chain()
            evidence_payload = {
                "schema": "hydra.vertical-slice.evidence.v1",
                "mission_id": task.mission_id,
                "task_id": task.task_id,
                "worker": "michael-angelo",
                "checked_at": utc_now(),
                "operation": task.payload.get("operation"),
                "target": task.payload.get("target"),
                "queue_stats": queue.stats(),
                "queue_lag_seconds": queue.queue_lag_seconds(),
                "ledger_chain": {"ok": chain_ok, "detail": chain_detail},
            }
            evidence_dir = self.evidence_root / task.mission_id
            evidence_dir.mkdir(parents=True, exist_ok=True)
            evidence_file = evidence_dir / (task.task_id + ".json")
            material = json.dumps(
                evidence_payload, indent=2, sort_keys=True, separators=(",", ": ")
            ).encode("utf-8")
            evidence_file.write_bytes(material)

            expected_sha = hashlib.sha256(material).hexdigest()
            actual_sha = hashlib.sha256(evidence_file.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                queue.fail(task.task_id, "evidence hash mismatch")
                ledger.transition(
                    task.mission_id,
                    "FAILED",
                    actor="Pinokio",
                    reason="Evidence artifact hash mismatch",
                    task_id=task.task_id,
                )
                raise RuntimeError("evidence verification failed")

            evidence_ref = (
                "evidence://control-plane/"
                + task.mission_id
                + "/"
                + task.task_id
                + ".json#sha256="
                + actual_sha
            )

            queue.start_validation(task.task_id)
            ledger.transition(
                task.mission_id,
                "VALIDATING",
                actor="Pinokio",
                reason="Evidence artifact present; SHA-256 verified mechanically",
                task_id=task.task_id,
                evidence_refs=[evidence_ref],
            )
            queue.complete(task.task_id, [evidence_ref])
            ledger.transition(
                task.mission_id,
                "COMPLETED",
                actor="Pinokio",
                reason="Vertical slice completed with mechanically verified evidence",
                task_id=task.task_id,
                evidence_refs=[evidence_ref],
            )

        return {
            "executed": {
                "mission_id": task.mission_id,
                "task_id": task.task_id,
                "worker": "michael-angelo",
                "verifier": "Pinokio",
                "evidence_ref": evidence_ref,
                "evidence_file": str(evidence_file),
                "sha256": actual_sha,
            },
            "snapshot": self.snapshot(),
        }

    def snapshot(self) -> dict[str, Any]:
        with Ledger(self.ledger_path) as ledger, TaskQueue(self.queue_path) as queue:
            mission_rows = ledger.conn.execute(
                "SELECT mission_id, title, state, created_at, updated_at "
                "FROM missions ORDER BY created_at DESC, mission_id DESC"
            ).fetchall()
            missions = [dict(row) for row in mission_rows]

            tasks = [task.to_dict() for task in queue.list_tasks()]
            worker_rows = queue.conn.execute(
                "SELECT task_id, mission_id, worker_id, heartbeat_at, status "
                "FROM tasks WHERE worker_id IS NOT NULL ORDER BY started_at DESC"
            ).fetchall()
            workers = [dict(row) for row in worker_rows]

            events = []
            for event in ledger.events():
                item = event.to_dict()
                item["seq"] = event.seq
                events.append(item)

            chain_ok, chain_detail = ledger.verify_chain()
            return {
                "mode": "LIVE_CONTROL_PLANE",
                "source_of_truth": {
                    "missions": str(self.ledger_path),
                    "queue": str(self.queue_path),
                    "evidence": str(self.evidence_root),
                },
                "missions": missions,
                "tasks": tasks,
                "workers": workers,
                "events": events,
                "queue_stats": queue.stats(),
                "queue_lag_seconds": queue.queue_lag_seconds(),
                "chain": {"ok": chain_ok, "detail": chain_detail},
            }
