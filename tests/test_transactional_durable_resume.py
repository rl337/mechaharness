"""Transactional durable resume crash-window matrix (DR-02, DR-10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mechaharness.budget import BudgetPolicy
from mechaharness.external_effect import EffectRecord, EffectState
from mechaharness.graph import NodeStatus
from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore
from tests.support.transactional_durable_resume_cases import (
    FakeCodingJobBackend,
    assert_expect,
    build_executor,
    iter_cases,
    make_graph,
    run_crash_case,
)

_CASES = iter_cases()


def _case_id(case: object) -> str:
    return getattr(case, "id", "unknown")


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
@pytest.mark.asyncio
async def test_transactional_durable_resume_crash_matrix(
    case: object, tmp_path: Path
) -> None:
    assert _CASES, "expected transactional durable resume fixtures"
    db = tmp_path / f"{_case_id(case)}.sqlite"
    payload = await run_crash_case(case, db_path=db)  # type: ignore[arg-type]
    assert_expect(payload["actual"], payload["expect"])


def test_transactional_durable_resume_fixture_ids_unique() -> None:
    ids = [_case_id(c) for c in _CASES]
    assert len(ids) >= 6
    assert len(ids) == len(set(ids))


@pytest.mark.asyncio
async def test_uncertain_effect_without_backend_job_needs_attention(
    tmp_path: Path,
) -> None:
    """DR-06: unknowable uncertain acceptance must not redispatch."""
    store = SqliteCheckpointStore(tmp_path / "uncertain.sqlite")
    backend = FakeCodingJobBackend()
    backend.unknown_effect_ids = {"run-u:dispatch:1"}
    run_id = "run-u"
    store.save_effect(
        EffectRecord(
            effect_id=f"{run_id}:dispatch:1",
            run_id=run_id,
            node_id="dispatch",
            node_attempt=1,
            backend_id="fake.coding_job",
            state=EffectState.UNCERTAIN,
            recovery_boundary="dispatch",
        )
    )
    graph = make_graph()
    graph.nodes["dispatch"].attempt = 1
    graph.nodes["dispatch"].status = NodeStatus.RUNNING
    store.save(graph, run_id=run_id, boundary="dispatch", fingerprint="fp")

    executor = build_executor(store=store, backend=backend)
    result = await executor.run(
        make_graph(),
        budget_policy=BudgetPolicy.unlimited(),
        run_id=run_id,
        resume=True,
        skip_linkage=True,
    )
    assert result.status == "failed"
    assert result.graph.nodes["dispatch"].error == "uncertain_effect_unresolved"
    assert backend.dispatch_count == 0
    assert backend.reconcile_count >= 1
    effect = store.get_effect(f"{run_id}:dispatch:1")
    assert effect is not None
    assert effect.state is EffectState.NEEDS_ATTENTION
    store.close()
