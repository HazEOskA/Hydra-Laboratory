"""Mission state machine and append-only evidence ledger.

Two guarantees this module exists to provide:

1. A mission cannot reach COMPLETED without passing through VALIDATING. "It ran"
   is not "it worked", and the state machine refuses to let anything skip the
   check.
2. The event log is hash-chained and append-only. Every event commits to its
   predecessor, so a record cannot be quietly rewritten after the fact — the
   chain check fails loudly instead.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

GENESIS_HASH = "0" * 64

STATES = (
    "CREATED",
    "INTAKE_VALIDATED",
    "PLANNED",
    "WAITING_FOR_APPROVAL",
    "QUEUED",
    "DISPATCHED",
    "RUNNING",
    "VALIDATING",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
    "CANCELLED",
    "ROLLED_BACK",
)

TERMINAL_STATES = frozenset({"COMPLETED", "CANCELLED", "ROLLED_BACK"})

# Allowed transitions. RUNNING -> COMPLETED is deliberately absent: validation is
# not optional, and this table is the thing that enforces it.
TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset({"INTAKE_VALIDATED", "FAILED", "CANCELLED", "BLOCKED"}),
    "INTAKE_VALIDATED": frozenset({"PLANNED", "FAILED", "CANCELLED", "BLOCKED"}),
    "PLANNED": frozenset({"WAITING_FOR_APPROVAL", "QUEUED", "FAILED", "CANCELLED", "BLOCKED"}),
    "WAITING_FOR_APPROVAL": frozenset({"QUEUED", "BLOCKED", "CANCELLED", "FAILED"}),
    "QUEUED": frozenset({"DISPATCHED", "CANCELLED", "BLOCKED", "FAILED"}),
    "DISPATCHED": frozenset({"RUNNING", "FAILED", "BLOCKED", "CANCELLED"}),
    "RUNNING": frozenset({"VALIDATING", "FAILED", "BLOCKED", "CANCELLED"}),
    "VALIDATING": frozenset({"COMPLETED", "FAILED", "BLOCKED", "ROLLED_BACK"}),
    "COMPLETED": frozenset({"ROLLED_BACK"}),
    "FAILED": frozenset({"QUEUED", "ROLLED_BACK", "CANCELLED", "BLOCKED"}),
    "BLOCKED": frozenset({"QUEUED", "CANCELLED", "FAILED"}),
    "CANCELLED": frozenset(),
    "ROLLED_BACK": frozenset(),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq                 INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id          TEXT NOT NULL,
    task_id             TEXT NOT NULL DEFAULT '',
    from_state          TEXT NOT NULL,
    to_state            TEXT NOT NULL,
    timestamp           TEXT NOT NULL,
    actor               TEXT NOT NULL,
    reason              TEXT NOT NULL,
    evidence_refs       TEXT NOT NULL,
    previous_event_hash TEXT NOT NULL,
    event_hash          TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS events_mission ON events (mission_id, seq);

CREATE TABLE IF NOT EXISTS missions (
    mission_id  TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    state       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Append-only enforcement at the storage layer, not just in application code.
CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'evidence ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'evidence ledger is append-only');
END;
"""


class TransitionError(ValueError):
    """Raised when a transition is not permitted by the state machine."""


