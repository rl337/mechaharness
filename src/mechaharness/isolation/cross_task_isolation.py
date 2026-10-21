"""Deprecated task-scoped visibility shim (MH-DOTS-07).

Prefer :class:`~mechaharness.job_lane_broker.JobLaneBroker` for product
lane sequences, exposure, and ``observe``. This guard remains for interim
call sites and unit tests; new work should not extend it.
"""

from __future__ import annotations

from mechaharness.handoff_record import HandoffRecord
from mechaharness.isolation.isolation_contract import IsolationContract
from mechaharness.job_lane_broker import IsolationViolation

__all__ = [
    "CrossTaskIsolationGuard",
    "IsolationViolation",
]


class CrossTaskIsolationGuard:
    """Per-task visible refs: contract inputs, own publications, shared handoffs.

    Deprecated — use :class:`~mechaharness.job_lane_broker.JobLaneBroker`.
    """

    def __init__(self) -> None:
        self._visible: dict[str, set[str]] = {}
        self._owners: dict[str, str] = {}

    def open_task(self, task_id: str, contract: IsolationContract) -> None:
        issues = contract.validation_issues()
        if issues:
            raise IsolationViolation(f"invalid isolation contract: {'; '.join(issues)}")
        self._visible[task_id] = set(contract.input_context_refs)

    def publish(self, task_id: str, ref: str) -> None:
        """Register a task-local ref; only ``task_id`` can read it by default."""
        self._require_open(task_id)
        owner = self._owners.setdefault(ref, task_id)
        if owner != task_id:
            raise IsolationViolation(f"ref {ref!r} is owned by task {owner!r}")
        self._visible[task_id].add(ref)

    def share(self, from_task: str, to_task: str, handoff: HandoffRecord) -> None:
        """Grant ``to_task`` the refs the source named in an explicit handoff."""
        self._require_open(to_task)
        self._require_open(from_task)
        for ref in handoff.evidence_refs:
            if ref not in self._visible[from_task]:
                raise IsolationViolation(
                    f"task {from_task!r} cannot hand off unreadable {ref!r}"
                )
            self._visible[to_task].add(ref)

    def can_read(self, task_id: str, ref: str) -> bool:
        return ref in self._visible.get(task_id, set())

    def assert_readable(self, task_id: str, ref: str) -> None:
        if not self.can_read(task_id, ref):
            raise IsolationViolation(f"task {task_id!r} cannot read {ref!r}")

    def close_task(self, task_id: str) -> None:
        """Drop a finished task's scope; its published refs stay unreadable to others."""
        self._visible.pop(task_id, None)

    def _require_open(self, task_id: str) -> None:
        if task_id not in self._visible:
            raise IsolationViolation(f"task {task_id!r} is not open")
