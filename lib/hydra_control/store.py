"""SQLite persistence for Hydra missions, nodes, evidence and immutable events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    ConflictError,
    ExecutionArtifact,
    MissionManifest,
    MissionState,
    NodeState,
    NotFoundError,
)


GENESIS_HASH = "0" * 64

NODE_TRANSITIONS: dict[str, frozenset[str]] = {
    NodeState.PENDING: frozenset({NodeState.READY, NodeState.CANCELLED}),
    NodeState.READY: frozenset(
        {NodeState.RUNNING, NodeState.BLOCKED, NodeState.CANCELLED}
    ),
    NodeState.RUNNING: frozenset(
        {
            NodeState.PASSED,
            NodeState.FAILED,
            NodeState.BLOCKED,
            NodeState.CANCELLED,
            NodeState.UNKNOWN,
        }
    ),
    NodeState.FAILED: frozenset({NodeState.READY, NodeState.CANCELLED}),
    NodeState.BLOCKED: frozenset({NodeState.READY, NodeState.CANCELLED}),
    NodeState.UNKNOWN: frozenset({NodeState.READY, NodeState.CANCELLED}),
    NodeState.PASSED: frozenset(),
    NodeState.SKIPPED: frozenset(),
    NodeState.CANCELLED: frozenset(),
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS control_schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS control_missions (
    mission_id       TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    request          TEXT NOT NULL,
    repository       TEXT NOT NULL,
    branch           TEXT NOT NULL,
    risk_level       TEXT NOT NULL,
    backend          TEXT NOT NULL,
    compiler         TEXT NOT NULL,
    state            TEXT NOT NULL,
    current_node_id  TEXT NOT NULL DEFAULT '',
    manifest_json    TEXT NOT NULL,
    failure_mode     TEXT NOT NULL DEFAULT 'none',
    base_commit      TEXT NOT NULL DEFAULT '',
    result_commit    TEXT NOT NULL DEFAULT '',
    workspace_rel    TEXT NOT NULL DEFAULT '',
    failure_reason   TEXT NOT NULL DEFAULT '',
    final_outcome    TEXT NOT NULL DEFAULT '',
    token_usage      INTEGER,
    cost_amount      REAL,
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    finished_at      TEXT,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS control_pipeline_nodes (
    mission_id         TEXT NOT NULL,
    node_id            TEXT NOT NULL,
    ordinal            INTEGER NOT NULL,
    name               TEXT NOT NULL,
    state              TEXT NOT NULL,
    dependencies_json  TEXT NOT NULL,
    started_at         TEXT,
    finished_at        TEXT,
    attempt            INTEGER NOT NULL DEFAULT 0,
    backend            TEXT NOT NULL,
    summary            TEXT NOT NULL DEFAULT '',
    validation_result  TEXT NOT NULL DEFAULT 'UNKNOWN',
    PRIMARY KEY (mission_id, node_id),
    FOREIGN KEY (mission_id) REFERENCES control_missions(mission_id)
);
CREATE INDEX IF NOT EXISTS control_nodes_order
    ON control_pipeline_nodes (mission_id, ordinal);

CREATE TABLE IF NOT EXISTS control_events (
    seq                  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id             TEXT NOT NULL UNIQUE,
    mission_id           TEXT NOT NULL,
    node_id              TEXT NOT NULL DEFAULT '',
    event_type           TEXT NOT NULL,
    previous_state       TEXT NOT NULL,
    next_state           TEXT NOT NULL,
    timestamp            TEXT NOT NULL,
    actor                TEXT NOT NULL,
    backend              TEXT NOT NULL,
    message              TEXT NOT NULL DEFAULT '',
    artifact_refs_json   TEXT NOT NULL DEFAULT '[]',
    command_result_json  TEXT,
    commit_sha           TEXT,
    previous_event_hash  TEXT NOT NULL,
    event_hash           TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS control_events_mission
    ON control_events (mission_id, seq);

CREATE TRIGGER IF NOT EXISTS control_events_no_update
BEFORE UPDATE ON control_events
BEGIN
    SELECT RAISE(ABORT, 'control event ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS control_events_no_delete
BEFORE DELETE ON control_events
BEGIN
    SELECT RAISE(ABORT, 'control event ledger is append-only');
END;

CREATE TABLE IF NOT EXISTS control_logs (
    log_id       TEXT PRIMARY KEY,
    mission_id   TEXT NOT NULL,
    node_id      TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    stream       TEXT NOT NULL,
    message      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS control_logs_mission
    ON control_logs (mission_id, timestamp);

CREATE TABLE IF NOT EXISTS control_artifacts (
    artifact_id  TEXT PRIMARY KEY,
    mission_id   TEXT NOT NULL,
    node_id      TEXT NOT NULL,
    kind         TEXT NOT NULL,
    name         TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    size         INTEGER NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS control_artifacts_mission
    ON control_artifacts (mission_id, created_at);

CREATE TABLE IF NOT EXISTS control_approvals (
    approval_id  TEXT PRIMARY KEY,
    mission_id   TEXT NOT NULL,
    node_id      TEXT NOT NULL,
    gate         TEXT NOT NULL,
    actor        TEXT NOT NULL,
    decision     TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    UNIQUE (mission_id, gate)
);

CREATE TABLE IF NOT EXISTS control_command_results (
    command_id          TEXT PRIMARY KEY,
    mission_id          TEXT NOT NULL,
    node_id             TEXT NOT NULL,
    command_json        TEXT NOT NULL,
    display             TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    finished_at         TEXT NOT NULL,
    exit_code           INTEGER NOT NULL,
    stdout_artifact_id  TEXT NOT NULL,
    stderr_artifact_id  TEXT NOT NULL,
    timed_out           INTEGER NOT NULL DEFAULT 0,
    cancelled           INTEGER NOT NULL DEFAULT 0,
    commit_sha          TEXT
);
CREATE INDEX IF NOT EXISTS control_commands_mission
    ON control_command_results (mission_id, started_at);

CREATE TABLE IF NOT EXISTS control_evidence_bundles (
    mission_id      TEXT PRIMARY KEY,
    schema_version  TEXT NOT NULL,
    bundle_json     TEXT NOT NULL,
    result_commit   TEXT NOT NULL,
    generated_at    TEXT NOT NULL,
    valid_at_write  INTEGER NOT NULL
);
"""