class ChainError(RuntimeError):
    """Raised when the hash chain does not verify."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_hash(payload: dict[str, Any]) -> str:
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Event:
    seq: int
    mission_id: str
    task_id: str
    from_state: str
    to_state: str
    timestamp: str
    actor: str
    reason: str
    evidence_refs: list[str]
    previous_event_hash: str
    event_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "task_id": self.task_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "reason": self.reason,
            "evidence_refs": self.evidence_refs,
            "previous_event_hash": self.previous_event_hash,
            "event_hash": self.event_hash,
        }


def allowed(from_state: str, to_state: str) -> bool:
    if from_state not in TRANSITIONS or to_state not in STATES:
        return False
    return to_state in TRANSITIONS[from_state]


class Ledger:
    """SQLite-backed evidence ledger. Durable across restarts by construction."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- missions ---------------------------------------------------------

    def create_mission(self, mission_id: str, title: str = "", actor: str = "hermes") -> Event:
        now = utc_now()
        self.conn.execute(
            "INSERT INTO missions (mission_id, title, state, created_at, updated_at)"
            " VALUES (?, ?, 'CREATED', ?, ?)",
            (mission_id, title, now, now),
        )
        self.conn.commit()
        return self._append(mission_id, "", "", "CREATED", actor, "mission created", [])

    def mission_state(self, mission_id: str) -> str:
        row = self.conn.execute(
            "SELECT state FROM missions WHERE mission_id = ?", (mission_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown mission: {mission_id}")
        return row["state"]

    def transition(
        self,
        mission_id: str,
        to_state: str,
        *,
        actor: str = "hermes",
        reason: str = "",
        task_id: str = "",
        evidence_refs: list[str] | None = None,
    ) -> Event:
        from_state = self.mission_state(mission_id)
        if not allowed(from_state, to_state):
            raise TransitionError(
                f"{mission_id}: {from_state} -> {to_state} is not an allowed transition"
            )
        if to_state == "COMPLETED" and from_state != "VALIDATING":
            raise TransitionError("COMPLETED is reachable only from VALIDATING")
        refs = list(evidence_refs or [])
        if to_state == "COMPLETED" and not refs:
            raise TransitionError("COMPLETED requires at least one evidence reference")
        now = utc_now()
        event = self._append(mission_id, task_id, from_state, to_state, actor, reason, refs)
        self.conn.execute(
            "UPDATE missions SET state = ?, updated_at = ? WHERE mission_id = ?",
            (to_state, now, mission_id),
        )
        self.conn.commit()
        return event

    # -- events -----------------------------------------------------------

    def _head_hash(self) -> str:
        row = self.conn.execute(
            "SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return row["event_hash"] if row else GENESIS_HASH

    def _append(
        self,
        mission_id: str,
        task_id: str,
        from_state: str,
        to_state: str,
        actor: str,
        reason: str,
        evidence_refs: list[str],
    ) -> Event:
        previous = self._head_hash()
        record = {
            "mission_id": mission_id,
            "task_id": task_id,
            "from_state": from_state,
            "to_state": to_state,
            "timestamp": utc_now(),
            "actor": actor,
            "reason": reason,
            "evidence_refs": evidence_refs,
            "previous_event_hash": previous,
        }
        event_hash = compute_hash(record)
        cursor = self.conn.execute(
            "INSERT INTO events (mission_id, task_id, from_state, to_state, timestamp,"
            " actor, reason, evidence_refs, previous_event_hash, event_hash)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                mission_id,
                task_id,
                from_state,
                to_state,
                record["timestamp"],
                actor,
                reason,
                json.dumps(evidence_refs),
                previous,
                event_hash,
            ),
        )
        self.conn.commit()
        return Event(
            seq=int(cursor.lastrowid or 0),
            mission_id=mission_id,
            task_id=task_id,
            from_state=from_state,
            to_state=to_state,
            timestamp=str(record["timestamp"]),
            actor=actor,
            reason=reason,
            evidence_refs=evidence_refs,
            previous_event_hash=previous,
            event_hash=event_hash,
        )

    def record(
        self,
        mission_id: str,
        *,
        actor: str,
        reason: str,
        task_id: str = "",
        evidence_refs: list[str] | None = None,
        marker: str = "AUDIT",
    ) -> Event:
        """Append an audit entry (YELLOW actions, approvals) without moving state."""
        return self._append(
            mission_id, task_id, marker, marker, actor, reason, list(evidence_refs or [])
        )

    def events(self, mission_id: str | None = None) -> Iterator[Event]:
        if mission_id is None:
            rows = self.conn.execute("SELECT * FROM events ORDER BY seq")
        else:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE mission_id = ? ORDER BY seq", (mission_id,)
            )
        for row in rows:
            yield Event(
                seq=row["seq"],
                mission_id=row["mission_id"],
                task_id=row["task_id"],
                from_state=row["from_state"],
                to_state=row["to_state"],
                timestamp=row["timestamp"],
                actor=row["actor"],
                reason=row["reason"],
                evidence_refs=json.loads(row["evidence_refs"]),
                previous_event_hash=row["previous_event_hash"],
                event_hash=row["event_hash"],
            )

    def verify_chain(self) -> tuple[bool, str]:
        """Recompute every hash. Returns (ok, detail) rather than raising."""
        previous = GENESIS_HASH
        count = 0
        for event in self.events():
            if event.previous_event_hash != previous:
                return False, f"seq {event.seq}: previous hash mismatch"
            payload = event.to_dict()
            payload.pop("event_hash")
            if compute_hash(payload) != event.event_hash:
                return False, f"seq {event.seq}: event hash mismatch"
            previous = event.event_hash
            count += 1
        return True, f"chain verified over {count} events"
