"""Durable task queue.

SQLite-backed so the queue survives a crash, a service restart and a VPS reboot
without a broker to operate. Everything the spec asks for is enforced here rather
than left to the caller: attempts and exponential backoff, a dead-letter queue,
idempotency, dependencies, cancellation, replay, worker heartbeats and stale-lease
recovery.

Default concurrency is 1. Raise it only after the safety tests still pass at the
higher value.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_MAX_ACTIVE_TASKS = int(os.environ.get("MAX_ACTIVE_TASKS", "1"))
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT_SECONDS = 900
BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 3600
HEARTBEAT_STALE_SECONDS = 300

STATUSES = (
    "QUEUED",
    "WAITING_FOR_APPROVAL",
    "DISPATCHED",
    "RUNNING",
    "VALIDATING",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
    "CANCELLED",
    "DEAD_LETTER",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id          TEXT PRIMARY KEY,
    mission_id       TEXT NOT NULL,
    type             TEXT NOT NULL,
    priority         INTEGER NOT NULL DEFAULT 50,
    permission       TEXT NOT NULL DEFAULT 'GREEN',
    status           TEXT NOT NULL DEFAULT 'QUEUED',
    payload          TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL,
    scheduled_at     TEXT NOT NULL,
    started_at       TEXT,
    finished_at      TEXT,
    attempt          INTEGER NOT NULL DEFAULT 0,
    max_attempts     INTEGER NOT NULL DEFAULT 3,
    timeout_seconds  INTEGER NOT NULL DEFAULT 900,
    idempotency_key  TEXT NOT NULL,
    depends_on       TEXT NOT NULL DEFAULT '[]',
    evidence_refs    TEXT NOT NULL DEFAULT '[]',
    last_error       TEXT,
    worker_id        TEXT,
    heartbeat_at     TEXT,
    lease_expires_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS tasks_idempotency
    ON tasks (idempotency_key)
    WHERE status NOT IN ('CANCELLED', 'DEAD_LETTER', 'FAILED');
CREATE INDEX IF NOT EXISTS tasks_ready ON tasks (status, priority, scheduled_at);
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def backoff_seconds(attempt: int) -> int:
    """Exponential backoff, capped so a poisoned task cannot schedule itself far out."""
    return min(BACKOFF_BASE_SECONDS * (2 ** max(0, attempt - 1)), BACKOFF_CAP_SECONDS)


class DuplicateTaskError(ValueError):
    """Raised when an idempotency key is already live in the queue."""


@dataclass
class Task:
    task_id: str
    mission_id: str
    type: str
    priority: int = 50
    permission: str = "GREEN"
    status: str = "QUEUED"
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    scheduled_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    attempt: int = 0
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    idempotency_key: str = ""
    depends_on: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "mission_id": self.mission_id,
            "type": self.type,
            "priority": self.priority,
            "permission": self.permission,
            "status": self.status,
            "payload": self.payload,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "timeout_seconds": self.timeout_seconds,
            "idempotency_key": self.idempotency_key,
            "depends_on": self.depends_on,
            "evidence_refs": self.evidence_refs,
            "last_error": self.last_error,
        }


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        task_id=row["task_id"],
        mission_id=row["mission_id"],
        type=row["type"],
        priority=row["priority"],
        permission=row["permission"],
        status=row["status"],
        payload=json.loads(row["payload"]),
        created_at=row["created_at"],
        scheduled_at=row["scheduled_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        attempt=row["attempt"],
        max_attempts=row["max_attempts"],
        timeout_seconds=row["timeout_seconds"],
        idempotency_key=row["idempotency_key"],
        depends_on=json.loads(row["depends_on"]),
        evidence_refs=json.loads(row["evidence_refs"]),
        last_error=row["last_error"],
    )


class TaskQueue:
    def __init__(self, path: str | Path, max_active: int | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_active = DEFAULT_MAX_ACTIVE_TASKS if max_active is None else max_active
        self.conn = sqlite3.connect(str(self.path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "TaskQueue":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- enqueue ----------------------------------------------------------

    def enqueue(
        self,
        task_id: str,
        mission_id: str,
        task_type: str,
        *,
        payload: dict[str, Any] | None = None,
        priority: int = 50,
        permission: str = "GREEN",
        idempotency_key: str = "",
        depends_on: list[str] | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        scheduled_at: datetime | None = None,
    ) -> Task:
        now = utc_now()
        status = "WAITING_FOR_APPROVAL" if permission == "RED" else "QUEUED"
        task = Task(
            task_id=task_id,
            mission_id=mission_id,
            type=task_type,
            priority=priority,
            permission=permission,
            status=status,
            payload=payload or {},
            created_at=iso(now),
            scheduled_at=iso(scheduled_at or now),
            idempotency_key=idempotency_key or task_id,
            depends_on=list(depends_on or []),
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
        )
        try:
            self.conn.execute(
                "INSERT INTO tasks (task_id, mission_id, type, priority, permission, status,"
                " payload, created_at, scheduled_at, attempt, max_attempts, timeout_seconds,"
                " idempotency_key, depends_on, evidence_refs)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, '[]')",
                (
                    task.task_id,
                    task.mission_id,
                    task.type,
                    task.priority,
                    task.permission,
                    task.status,
                    json.dumps(task.payload),
                    task.created_at,
                    task.scheduled_at,
                    task.max_attempts,
                    task.timeout_seconds,
                    task.idempotency_key,
                    json.dumps(task.depends_on),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateTaskError(
                f"a live task already holds idempotency key {task.idempotency_key!r}"
            ) from error
        return task

    # -- dispatch ---------------------------------------------------------

    def active_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE status IN ('DISPATCHED', 'RUNNING')"
        ).fetchone()
        return int(row["n"])

    def _dependencies_met(self, task: Task) -> bool:
        if not task.depends_on:
            return True
        placeholders = ",".join("?" for _ in task.depends_on)
        rows = self.conn.execute(
            f"SELECT status FROM tasks WHERE task_id IN ({placeholders})", task.depends_on
        ).fetchall()
        if len(rows) != len(task.depends_on):
            return False
        return all(row["status"] == "COMPLETED" for row in rows)

    def claim(self, worker_id: str) -> Task | None:
        """Lease the next ready task, or return None. Respects the concurrency cap."""
        self.recover_stale(worker_id)
        if self.active_count() >= self.max_active:
            return None
        now = utc_now()
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE status = 'QUEUED' AND scheduled_at <= ?"
            " ORDER BY priority ASC, scheduled_at ASC",
            (iso(now),),
        ).fetchall()
        for row in rows:
            task = _row_to_task(row)
            if not self._dependencies_met(task):
                continue
            lease_expiry = now + timedelta(seconds=task.timeout_seconds)
            cursor = self.conn.execute(
                "UPDATE tasks SET status = 'RUNNING', started_at = ?, attempt = attempt + 1,"
                " worker_id = ?, heartbeat_at = ?, lease_expires_at = ?"
                " WHERE task_id = ? AND status = 'QUEUED'",
                (iso(now), worker_id, iso(now), iso(lease_expiry), task.task_id),
            )
            if cursor.rowcount == 1:
                return self.get(task.task_id)
        return None

    def heartbeat(self, task_id: str, worker_id: str) -> None:
        now = utc_now()
        task = self.get(task_id)
        if task is None:
            return
        self.conn.execute(
            "UPDATE tasks SET heartbeat_at = ?, lease_expires_at = ?"
            " WHERE task_id = ? AND worker_id = ?",
            (iso(now), iso(now + timedelta(seconds=task.timeout_seconds)), task_id, worker_id),
        )

    def recover_stale(self, worker_id: str = "recovery") -> list[str]:
        """Requeue tasks whose worker died mid-flight.

        A crashed worker leaves RUNNING rows with an expired lease. They are
        returned to QUEUED with backoff rather than left to block the queue.
        """
        now = utc_now()
        stale = self.conn.execute(
            "SELECT * FROM tasks WHERE status = 'RUNNING'"
            " AND (lease_expires_at IS NULL OR lease_expires_at <= ?)",
            (iso(now),),
        ).fetchall()
        recovered: list[str] = []
        for row in stale:
            task = _row_to_task(row)
            heartbeat = parse(row["heartbeat_at"])
            if heartbeat and (now - heartbeat).total_seconds() < HEARTBEAT_STALE_SECONDS:
                continue
            recovered.append(task.task_id)
            self._retry_or_dead_letter(task, "worker lease expired; task recovered", now)
        return recovered

    # -- completion -------------------------------------------------------

    def start_validation(self, task_id: str) -> None:
        self.conn.execute(
            "UPDATE tasks SET status = 'VALIDATING' WHERE task_id = ? AND status = 'RUNNING'",
            (task_id,),
        )

    def complete(self, task_id: str, evidence_refs: list[str]) -> None:
        """Completion requires evidence; an empty list is refused."""
        if not evidence_refs:
            raise ValueError("completion requires at least one evidence reference")
        self.conn.execute(
            "UPDATE tasks SET status = 'COMPLETED', finished_at = ?, evidence_refs = ?,"
            " worker_id = NULL, lease_expires_at = NULL WHERE task_id = ?",
            (iso(utc_now()), json.dumps(evidence_refs), task_id),
        )

    def fail(self, task_id: str, error: str) -> Task | None:
        task = self.get(task_id)
        if task is None:
            return None
        self._retry_or_dead_letter(task, error, utc_now())
        return self.get(task_id)

    def _retry_or_dead_letter(self, task: Task, error: str, now: datetime) -> None:
        if task.attempt >= task.max_attempts:
            self.conn.execute(
                "UPDATE tasks SET status = 'DEAD_LETTER', finished_at = ?, last_error = ?,"
                " worker_id = NULL, lease_expires_at = NULL WHERE task_id = ?",
                (iso(now), error, task.task_id),
            )
            return
        retry_at = now + timedelta(seconds=backoff_seconds(task.attempt))
        self.conn.execute(
            "UPDATE tasks SET status = 'QUEUED', scheduled_at = ?, last_error = ?,"
            " started_at = NULL, worker_id = NULL, lease_expires_at = NULL WHERE task_id = ?",
            (iso(retry_at), error, task.task_id),
        )

    def block(self, task_id: str, reason: str) -> None:
        """Block one task without touching anything else in the queue."""
        self.conn.execute(
            "UPDATE tasks SET status = 'BLOCKED', last_error = ?, worker_id = NULL,"
            " lease_expires_at = NULL WHERE task_id = ?",
            (reason, task_id),
        )

    def approve(self, task_id: str, approver: str, expires_at: datetime | None = None) -> Task | None:
        """Release exactly one RED task. Scoped, expiring, never a blanket grant."""
        task = self.get(task_id)
        if task is None:
            return None
        if task.status not in ("WAITING_FOR_APPROVAL", "BLOCKED"):
            raise ValueError(f"task {task_id} is not awaiting approval (status {task.status})")
        if expires_at is not None and expires_at <= utc_now():
            raise ValueError("approval has already expired")
        payload = dict(task.payload)
        payload["approval"] = {
            "approver": approver,
            "granted_at": iso(utc_now()),
            "expires_at": iso(expires_at) if expires_at else None,
            "scope": {"task_id": task_id, "type": task.type},
        }
        self.conn.execute(
            "UPDATE tasks SET status = 'QUEUED', payload = ?, scheduled_at = ? WHERE task_id = ?",
            (json.dumps(payload), iso(utc_now()), task_id),
        )
        return self.get(task_id)

    def cancel(self, task_id: str, reason: str = "cancelled by operator") -> None:
        self.conn.execute(
            "UPDATE tasks SET status = 'CANCELLED', finished_at = ?, last_error = ?,"
            " worker_id = NULL, lease_expires_at = NULL WHERE task_id = ?",
            (iso(utc_now()), reason, task_id),
        )

    def replay(self, task_id: str, new_task_id: str) -> Task:
        """Re-run finished work as a new task; the original record is preserved."""
        task = self.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return self.enqueue(
            new_task_id,
            task.mission_id,
            task.type,
            payload=task.payload,
            priority=task.priority,
            permission=task.permission,
            idempotency_key=f"{task.idempotency_key}:replay:{new_task_id}",
            depends_on=task.depends_on,
            max_attempts=task.max_attempts,
            timeout_seconds=task.timeout_seconds,
        )

    # -- inspection -------------------------------------------------------

    def get(self, task_id: str) -> Task | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return _row_to_task(row) if row else None

    def list_tasks(self, status: str | None = None) -> list[Task]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY priority, created_at", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks ORDER BY priority, created_at"
            ).fetchall()
        return [_row_to_task(row) for row in rows]

    def dead_letters(self) -> list[Task]:
        return self.list_tasks("DEAD_LETTER")

    def stats(self) -> dict[str, int]:
        counts = {status: 0 for status in STATUSES}
        for row in self.conn.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"):
            counts[row["status"]] = int(row["n"])
        return counts

    def queue_lag_seconds(self) -> int:
        """Age of the oldest ready task — the metric that shows a stalled queue."""
        row = self.conn.execute(
            "SELECT MIN(scheduled_at) AS oldest FROM tasks WHERE status = 'QUEUED'"
        ).fetchone()
        oldest = parse(row["oldest"]) if row and row["oldest"] else None
        if oldest is None:
            return 0
        return max(0, int((utc_now() - oldest).total_seconds()))


def wait_for(predicate, timeout: float = 5.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False
