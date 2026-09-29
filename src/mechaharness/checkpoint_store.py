"""Checkpoint store protocol over :class:`~mechaharness.graph.GraphStore`."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from mechaharness.graph import ExecutionGraph, GraphStore, RecoveryBoundary


class CheckpointStore(ABC):
    """Durable graph execution state independent of model context."""

    @abstractmethod
    def save(
        self,
        graph: ExecutionGraph,
        *,
        run_id: str | None = None,
        boundary: RecoveryBoundary | None = None,
        fingerprint: str | None = None,
    ) -> None:
        ...

    @abstractmethod
    def latest(self, *, run_id: str | None = None) -> ExecutionGraph | None:
        ...

    @abstractmethod
    def latest_fingerprint(self, *, run_id: str | None = None) -> str | None:
        ...


class EventLogCheckpointStore(CheckpointStore):
    """Adapter around :class:`~mechaharness.graph.GraphStore`."""

    def __init__(self, store: GraphStore) -> None:
        self.store = store

    def save(
        self,
        graph: ExecutionGraph,
        *,
        run_id: str | None = None,
        boundary: RecoveryBoundary | None = None,
        fingerprint: str | None = None,
    ) -> None:
        self.store.save(
            graph, run_id=run_id, boundary=boundary, fingerprint=fingerprint
        )

    def latest(self, *, run_id: str | None = None) -> ExecutionGraph | None:
        return self.store.latest(run_id=run_id)

    def latest_fingerprint(self, *, run_id: str | None = None) -> str | None:
        return self.store.latest_fingerprint(run_id=run_id)

    def latest_boundary(self, *, run_id: str | None = None) -> RecoveryBoundary | None:
        return self.store.latest_boundary(run_id=run_id)