# Schema v2 adds the canonical Hydra control-plane registries, the durable queue
# and the budget ledger. It is strictly additive: no v1 table is altered, so an
# existing missions.db keeps every legacy Hermes and control_* contract.
SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS control_projects (
    project_id   TEXT PRIMARY KEY,
    key          TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    surface      TEXT NOT NULL DEFAULT 'MICHAEL_ANGELO',
    permission   TEXT NOT NULL DEFAULT 'GREEN',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS control_repositories (
    repository_id  TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    slug           TEXT NOT NULL UNIQUE,
    uri            TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT 'main',
    executable     INTEGER NOT NULL DEFAULT 0,
    permission     TEXT NOT NULL DEFAULT 'GREEN',
    created_at     TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES control_projects(project_id)
);

CREATE TABLE IF NOT EXISTS control_workers (
    worker_id     TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL,
    availability  TEXT NOT NULL DEFAULT 'UNAVAILABLE',
    reason        TEXT NOT NULL DEFAULT '',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    ephemeral     INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS control_models (
    model_id      TEXT PRIMARY KEY,
    provider      TEXT NOT NULL,
    role          TEXT NOT NULL,
    availability  TEXT NOT NULL DEFAULT 'UNKNOWN',
    reason        TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS control_budgets (
    scope        TEXT PRIMARY KEY,
    limit_amount REAL NOT NULL,
    spent_amount REAL NOT NULL DEFAULT 0,
    currency     TEXT NOT NULL DEFAULT 'USD',
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS control_budget_entries (
    entry_id    TEXT PRIMARY KEY,
    scope       TEXT NOT NULL,
    mission_id  TEXT NOT NULL DEFAULT '',
    amount      REAL NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS control_budget_entries_scope
    ON control_budget_entries (scope, created_at);

CREATE TABLE IF NOT EXISTS control_queue (
    queue_id     TEXT PRIMARY KEY,
    mission_id   TEXT NOT NULL UNIQUE,
    priority     INTEGER NOT NULL DEFAULT 100,
    status       TEXT NOT NULL DEFAULT 'WAITING',
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT NOT NULL DEFAULT '',
    enqueued_at  TEXT NOT NULL,
    leased_at    TEXT,
    finished_at  TEXT
);
CREATE INDEX IF NOT EXISTS control_queue_ready
    ON control_queue (status, priority, enqueued_at);
"""


# Schema v3 stores the Zgredek context packet that a mission was approved
# against. Additive: no earlier table is touched.
SCHEMA_V3 = """
CREATE TABLE IF NOT EXISTS control_context_packets (
    mission_id      TEXT PRIMARY KEY,
    schema_version  TEXT NOT NULL,
    adapter         TEXT NOT NULL,
    packet_json     TEXT NOT NULL,
    packet_sha256   TEXT NOT NULL,
    repository      TEXT NOT NULL,
    base_branch     TEXT NOT NULL,
    approved_by     TEXT NOT NULL DEFAULT '',
    approved_at     TEXT,
    prepared_at     TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class ControlPlaneStore:
    """Thread-safe store using the existing mission SQLite database boundary."""

    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root).resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.workspace_root = self.state_root / "control-workspaces"
        self.artifact_root = self.state_root / "control-artifacts"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_root / "missions.db"
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO control_schema_migrations(version, applied_at) VALUES (1, ?)",
            (utc_now(),),
        )
        self.conn.executescript(SCHEMA_V2)
        self.conn.execute(
            "INSERT OR IGNORE INTO control_schema_migrations(version, applied_at) VALUES (2, ?)",
            (utc_now(),),
        )
        self.conn.executescript(SCHEMA_V3)
        self.conn.execute(
            "INSERT OR IGNORE INTO control_schema_migrations(version, applied_at) VALUES (3, ?)",
            (utc_now(),),
        )
        self.conn.commit()

    def schema_versions(self) -> list[int]:
        return [
            int(row["version"])
            for row in self.conn.execute(
                "SELECT version FROM control_schema_migrations ORDER BY version"
            ).fetchall()
        ]

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def _mission_row(self, mission_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM control_missions WHERE mission_id = ?", (mission_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"unknown mission: {mission_id}")
        return row

    def _node_row(self, mission_id: str, node_id: str) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM control_pipeline_nodes WHERE mission_id = ? AND node_id = ?",
            (mission_id, node_id),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"unknown node: {mission_id}/{node_id}")
        return row

    def create_mission(self, manifest: MissionManifest, actor: str) -> dict[str, Any]:
        now = utc_now()
        payload = manifest.to_dict()
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(
                    "INSERT INTO control_missions (mission_id, title, request, repository,"
                    " branch, risk_level, backend, compiler, state, manifest_json, failure_mode,"
                    " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        manifest.mission_id,
                        manifest.title,
                        manifest.request,
                        manifest.repository,
                        manifest.branch,
                        str(manifest.risk_level),
                        manifest.execution_backend,
                        manifest.compiler,
                        str(MissionState.DRAFT),
                        json.dumps(payload, sort_keys=True),
                        manifest.failure_mode,
                        now,
                        now,
                    ),
                )
                for ordinal, node in enumerate(manifest.nodes):
                    self.conn.execute(
                        "INSERT INTO control_pipeline_nodes (mission_id, node_id, ordinal, name,"
                        " state, dependencies_json, backend) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            manifest.mission_id,
                            node.node_id,
                            ordinal,
                            node.name,
                            str(NodeState.PENDING),
                            json.dumps(list(node.dependencies)),
                            node.backend,
                        ),
                    )
                self._append_event_locked(
                    mission_id=manifest.mission_id,
                    node_id="mission-intake",
                    event_type="MISSION_CREATED",
                    previous_state="",
                    next_state=str(MissionState.DRAFT),
                    actor=actor,
                    backend=manifest.execution_backend,
                    message="mission manifest compiled and stored",
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return self.get_mission(manifest.mission_id)

    def list_missions(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM control_missions ORDER BY created_at DESC"
            ).fetchall()
            return [self._mission_payload(row, include_details=False) for row in rows]

    def get_mission(self, mission_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._mission_row(mission_id)
            payload = self._mission_payload(row, include_details=True)
            payload["nodes"] = [
                self._node_payload(node)
                for node in self.conn.execute(
                    "SELECT * FROM control_pipeline_nodes WHERE mission_id = ? ORDER BY ordinal",
                    (mission_id,),
                ).fetchall()
            ]
            payload["approvals"] = [
                dict(item)
                for item in self.conn.execute(
                    "SELECT * FROM control_approvals WHERE mission_id = ? ORDER BY timestamp",
                    (mission_id,),
                ).fetchall()
            ]
            evidence = self.conn.execute(
                "SELECT schema_version, result_commit, generated_at, valid_at_write"
                " FROM control_evidence_bundles WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()
            payload["evidenceSummary"] = dict(evidence) if evidence else None
            return payload

    @staticmethod
    def _mission_payload(row: sqlite3.Row, *, include_details: bool) -> dict[str, Any]:
        keys = (
            "mission_id",
            "title",
            "repository",
            "branch",
            "risk_level",
            "backend",
            "compiler",
            "state",
            "current_node_id",
            "base_commit",
            "result_commit",
            "failure_reason",
            "final_outcome",
            "token_usage",
            "cost_amount",
            "created_at",
            "started_at",
            "finished_at",
            "updated_at",
        )
        payload = {key: row[key] for key in keys}
        if include_details:
            payload["request"] = row["request"]
            payload["failureMode"] = row["failure_mode"]
            payload["manifest"] = json.loads(row["manifest_json"])
            payload["workspace"] = row["workspace_rel"] or None
        return payload

    @staticmethod
    def _node_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "mission_id": row["mission_id"],
            "node_id": row["node_id"],
            "ordinal": row["ordinal"],
            "name": row["name"],
            "state": row["state"],
            "dependencies": json.loads(row["dependencies_json"]),
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "attempt": row["attempt"],
            "backend": row["backend"],
            "summary": row["summary"],
            "validation_result": row["validation_result"],
        }

    def set_mission_state(
        self,
        mission_id: str,
        state: MissionState | str,
        *,
        actor: str,
        node_id: str = "",
        message: str = "",
        failure_reason: str = "",
        final_outcome: str = "",
        commit_sha: str = "",
    ) -> None:
        next_state = str(state)
        with self._lock:
            row = self._mission_row(mission_id)
            previous = row["state"]
            if previous == next_state and not message:
                return
            now = utc_now()
            started_at = row["started_at"] or (
                now if next_state != MissionState.DRAFT else None
            )
            finished_at = (
                now
                if next_state
                in (MissionState.COMPLETED, MissionState.CANCELLED, MissionState.FAILED)
                else row["finished_at"]
            )
            self.conn.execute(
                "UPDATE control_missions SET state = ?, current_node_id = ?, failure_reason = ?,"
                " final_outcome = ?, started_at = ?, finished_at = ?, updated_at = ?"
                " WHERE mission_id = ?",
                (
                    next_state,
                    node_id,
                    failure_reason,
                    final_outcome,
                    started_at,
                    finished_at,
                    now,
                    mission_id,
                ),
            )
            self._append_event_locked(
                mission_id=mission_id,
                node_id=node_id,
                event_type="MISSION_STATE_CHANGED",
                previous_state=previous,
                next_state=next_state,
                actor=actor,
                backend=row["backend"],
                message=message,
                commit_sha=commit_sha,
            )
            self.conn.commit()

    def transition_node(
        self,
        mission_id: str,
        node_id: str,
        state: NodeState | str,
        *,
        actor: str,
        message: str = "",
        summary: str = "",
        validation_result: str = "UNKNOWN",
        artifact_refs: list[str] | None = None,
        command_result: dict[str, Any] | None = None,
        commit_sha: str = "",
    ) -> dict[str, Any]:
        next_state = str(state)
        with self._lock:
            row = self._node_row(mission_id, node_id)
            previous = row["state"]
            if next_state != previous and next_state not in NODE_TRANSITIONS[previous]:
                raise ConflictError(
                    f"invalid node transition {mission_id}/{node_id}: {previous} -> {next_state}"
                )
            now = utc_now()
            started_at = now if next_state == NodeState.RUNNING else row["started_at"]
            finished_at = (
                now
                if next_state
                in (
                    NodeState.PASSED,
                    NodeState.FAILED,
                    NodeState.BLOCKED,
                    NodeState.SKIPPED,
                    NodeState.CANCELLED,
                    NodeState.UNKNOWN,
                )
                else (None if next_state == NodeState.READY else row["finished_at"])
            )
            attempt = row["attempt"] + (1 if next_state == NodeState.RUNNING else 0)
            self.conn.execute(
                "UPDATE control_pipeline_nodes SET state = ?, started_at = ?, finished_at = ?,"
                " attempt = ?, summary = ?, validation_result = ?"
                " WHERE mission_id = ? AND node_id = ?",
                (
                    next_state,
                    started_at,
                    finished_at,
                    attempt,
                    summary or row["summary"],
                    validation_result,
                    mission_id,
                    node_id,
                ),
            )
            self._append_event_locked(
                mission_id=mission_id,
                node_id=node_id,
                event_type="NODE_STATE_CHANGED",
                previous_state=previous,
                next_state=next_state,
                actor=actor,
                backend=row["backend"],
                message=message,
                artifact_refs=artifact_refs,
                command_result=command_result,
                commit_sha=commit_sha,
            )
            self.conn.commit()
            return self._node_payload(self._node_row(mission_id, node_id))

    def set_commits(
        self,
        mission_id: str,
        *,
        base_commit: str | None = None,
        result_commit: str | None = None,
        workspace: Path | None = None,
    ) -> None:
        with self._lock:
            row = self._mission_row(mission_id)
            relative = row["workspace_rel"]
            if workspace is not None:
                relative = str(self._relative_to_state(workspace))
            self.conn.execute(
                "UPDATE control_missions SET base_commit = ?, result_commit = ?, workspace_rel = ?,"
                " updated_at = ? WHERE mission_id = ?",
                (
                    base_commit if base_commit is not None else row["base_commit"],
                    result_commit if result_commit is not None else row["result_commit"],
                    relative,
                    utc_now(),
                    mission_id,
                ),
            )
            self.conn.commit()

    def append_log(self, mission_id: str, node_id: str, stream: str, message: str) -> str:
        log_id = str(uuid.uuid4())
        with self._lock:
            self.conn.execute(
                "INSERT INTO control_logs VALUES (?, ?, ?, ?, ?, ?)",
                (log_id, mission_id, node_id, utc_now(), stream, message),
            )
            self.conn.commit()
        return log_id

    def logs(self, mission_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._mission_row(mission_id)
            return [
                dict(row)
                for row in self.conn.execute(
                    "SELECT * FROM control_logs WHERE mission_id = ? ORDER BY timestamp, rowid",
                    (mission_id,),
                ).fetchall()
            ]

    def register_artifact(self, artifact: ExecutionArtifact) -> dict[str, Any]:
        relative = self._relative_to_state(artifact.path)
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO control_artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact.artifact_id,
                    artifact.mission_id,
                    artifact.node_id,
                    artifact.kind,
                    artifact.name,
                    str(relative),
                    artifact.sha256,
                    artifact.size,
                    utc_now(),
                ),
            )
            self.conn.commit()
        return self.artifact(artifact.artifact_id)

    def artifact(self, artifact_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM control_artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"unknown artifact: {artifact_id}")
            return dict(row)

    def artifacts(self, mission_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._mission_row(mission_id)
            return [
                dict(row)
                for row in self.conn.execute(
                    "SELECT * FROM control_artifacts WHERE mission_id = ? ORDER BY created_at",
                    (mission_id,),
                ).fetchall()
            ]

    def read_artifact(self, artifact_id: str) -> bytes:
        record = self.artifact(artifact_id)
        path = self._state_path(record["relative_path"], must_exist=True)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ConflictError(f"artifact hash mismatch: {artifact_id}")
        return data

    def record_command(
        self,
        *,
        command_id: str,
        mission_id: str,
        node_id: str,
        command: list[str],
        display: str,
        started_at: str,
        finished_at: str,
        exit_code: int,
        stdout_artifact_id: str,
        stderr_artifact_id: str,
        timed_out: bool,
        cancelled: bool,
        commit_sha: str,
    ) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO control_command_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    command_id,
                    mission_id,
                    node_id,
                    json.dumps(command),
                    display,
                    started_at,
                    finished_at,
                    exit_code,
                    stdout_artifact_id,
                    stderr_artifact_id,
                    int(timed_out),
                    int(cancelled),
                    commit_sha or None,
                ),
            )
            self.conn.commit()

    def commands(self, mission_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    **dict(row),
                    "command": json.loads(row["command_json"]),
                    "timed_out": bool(row["timed_out"]),
                    "cancelled": bool(row["cancelled"]),
                }
                for row in self.conn.execute(
                    "SELECT * FROM control_command_results WHERE mission_id = ?"
                    " ORDER BY started_at, rowid",
                    (mission_id,),
                ).fetchall()
            ]

    def approve(
        self, mission_id: str, node_id: str, gate: str, actor: str
    ) -> dict[str, Any]:
        approval_id = str(uuid.uuid4())
        now = utc_now()
        with self._lock:
            mission = self._mission_row(mission_id)
            try:
                self.conn.execute(
                    "INSERT INTO control_approvals VALUES (?, ?, ?, ?, ?, 'APPROVED', ?)",
                    (approval_id, mission_id, node_id, gate, actor, now),
                )
            except sqlite3.IntegrityError as error:
                raise ConflictError(f"gate already approved: {gate}") from error
            self._append_event_locked(
                mission_id=mission_id,
                node_id=node_id,
                event_type="APPROVAL_RECORDED",
                previous_state="BLOCKED",
                next_state="APPROVED",
                actor=actor,
                backend=mission["backend"],
                message=f"{gate} approval recorded",
            )
            self.conn.commit()
            return {
                "approval_id": approval_id,
                "mission_id": mission_id,
                "node_id": node_id,
                "gate": gate,
                "actor": actor,
                "decision": "APPROVED",
                "timestamp": now,
            }

    def has_approval(self, mission_id: str, gate: str) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM control_approvals WHERE mission_id = ? AND gate = ?",
                (mission_id, gate),
            ).fetchone()
            return row is not None

    def save_evidence(self, mission_id: str, bundle: dict[str, Any]) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO control_evidence_bundles VALUES (?, ?, ?, ?, ?, 1)",
                (
                    mission_id,
                    bundle["schemaVersion"],
                    json.dumps(bundle, indent=2, sort_keys=True),
                    bundle["resultCommit"],
                    bundle["generatedAt"],
                ),
            )
            self.conn.commit()

    def evidence(self, mission_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM control_evidence_bundles WHERE mission_id = ?", (mission_id,)
            ).fetchone()
            return json.loads(row["bundle_json"]) if row else None

    def events(self, mission_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._mission_row(mission_id)
            result = []
            for row in self.conn.execute(
                "SELECT * FROM control_events WHERE mission_id = ? ORDER BY seq",
                (mission_id,),
            ).fetchall():
                item = dict(row)
                item["artifact_refs"] = json.loads(item.pop("artifact_refs_json"))
                command_result_json = item.pop("command_result_json")
                item["command_result"] = (
                    json.loads(command_result_json) if command_result_json else None
                )
                result.append(item)
            return result

    def verify_event_chain(self, mission_id: str) -> tuple[bool, str]:
        previous = GENESIS_HASH
        count = 0
        for event in self.events(mission_id):
            event_hash = event.pop("event_hash")
            event.pop("seq")
            if event["previous_event_hash"] != previous:
                return False, f"event {event['event_id']}: previous hash mismatch"
            if _digest(event) != event_hash:
                return False, f"event {event['event_id']}: hash mismatch"
            previous = event_hash
            count += 1
        return True, f"chain verified over {count} events"

    def verify_artifacts(self, mission_id: str) -> tuple[bool, list[str]]:
        problems: list[str] = []
        for record in self.artifacts(mission_id):
            try:
                path = self._state_path(record["relative_path"], must_exist=True)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != record["sha256"]:
                    problems.append(f"{record['artifact_id']}: hash mismatch")
            except (FileNotFoundError, ConflictError):
                problems.append(f"{record['artifact_id']}: missing or outside artifact root")
        return not problems, problems

    def cancel_mission(self, mission_id: str, actor: str, reason: str) -> None:
        with self._lock:
            mission = self._mission_row(mission_id)
            if mission["state"] in (MissionState.COMPLETED, MissionState.CANCELLED):
                raise ConflictError(f"mission cannot be cancelled from {mission['state']}")
            rows = self.conn.execute(
                "SELECT * FROM control_pipeline_nodes WHERE mission_id = ? ORDER BY ordinal",
                (mission_id,),
            ).fetchall()
            for row in rows:
                if row["state"] in (
                    NodeState.PENDING,
                    NodeState.READY,
                    NodeState.RUNNING,
                    NodeState.BLOCKED,
                    NodeState.FAILED,
                    NodeState.UNKNOWN,
                ):
                    self.conn.execute(
                        "UPDATE control_pipeline_nodes SET state = ?, finished_at = ?, summary = ?"
                        " WHERE mission_id = ? AND node_id = ?",
                        (NodeState.CANCELLED, utc_now(), reason, mission_id, row["node_id"]),
                    )
                    self._append_event_locked(
                        mission_id=mission_id,
                        node_id=row["node_id"],
                        event_type="NODE_STATE_CHANGED",
                        previous_state=row["state"],
                        next_state=str(NodeState.CANCELLED),
                        actor=actor,
                        backend=row["backend"],
                        message=reason,
                    )
            self.conn.execute(
                "UPDATE control_missions SET state = ?, failure_reason = ?, finished_at = ?,"
                " updated_at = ? WHERE mission_id = ?",
                (MissionState.CANCELLED, reason, utc_now(), utc_now(), mission_id),
            )
            self._append_event_locked(
                mission_id=mission_id,
                node_id=mission["current_node_id"],
                event_type="MISSION_CANCELLED",
                previous_state=mission["state"],
                next_state=str(MissionState.CANCELLED),
                actor=actor,
                backend=mission["backend"],
                message=reason,
            )
            self.conn.commit()

    def recover_interrupted(self, actor: str = "hydra-recovery") -> list[str]:
        recoverable = (
            MissionState.QUEUED,
            MissionState.FACT_LOADING,
            MissionState.PLANNING,
            MissionState.PROVISIONING,
            MissionState.RUNNING,
            MissionState.VALIDATING,
            MissionState.REVIEWING,
            MissionState.BUILDING_EVIDENCE,
            MissionState.PR_READY,
        )
        recovered: list[str] = []
        with self._lock:
            rows = self.conn.execute(
                f"SELECT * FROM control_missions WHERE state IN ({','.join('?' for _ in recoverable)})",
                tuple(str(state) for state in recoverable),
            ).fetchall()
            for mission in rows:
                running = self.conn.execute(
                    "SELECT * FROM control_pipeline_nodes WHERE mission_id = ? AND state = ?",
                    (mission["mission_id"], NodeState.RUNNING),
                ).fetchall()
                for node in running:
                    self.conn.execute(
                        "UPDATE control_pipeline_nodes SET state = ?, started_at = NULL,"
                        " finished_at = NULL, summary = ? WHERE mission_id = ? AND node_id = ?",
                        (
                            NodeState.READY,
                            "recovered after control-plane restart",
                            mission["mission_id"],
                            node["node_id"],
                        ),
                    )
                    self._append_event_locked(
                        mission_id=mission["mission_id"],
                        node_id=node["node_id"],
                        event_type="NODE_RECOVERED",
                        previous_state=str(NodeState.RUNNING),
                        next_state=str(NodeState.READY),
                        actor=actor,
                        backend=node["backend"],
                        message="running node reset to ready after restart",
                    )
                self.conn.execute(
                    "UPDATE control_missions SET state = ?, updated_at = ? WHERE mission_id = ?",
                    (MissionState.QUEUED, utc_now(), mission["mission_id"]),
                )
                self._append_event_locked(
                    mission_id=mission["mission_id"],
                    node_id=mission["current_node_id"],
                    event_type="MISSION_RECOVERED",
                    previous_state=mission["state"],
                    next_state=str(MissionState.QUEUED),
                    actor=actor,
                    backend=mission["backend"],
                    message="mission recovered from durable SQLite state",
                )
                recovered.append(mission["mission_id"])
            self.conn.commit()
        return recovered

    def _append_event_locked(
        self,
        *,
        mission_id: str,
        node_id: str,
        event_type: str,
        previous_state: str,
        next_state: str,
        actor: str,
        backend: str,
        message: str = "",
        artifact_refs: list[str] | None = None,
        command_result: dict[str, Any] | None = None,
        commit_sha: str = "",
    ) -> str:
        head = self.conn.execute(
            "SELECT event_hash FROM control_events WHERE mission_id = ? ORDER BY seq DESC LIMIT 1",
            (mission_id,),
        ).fetchone()
        previous_hash = head["event_hash"] if head else GENESIS_HASH
        event = {
            "event_id": str(uuid.uuid4()),
            "mission_id": mission_id,
            "node_id": node_id,
            "event_type": event_type,
            "previous_state": previous_state,
            "next_state": next_state,
            "timestamp": utc_now(),
            "actor": actor,
            "backend": backend,
            "message": message,
            "artifact_refs": list(artifact_refs or []),
            "command_result": command_result,
            "commit_sha": commit_sha or None,
            "previous_event_hash": previous_hash,
        }
        event_hash = _digest(event)
        self.conn.execute(
            "INSERT INTO control_events (event_id, mission_id, node_id, event_type,"
            " previous_state, next_state, timestamp, actor, backend, message,"
            " artifact_refs_json, command_result_json, commit_sha, previous_event_hash, event_hash)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event["event_id"],
                mission_id,
                node_id,
                event_type,
                previous_state,
                next_state,
                event["timestamp"],
                actor,
                backend,
                message,
                json.dumps(event["artifact_refs"]),
                json.dumps(command_result, sort_keys=True) if command_result else None,
                commit_sha or None,
                previous_hash,
                event_hash,
            ),
        )
        return event["event_id"]

    # ------------------------------------------------------------------
    # Registries: projects, repositories, workers, models
    # ------------------------------------------------------------------

    def upsert_project(
        self,
        *,
        key: str,
        name: str,
        description: str = "",
        surface: str = "MICHAEL_ANGELO",
        permission: str = "GREEN",
    ) -> dict[str, Any]:
        with self._lock:
            existing = self.conn.execute(
                "SELECT project_id FROM control_projects WHERE key = ?", (key,)
            ).fetchone()
            project_id = existing["project_id"] if existing else str(uuid.uuid4())
            self.conn.execute(
                "INSERT INTO control_projects (project_id, key, name, description, surface,"
                " permission, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET name=excluded.name,"
                " description=excluded.description, surface=excluded.surface,"
                " permission=excluded.permission",
                (project_id, key, name, description, surface, permission, utc_now()),
            )
            self.conn.commit()
        return self.project(key)

    def project(self, key: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM control_projects WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"unknown project: {key}")
        return dict(row)

    def projects(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM control_projects ORDER BY key"
            ).fetchall()
        ]

    def upsert_repository(
        self,
        *,
        project_key: str,
        slug: str,
        uri: str,
        default_branch: str = "main",
        executable: bool = False,
        permission: str = "GREEN",
    ) -> dict[str, Any]:
        project = self.project(project_key)
        with self._lock:
            existing = self.conn.execute(
                "SELECT repository_id FROM control_repositories WHERE slug = ?", (slug,)
            ).fetchone()
            repository_id = existing["repository_id"] if existing else str(uuid.uuid4())
            self.conn.execute(
                "INSERT INTO control_repositories (repository_id, project_id, slug, uri,"
                " default_branch, executable, permission, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(slug) DO UPDATE SET uri=excluded.uri,"
                " default_branch=excluded.default_branch, executable=excluded.executable,"
                " permission=excluded.permission, project_id=excluded.project_id",
                (
                    repository_id,
                    project["project_id"],
                    slug,
                    uri,
                    default_branch,
                    1 if executable else 0,
                    permission,
                    utc_now(),
                ),
            )
            self.conn.commit()
        return self.repository(slug)

    def repository(self, slug: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM control_repositories WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"unknown repository: {slug}")
        payload = dict(row)
        payload["executable"] = bool(payload["executable"])
        return payload

    def repositories(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT r.*, p.key AS project_key FROM control_repositories r"
            " JOIN control_projects p ON p.project_id = r.project_id ORDER BY r.slug"
        ).fetchall()
        payload = []
        for row in rows:
            item = dict(row)
            item["executable"] = bool(item["executable"])
            payload.append(item)
        return payload

    def upsert_worker(
        self,
        *,
        worker_id: str,
        name: str,
        kind: str,
        availability: str,
        reason: str = "",
        capabilities: tuple[str, ...] = (),
        ephemeral: bool = False,
    ) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO control_workers (worker_id, name, kind, availability, reason,"
                " capabilities_json, ephemeral, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(worker_id) DO UPDATE SET name=excluded.name, kind=excluded.kind,"
                " availability=excluded.availability, reason=excluded.reason,"
                " capabilities_json=excluded.capabilities_json, ephemeral=excluded.ephemeral,"
                " updated_at=excluded.updated_at",
                (
                    worker_id,
                    name,
                    kind,
                    availability,
                    reason,
                    _canonical_json(list(capabilities)),
                    1 if ephemeral else 0,
                    utc_now(),
                ),
            )
            self.conn.commit()

    def workers(self) -> list[dict[str, Any]]:
        payload = []
        for row in self.conn.execute(
            "SELECT * FROM control_workers ORDER BY availability DESC, worker_id"
        ).fetchall():
            item = dict(row)
            item["capabilities"] = json.loads(item.pop("capabilities_json"))
            item["ephemeral"] = bool(item["ephemeral"])
            payload.append(item)
        return payload

    def upsert_model(
        self,
        *,
        model_id: str,
        provider: str,
        role: str,
        availability: str,
        reason: str = "",
    ) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO control_models (model_id, provider, role, availability, reason,"
                " updated_at) VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(model_id) DO UPDATE SET provider=excluded.provider,"
                " role=excluded.role, availability=excluded.availability,"
                " reason=excluded.reason, updated_at=excluded.updated_at",
                (model_id, provider, role, availability, reason, utc_now()),
            )
            self.conn.commit()

    def models(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM control_models ORDER BY role, model_id"
            ).fetchall()
        ]

    # ------------------------------------------------------------------
    # Zgredek context packets
    # ------------------------------------------------------------------

    def append_context_event(
        self,
        mission_id: str,
        *,
        event_type: str,
        actor: str,
        message: str,
        node_id: str = "repository-fact-load",
        verdict: str = "",
    ) -> str:
        """Record a Zgredek APR checkpoint in the append-only ledger.

        Context events carry a verdict instead of a state change, so both state
        columns hold the verdict. That keeps the hash chain over a single event
        shape rather than introducing a second, weaker one.
        """
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                event_id = self._append_event_locked(
                    mission_id=mission_id,
                    node_id=node_id,
                    event_type=event_type,
                    previous_state=verdict or "CONTEXT",
                    next_state=verdict or "CONTEXT",
                    actor=actor,
                    backend="zgredek",
                    message=message[:500],
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return event_id

    def save_context_packet(self, mission_id: str, packet: dict[str, Any]) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO control_context_packets (mission_id, schema_version, adapter,"
                " packet_json, packet_sha256, repository, base_branch, approved_by,"
                " approved_at, prepared_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(mission_id) DO UPDATE SET schema_version=excluded.schema_version,"
                " adapter=excluded.adapter, packet_json=excluded.packet_json,"
                " packet_sha256=excluded.packet_sha256, repository=excluded.repository,"
                " base_branch=excluded.base_branch, approved_by=excluded.approved_by,"
                " approved_at=excluded.approved_at, prepared_at=excluded.prepared_at",
                (
                    mission_id,
                    packet.get("schemaVersion", ""),
                    packet.get("adapter", ""),
                    _canonical_json(packet),
                    packet.get("sha256", ""),
                    packet.get("repository", ""),
                    packet.get("baseBranch", ""),
                    packet.get("approvedBy", ""),
                    packet.get("approvedAt"),
                    packet.get("preparedAt", ""),
                ),
            )
            self.conn.commit()

    def context_packet(self, mission_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT packet_json FROM control_context_packets WHERE mission_id = ?",
            (mission_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["packet_json"])

    # ------------------------------------------------------------------
    # Budgets
    # ------------------------------------------------------------------

    def set_budget(self, scope: str, limit_amount: float, currency: str = "USD") -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO control_budgets (scope, limit_amount, spent_amount, currency,"
                " updated_at) VALUES (?, ?, 0, ?, ?)"
                " ON CONFLICT(scope) DO UPDATE SET limit_amount=excluded.limit_amount,"
                " currency=excluded.currency, updated_at=excluded.updated_at",
                (scope, float(limit_amount), currency, utc_now()),
            )
            self.conn.commit()

    def budgets(self) -> list[dict[str, Any]]:
        payload = []
        for row in self.conn.execute(
            "SELECT * FROM control_budgets ORDER BY scope"
        ).fetchall():
            item = dict(row)
            item["remaining_amount"] = item["limit_amount"] - item["spent_amount"]
            payload.append(item)
        return payload

    def budget(self, scope: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM control_budgets WHERE scope = ?", (scope,)
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["remaining_amount"] = item["limit_amount"] - item["spent_amount"]
        return item

    def charge_budget(
        self, scope: str, amount: float, *, mission_id: str = "", reason: str = ""
    ) -> dict[str, Any]:
        """Record spend against a scope. Raises ConflictError when the limit is exceeded."""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                row = self.conn.execute(
                    "SELECT * FROM control_budgets WHERE scope = ?", (scope,)
                ).fetchone()
                if row is None:
                    raise NotFoundError(f"unknown budget scope: {scope}")
                spent = float(row["spent_amount"]) + float(amount)
                if spent > float(row["limit_amount"]) + 1e-9:
                    raise ConflictError(
                        f"budget '{scope}' exhausted: {spent:.4f} exceeds limit"
                        f" {float(row['limit_amount']):.4f} {row['currency']}"
                    )
                self.conn.execute(
                    "UPDATE control_budgets SET spent_amount = ?, updated_at = ? WHERE scope = ?",
                    (spent, utc_now(), scope),
                )
                self.conn.execute(
                    "INSERT INTO control_budget_entries (entry_id, scope, mission_id, amount,"
                    " reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), scope, mission_id, float(amount), reason, utc_now()),
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return self.budget(scope)

    def budget_entries(self, scope: str | None = None) -> list[dict[str, Any]]:
        if scope:
            rows = self.conn.execute(
                "SELECT * FROM control_budget_entries WHERE scope = ? ORDER BY created_at DESC",
                (scope,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM control_budget_entries ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Durable queue
    # ------------------------------------------------------------------

    def enqueue(self, mission_id: str, priority: int = 100) -> dict[str, Any]:
        with self._lock:
            self.conn.execute(
                "INSERT INTO control_queue (queue_id, mission_id, priority, status, enqueued_at)"
                " VALUES (?, ?, ?, 'WAITING', ?)"
                " ON CONFLICT(mission_id) DO UPDATE SET status='WAITING',"
                " priority=excluded.priority, enqueued_at=excluded.enqueued_at,"
                " leased_at=NULL, finished_at=NULL",
                (str(uuid.uuid4()), mission_id, int(priority), utc_now()),
            )
            self.conn.commit()
        return self.queue_entry(mission_id)

    def queue_entry(self, mission_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM control_queue WHERE mission_id = ?", (mission_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"mission is not queued: {mission_id}")
        return dict(row)

    def queue(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT q.*, m.title, m.state AS mission_state, m.risk_level"
            " FROM control_queue q JOIN control_missions m ON m.mission_id = q.mission_id"
            " ORDER BY CASE q.status WHEN 'LEASED' THEN 0 WHEN 'WAITING' THEN 1 ELSE 2 END,"
            " q.priority, q.enqueued_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def lease_next(self) -> dict[str, Any] | None:
        """Atomically lease the highest-priority waiting mission."""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                row = self.conn.execute(
                    "SELECT * FROM control_queue WHERE status = 'WAITING'"
                    " ORDER BY priority, enqueued_at LIMIT 1"
                ).fetchone()
                if row is None:
                    self.conn.commit()
                    return None
                self.conn.execute(
                    "UPDATE control_queue SET status='LEASED', leased_at=?,"
                    " attempts = attempts + 1 WHERE queue_id = ?",
                    (utc_now(), row["queue_id"]),
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return self.queue_entry(row["mission_id"])

    def finish_queue_entry(
        self, mission_id: str, status: str, error: str = ""
    ) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE control_queue SET status = ?, finished_at = ?, last_error = ?"
                " WHERE mission_id = ?",
                (status, utc_now(), error[:500], mission_id),
            )
            self.conn.commit()

    def requeue_leased(self) -> list[str]:
        """Restart-recovery contract for the queue: leased work returns to WAITING."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT mission_id FROM control_queue WHERE status = 'LEASED'"
            ).fetchall()
            self.conn.execute(
                "UPDATE control_queue SET status='WAITING', leased_at=NULL"
                " WHERE status = 'LEASED'"
            )
            self.conn.commit()
        return [row["mission_id"] for row in rows]

    def _relative_to_state(self, path: Path) -> Path:
        resolved = path.resolve(strict=True)
        try:
            return resolved.relative_to(self.state_root)
        except ValueError as error:
            raise ConflictError(f"path escapes state root: {resolved}") from error

    def _state_path(self, relative: str, *, must_exist: bool) -> Path:
        candidate = (self.state_root / relative).resolve(strict=must_exist)
        try:
            candidate.relative_to(self.state_root)
        except ValueError as error:
            raise ConflictError(f"path escapes state root: {relative}") from error
        return candidate
