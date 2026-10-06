"""SQLite reference :class:`~mechaharness.checkpoint_store.CheckpointStore` (DR-02).

Single-host durable persistence: one database may hold many runs keyed by
``run_id``. Schema is initialized/migrated deterministically on open. Writes
are transactional; readers use shared locks with serialized writers.

Survive process restart by reopening the same path::

    >>> import tempfile
    >>> from pathlib import Path
    >>> from mechaharness.external_effect import EffectRecord, EffectState
    >>> from mechaharness.graph import ExecutionGraph, GraphNode, NodeStatus
    >>> from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore
    >>> path = Path(tempfile.mkdtemp()) / "runs.sqlite"
    >>> store = SqliteCheckpointStore(path)
    >>> store.durability
    'durable'
    >>> g = ExecutionGraph(goal="dispatch coding job")
    >>> _ = g.add_node(GraphNode(id="job", kind="coding_job", status=NodeStatus.RUNNING))
    >>> _ = store.save(g, run_id="run-1", boundary="dispatch", fingerprint="fp")
    >>> _ = store.save_effect(EffectRecord(
    ...     effect_id="run-1:job:1",
    ...     run_id="run-1",
    ...     node_id="job",
    ...     node_attempt=1,
    ...     backend_id="host.cursor",
    ...     state=EffectState.ACCEPTED,
    ...     external_handle="cursor-run-42",
    ... ))
    >>> store.close()
    >>> # Fresh process against the same file:
    >>> again = SqliteCheckpointStore(path)
    >>> again.latest(run_id="run-1").nodes["job"].status.value
    'running'
    >>> again.get_effect("run-1:job:1").external_handle
    'cursor-run-42'
    >>> again.latest_boundary(run_id="run-1")
    'dispatch'
    >>> again.close()
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, get_args

from mechaharness.checkpoint_store import CheckpointDurability, CheckpointStore, effect_from_mapping
from mechaharness.external_effect import EffectRecord
from mechaharness.graph import ExecutionGraph, RecoveryBoundary

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    run_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    boundary TEXT,
    fingerprint TEXT,
    graph_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, revision)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON checkpoints(run_id, revision DESC);

CREATE TABLE IF NOT EXISTS effects (
    effect_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    node_attempt INTEGER NOT NULL,
    backend_id TEXT NOT NULL DEFAULT '',
    external_handle TEXT,
    state TEXT NOT NULL,
    revision INTEGER NOT NULL,
    recovery_boundary TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_effects_run_node ON effects(run_id, node_id, revision DESC);
"""


