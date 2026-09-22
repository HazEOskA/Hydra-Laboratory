"""Minimal durable Hydra World kernel.

True-loop boundary:

    Hydra Laboratory (control) <-> Hydra World (observed state)

World records facts supplied by trusted internal probes/adapters. It never
approves, dispatches, executes, opens sockets, or reads production credentials.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
KERNEL_ID = "hydra-world-kernel-v0.1"
MAX_PAYLOAD_BYTES = 256 * 1024
MAX_RECENT_LIMIT = 500
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("world payload must be JSON-serializable") from error


def _observation_digest(
    *,
    source: str,
    kind: str,
    payload: dict[str, Any],
    recorded_at: float,
) -> str:
    body = {
        "source": source,
        "kind": kind,
        "payload": payload,
        "recordedAt": recorded_at,
    }
    return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorldObservation:
    """One immutable observed fact."""

    source: str
    kind: str
    payload: dict[str, Any]
    recorded_at: float
    sha256: str = ""

    def with_hash(self) -> "WorldObservation":
        digest = _observation_digest(
            source=self.source,
            kind=self.kind,
            payload=self.payload,
            recorded_at=self.recorded_at,
        )
        return WorldObservation(
            source=self.source,
            kind=self.kind,
            payload=self.payload,
            recorded_at=self.recorded_at,
            sha256=digest,
        )

    def hash_valid(self) -> bool:
        if not self.sha256:
            return False
        return self.sha256 == _observation_digest(
            source=self.source,
            kind=self.kind,
            payload=self.payload,
            recorded_at=self.recorded_at,
        )


@dataclass(frozen=True)
class WorldSnapshot:
    """Point-in-time world view returned to the control plane."""

    kernel_id: str
    schema_version: int
    observation_count: int
    last_observation_at: float | None
    health: dict[str, Any]
    sha256: str


class WorldKernel:
    """Tiny durable observed-state store with no execution authority."""

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "world.db"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS observations (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    source        TEXT NOT NULL,
                    kind          TEXT NOT NULL,
                    payload_json  TEXT NOT NULL,
                    recorded_at   REAL NOT NULL,
                    sha256        TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_world_obs_source
                    ON observations(source);
                CREATE INDEX IF NOT EXISTS idx_world_obs_kind
                    ON observations(kind);
                CREATE INDEX IF NOT EXISTS idx_world_obs_time
                    ON observations(recorded_at);
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
                ("kernel_id", KERNEL_ID),
            )
            schema_row = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            kernel_row = conn.execute(
                "SELECT value FROM meta WHERE key = 'kernel_id'"
            ).fetchone()
            if schema_row is None or int(schema_row["value"]) != SCHEMA_VERSION:
                raise RuntimeError("unsupported Hydra World schema version")
            if kernel_row is None or kernel_row["value"] != KERNEL_ID:
                raise RuntimeError("unexpected Hydra World kernel identity")

    @staticmethod
    def _validate_identifier(value: str, label: str) -> str:
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            raise ValueError(
                f"{label} must match {IDENTIFIER.pattern} and be <= 128 chars"
            )
        return value

    @classmethod
    def _validate_observation(cls, observation: WorldObservation) -> None:
        cls._validate_identifier(observation.source, "source")
        cls._validate_identifier(observation.kind, "kind")
        if not isinstance(observation.payload, dict):
            raise ValueError("payload must be a JSON object")
        if (
            isinstance(observation.recorded_at, bool)
            or not isinstance(observation.recorded_at, (int, float))
            or not math.isfinite(float(observation.recorded_at))
            or float(observation.recorded_at) < 0
        ):
            raise ValueError("recorded_at must be a finite non-negative unix timestamp")
        encoded = _canonical_json(observation.payload).encode("utf-8")
        if len(encoded) > MAX_PAYLOAD_BYTES:
            raise ValueError(
                f"payload exceeds {MAX_PAYLOAD_BYTES} byte Hydra World limit"
            )

    def record(self, observation: WorldObservation) -> WorldObservation:
        """Append one observation and return the exact hash-bound value stored."""

        self._validate_observation(observation)
        obs = observation.with_hash()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO observations(
                    source, kind, payload_json, recorded_at, sha256
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    obs.source,
                    obs.kind,
                    _canonical_json(obs.payload),
                    float(obs.recorded_at),
                    obs.sha256,
                ),
            )
        return obs

    def record_health(
        self,
        source: str,
        status: str,
        details: dict[str, Any] | None = None,
        *,
        recorded_at: float | None = None,
    ) -> WorldObservation:
        """Record one health observation without granting any control authority."""

        self._validate_identifier(status, "status")
        return self.record(
            WorldObservation(
                source=source,
                kind="health",
                payload={"status": status, "details": details or {}},
                recorded_at=time.time() if recorded_at is None else recorded_at,
            )
        )

    def snapshot(self) -> WorldSnapshot:
        """Return the current hash-bound world view."""

        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt, MAX(recorded_at) AS last FROM observations"
            ).fetchone()
            count = int(row["cnt"] or 0)
            last = row["last"]

            health: dict[str, Any] = {}
            rows = conn.execute(
                """
                SELECT source, payload_json, recorded_at, sha256
                FROM observations
                WHERE kind = 'health'
                ORDER BY recorded_at DESC, id DESC
                """
            ).fetchall()
            for item in rows:
                source = item["source"]
                if source in health:
                    continue
                payload = json.loads(item["payload_json"])
                observation = WorldObservation(
                    source=source,
                    kind="health",
                    payload=payload,
                    recorded_at=float(item["recorded_at"]),
                    sha256=item["sha256"],
                )
                if not observation.hash_valid():
                    raise ValueError("stored Hydra World health observation hash mismatch")
                health[source] = {
                    "payload": payload,
                    "recordedAt": observation.recorded_at,
                    "sha256": observation.sha256,
                }

        body = {
            "kernelId": KERNEL_ID,
            "schemaVersion": SCHEMA_VERSION,
            "observationCount": count,
            "lastObservationAt": last,
            "health": health,
        }
        digest = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
        return WorldSnapshot(
            kernel_id=KERNEL_ID,
            schema_version=SCHEMA_VERSION,
            observation_count=count,
            last_observation_at=last,
            health=health,
            sha256=digest,
        )

    def recent(
        self,
        *,
        limit: int = 50,
        source: str | None = None,
        kind: str | None = None,
    ) -> list[WorldObservation]:
        """Read newest observations with bounded, parameterized filters."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit must be an integer")
        if limit < 1 or limit > MAX_RECENT_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_RECENT_LIMIT}")

        clauses: list[str] = []
        params: list[Any] = []
        if source is not None:
            clauses.append("source = ?")
            params.append(self._validate_identifier(source, "source"))
        if kind is not None:
            clauses.append("kind = ?")
            params.append(self._validate_identifier(kind, "kind"))
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT source, kind, payload_json, recorded_at, sha256
                FROM observations
                {where}
                ORDER BY recorded_at DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        observations: list[WorldObservation] = []
        for row in rows:
            observation = WorldObservation(
                source=row["source"],
                kind=row["kind"],
                payload=json.loads(row["payload_json"]),
                recorded_at=float(row["recorded_at"]),
                sha256=row["sha256"],
            )
            if not observation.hash_valid():
                raise ValueError("stored Hydra World observation hash mismatch")
            observations.append(observation)
        return observations
