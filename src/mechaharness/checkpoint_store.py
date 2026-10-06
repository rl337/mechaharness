"""Checkpoint store protocol: authoritative graph + effect persistence (DR-01..05).

:class:`EventLogCheckpointStore` is the ephemeral/default adapter
(observability-friendly, not process-restart durable).
:class:`~mechaharness.sqlite_checkpoint_store.SqliteCheckpointStore`
is the durable SQLite reference backend.

Hosts bind a store through ``MechaHarnessConfig.get_checkpoint_store()``.
Inspect ``durability`` so ephemeral EventLog adapters are never mistaken for
process-restart safety::

    >>> from mechaharness.checkpoint_store import EventLogCheckpointStore
    >>> from mechaharness.core.events import InMemoryEventLog
    >>> from mechaharness.graph import ExecutionGraph, GraphNode, GraphStore
    >>> log = InMemoryEventLog()
    >>> store = EventLogCheckpointStore(GraphStore(log))
    >>> store.durability
    'ephemeral'
    >>> g = ExecutionGraph(goal="plan")
    >>> _ = g.add_node(GraphNode(id="a", kind="compute"))
    >>> rev = store.save(g, run_id="r1", boundary="dispatch", fingerprint="fp")
    >>> rev
    1
    >>> store.latest_fingerprint(run_id="r1")
    'fp'
    >>> store.latest_boundary(run_id="r1")
    'dispatch'
    >>> store.latest(run_id="r1").nodes["a"].kind
    'compute'
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Literal

from mechaharness.core.events import CoreEvent, Event, EventLog, event_type_key
from mechaharness.external_effect import EffectRecord, EffectState
from mechaharness.graph import ExecutionGraph, GraphStore, RecoveryBoundary

CheckpointDurability = Literal["ephemeral", "durable"]


class GraphEffectEvent(CoreEvent):
    """Observational effect-transition event (not authoritative for recovery)."""

    name = "graph_effect"


class CheckpointStore(ABC):
    """Authoritative persistence seam for graph checkpoints and effects.

    ``durability`` is inspectable so hosts are not led to believe EventLog-backed
    stores survive process restart (compatibility note in requirements).
    """

    durability: CheckpointDurability = "ephemeral"

    @abstractmethod
    def save(
        self,
        graph: ExecutionGraph,
        *,
        run_id: str | None = None,
        boundary: RecoveryBoundary | None = None,
        fingerprint: str | None = None,
    ) -> int:
        """Persist a checkpoint; return the new monotonic revision."""

    @abstractmethod
    def latest(self, *, run_id: str | None = None) -> ExecutionGraph | None:
        ...

    @abstractmethod
    def latest_fingerprint(self, *, run_id: str | None = None) -> str | None:
        ...

    @abstractmethod
    def latest_boundary(self, *, run_id: str | None = None) -> RecoveryBoundary | None:
        ...

    @abstractmethod
    def latest_revision(self, *, run_id: str | None = None) -> int | None:
        ...

    @abstractmethod
    def save_effect(self, effect: EffectRecord) -> EffectRecord:
        """Upsert an effect record; bumps revision; returns stored copy."""

    @abstractmethod
    def get_effect(self, effect_id: str) -> EffectRecord | None:
        ...

    @abstractmethod
    def list_effects(
        self,
        *,
        run_id: str,
        node_id: str | None = None,
    ) -> list[EffectRecord]:
        ...

    def get_node_effect(
        self,
        *,
        run_id: str,
        node_id: str,
        node_attempt: int | None = None,
    ) -> EffectRecord | None:
        """Return the latest effect for a node (optionally filtered by attempt)."""
        effects = self.list_effects(run_id=run_id, node_id=node_id)
        if node_attempt is not None:
            effects = [e for e in effects if e.node_attempt == node_attempt]
        if not effects:
            return None
        return max(effects, key=lambda e: (e.revision, e.effect_id))


class EventLogCheckpointStore(CheckpointStore):
    """Ephemeral adapter around :class:`~mechaharness.graph.GraphStore`.

    Effects are kept in-process (and mirrored as observational events). This
    store does **not** provide process-restart durability.

    Persist an effect intent before a non-idempotent external call::

        >>> from mechaharness.checkpoint_store import EventLogCheckpointStore
        >>> from mechaharness.core.events import InMemoryEventLog
        >>> from mechaharness.external_effect import EffectRecord, EffectState
        >>> from mechaharness.graph import GraphStore
        >>> store = EventLogCheckpointStore(GraphStore(InMemoryEventLog()))
        >>> effect = store.save_effect(EffectRecord(
        ...     effect_id="r1:job:1",
        ...     run_id="r1",
        ...     node_id="job",
        ...     node_attempt=1,
        ...     backend_id="host.coding_job",
        ...     state=EffectState.INTENDED,
        ... ))
        >>> effect.state.value
        'intended'
        >>> store.get_effect("r1:job:1").revision
        1
    """

    durability: CheckpointDurability = "ephemeral"

    def __init__(
        self,
        store: GraphStore,
        *,
        event_log: EventLog | None = None,
        agent_id: str | None = None,
    ) -> None:
        self.store = store
        self.event_log = event_log if event_log is not None else store.event_log
        self.agent_id = agent_id or store.agent_id
        self._effects: dict[str, EffectRecord] = {}
        self._revisions: dict[str, int] = {}
        self._boundaries: dict[str, RecoveryBoundary | None] = {}
        self._fingerprints: dict[str, str | None] = {}

    def save(
        self,
        graph: ExecutionGraph,
        *,
        run_id: str | None = None,
        boundary: RecoveryBoundary | None = None,
        fingerprint: str | None = None,
    ) -> int:
        rid = run_id or graph.id
        rev = self._revisions.get(rid, 0) + 1
        self._revisions[rid] = rev
        if boundary is not None:
            self._boundaries[rid] = boundary
        if fingerprint is not None:
            self._fingerprints[rid] = fingerprint
        elif graph.config_fingerprint:
            self._fingerprints[rid] = graph.config_fingerprint
        self.store.save(
            graph, run_id=rid, boundary=boundary, fingerprint=fingerprint
        )
        return rev

    def latest(self, *, run_id: str | None = None) -> ExecutionGraph | None:
        return self.store.latest(run_id=run_id)

    def latest_fingerprint(self, *, run_id: str | None = None) -> str | None:
        if run_id and run_id in self._fingerprints:
            return self._fingerprints[run_id]
        return self.store.latest_fingerprint(run_id=run_id)

    def latest_boundary(self, *, run_id: str | None = None) -> RecoveryBoundary | None:
        if run_id and run_id in self._boundaries:
            return self._boundaries[run_id]
        return self.store.latest_boundary(run_id=run_id)

    def latest_revision(self, *, run_id: str | None = None) -> int | None:
        if run_id is None:
            return None
        return self._revisions.get(run_id)

    def save_effect(self, effect: EffectRecord) -> EffectRecord:
        now = datetime.now(timezone.utc).isoformat()
        existing = self._effects.get(effect.effect_id)
        rev = (existing.revision if existing else 0) + 1
        stored = effect.model_copy(
            update={
                "revision": rev,
                "created_at": existing.created_at if existing else (effect.created_at or now),
                "updated_at": now,
            }
        )
        self._effects[stored.effect_id] = stored
        # Observational only — recovery must not depend on this event.
        self.event_log.emit(
            Event(
                type=event_type_key(GraphEffectEvent),
                agent_id=self.agent_id,
                run_id=stored.run_id,
                payload={"effect": stored.model_dump(mode="json")},
            )
        )
        return stored

    def get_effect(self, effect_id: str) -> EffectRecord | None:
        return self._effects.get(effect_id)

    def list_effects(
        self,
        *,
        run_id: str,
        node_id: str | None = None,
    ) -> list[EffectRecord]:
        out = [e for e in self._effects.values() if e.run_id == run_id]
        if node_id is not None:
            out = [e for e in out if e.node_id == node_id]
        return sorted(out, key=lambda e: (e.revision, e.effect_id))


def effect_from_mapping(payload: dict[str, Any]) -> EffectRecord:
    """Validate a stored effect mapping into :class:`EffectRecord`."""
    data = dict(payload)
    state = data.get("state")
    if isinstance(state, str):
        data["state"] = EffectState(state)
    return EffectRecord.model_validate(data)
