"""Host kit: Config-injected GraphExecutor + submit-once effectful runner.

Pytest examples (readable host wiring)
--------------------------------------

The doctests on :mod:`mechaharness.host_kit` are the primary worked examples
(``pytest --doctest-modules``). This module covers the branch matrix and a few
structural guards hosts hit when wiring incorrectly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mechaharness.host_kit import SubmitOnceEffectfulRunner, host_graph_executor
from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore
from tests.support.host_kit_cases import assert_expect, iter_cases, run_case

_CASES = iter_cases()


def _case_id(case: object) -> str:
    return getattr(case, "id", "unknown")


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
@pytest.mark.asyncio
async def test_host_kit_case(case: object, tmp_path: Path) -> None:
    assert _CASES, "expected host_kit fixtures under tests/fixtures/host_kit/"
    durable = bool(getattr(case, "data", {}).get("durable", True))
    db = tmp_path / f"{_case_id(case)}.sqlite" if durable else None
    payload = await run_case(case, db_path=db)  # type: ignore[arg-type]
    assert_expect(payload["actual"], payload["expect"], case_id=_case_id(case))


def test_host_kit_fixture_ids_unique() -> None:
    ids = [_case_id(c) for c in _CASES]
    assert len(ids) >= 5
    assert len(ids) == len(set(ids))


def test_submit_once_requires_kinds() -> None:
    with pytest.raises(ValueError, match="at least one kind"):
        SubmitOnceEffectfulRunner(kinds=[], backend_id="x")


def test_host_graph_executor_rejects_checkpoint_both(tmp_path: Path) -> None:
    runner = SubmitOnceEffectfulRunner(kinds=["coding_job"], backend_id="x")
    store = SqliteCheckpointStore(tmp_path / "a.sqlite")
    with pytest.raises(ValueError, match="not both"):
        host_graph_executor(
            runners=[runner],
            checkpoint_path=tmp_path / "b.sqlite",
            checkpoint_store=store,
        )
    store.close()


@pytest.mark.asyncio
async def test_submit_once_dispatch_requires_submit_callable() -> None:
    """Example: subclass or pass submit= — bare runner cannot dispatch."""
    from mechaharness.budget import Budget, BudgetPolicy
    from mechaharness.external_effect import EffectRecord, EffectState
    from mechaharness.graph import ExecutionGraph, GraphNode
    from mechaharness.graph_executor import GraphRunContext

    runner = SubmitOnceEffectfulRunner(kinds=["coding_job"], backend_id="x")
    node = GraphNode(id="coding_job", kind="coding_job")
    effect = EffectRecord(
        effect_id="r:coding_job:1",
        run_id="r",
        node_id="coding_job",
        state=EffectState.INTENDED,
    )
    ctx = GraphRunContext(
        graph=ExecutionGraph(goal="x"),
        run_id="r",
        agent_id="host",
        budget=Budget(BudgetPolicy.unlimited()),
    )
    with pytest.raises(TypeError, match="submit="):
        await runner.dispatch(node, effect=effect, context=ctx)