class SqliteCheckpointStore(CheckpointStore):
    """Process-restart-durable checkpoint + effect store."""

    durability: CheckpointDurability = "durable"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.parent and str(self.path.parent) not in {"", "."}:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            isolation_level=None,  # explicit BEGIN
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _migrate(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA_SQL)
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
                    (str(_SCHEMA_VERSION),),
                )
            else:
                version = int(row["value"])
                if version > _SCHEMA_VERSION:
                    raise RuntimeError(
                        f"sqlite checkpoint schema {version} newer than supported {_SCHEMA_VERSION}"
                    )
                if version < _SCHEMA_VERSION:
                    # Future migrations land here; v1 is the baseline.
                    self._conn.execute(
                        "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                        (str(_SCHEMA_VERSION),),
                    )

    def save(
        self,
        graph: ExecutionGraph,
        *,
        run_id: str | None = None,
        boundary: RecoveryBoundary | None = None,
        fingerprint: str | None = None,
    ) -> int:
        rid = run_id or graph.id
        if fingerprint is not None:
            graph.config_fingerprint = fingerprint
        fp = fingerprint or graph.config_fingerprint
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(graph.checkpoint(), separators=(",", ":"), sort_keys=True)
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT COALESCE(MAX(revision), 0) AS rev FROM checkpoints WHERE run_id = ?",
                    (rid,),
                ).fetchone()
                rev = int(row["rev"]) + 1
                self._conn.execute(
                    """
                    INSERT INTO checkpoints(
                        run_id, revision, boundary, fingerprint, graph_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (rid, rev, boundary, fp, payload, now),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return rev

    def latest(self, *, run_id: str | None = None) -> ExecutionGraph | None:
        if run_id is None:
            return None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT graph_json FROM checkpoints
                WHERE run_id = ?
                ORDER BY revision DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["graph_json"])
        if not isinstance(payload, dict):
            return None
        return ExecutionGraph.resume(payload)

    def latest_fingerprint(self, *, run_id: str | None = None) -> str | None:
        row = self._latest_row(run_id)
        if row is None:
            return None
        fp = row["fingerprint"]
        if isinstance(fp, str) and fp:
            return fp
        payload = json.loads(row["graph_json"])
        nested = payload.get("config_fingerprint") if isinstance(payload, dict) else None
        return nested if isinstance(nested, str) else None

    def latest_boundary(self, *, run_id: str | None = None) -> RecoveryBoundary | None:
        row = self._latest_row(run_id)
        if row is None:
            return None
        boundary = row["boundary"]
        if isinstance(boundary, str) and boundary in get_args(RecoveryBoundary):
            return boundary  # type: ignore[return-value]
        return None

    def latest_revision(self, *, run_id: str | None = None) -> int | None:
        row = self._latest_row(run_id)
        if row is None:
            return None
        return int(row["revision"])

    def _latest_row(self, run_id: str | None) -> sqlite3.Row | None:
        if run_id is None:
            return None
        with self._lock:
            row = self._conn.execute(
                """
                SELECT revision, boundary, fingerprint, graph_json
                FROM checkpoints
                WHERE run_id = ?
                ORDER BY revision DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        return row if isinstance(row, sqlite3.Row) else None

    def save_effect(self, effect: EffectRecord) -> EffectRecord:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._conn.execute(
                    "SELECT revision, created_at FROM effects WHERE effect_id = ?",
                    (effect.effect_id,),
                ).fetchone()
                rev = (int(existing["revision"]) + 1) if existing else 1
                created = (
                    existing["created_at"]
                    if existing
                    else (effect.created_at or now)
                )
                detail_json = json.dumps(
                    effect.detail, separators=(",", ":"), sort_keys=True
                )
                self._conn.execute(
                    """
                    INSERT INTO effects(
                        effect_id, run_id, node_id, node_attempt, backend_id,
                        external_handle, state, revision, recovery_boundary,
                        detail_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(effect_id) DO UPDATE SET
                        run_id=excluded.run_id,
                        node_id=excluded.node_id,
                        node_attempt=excluded.node_attempt,
                        backend_id=excluded.backend_id,
                        external_handle=excluded.external_handle,
                        state=excluded.state,
                        revision=excluded.revision,
                        recovery_boundary=excluded.recovery_boundary,
                        detail_json=excluded.detail_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        effect.effect_id,
                        effect.run_id,
                        effect.node_id,
                        effect.node_attempt,
                        effect.backend_id,
                        effect.external_handle,
                        effect.state.value,
                        rev,
                        effect.recovery_boundary,
                        detail_json,
                        created,
                        now,
                    ),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return effect.model_copy(
            update={"revision": rev, "created_at": created, "updated_at": now}
        )

    def get_effect(self, effect_id: str) -> EffectRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM effects WHERE effect_id = ?",
                (effect_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_effect(row)

    def list_effects(
        self,
        *,
        run_id: str,
        node_id: str | None = None,
    ) -> list[EffectRecord]:
        with self._lock:
            if node_id is None:
                rows = self._conn.execute(
                    "SELECT * FROM effects WHERE run_id = ? ORDER BY revision ASC",
                    (run_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM effects
                    WHERE run_id = ? AND node_id = ?
                    ORDER BY revision ASC
                    """,
                    (run_id, node_id),
                ).fetchall()
        return [self._row_to_effect(r) for r in rows]

    @staticmethod
    def _row_to_effect(row: sqlite3.Row) -> EffectRecord:
        detail_raw = row["detail_json"] or "{}"
        detail: Any = json.loads(detail_raw)
        if not isinstance(detail, dict):
            detail = {}
        return effect_from_mapping(
            {
                "effect_id": row["effect_id"],
                "run_id": row["run_id"],
                "node_id": row["node_id"],
                "node_attempt": row["node_attempt"],
                "backend_id": row["backend_id"],
                "external_handle": row["external_handle"],
                "state": row["state"],
                "revision": row["revision"],
                "recovery_boundary": row["recovery_boundary"],
                "detail": detail,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
