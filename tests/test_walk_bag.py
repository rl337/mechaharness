"""WalkBag register ABI and FileArtifact contracts."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from mechaharness.walk_bag import FileArtifact, WalkBag, WalkBagRegister


@dataclass(frozen=True)
class _PutGetCase:
    key: str
    value: object


@pytest.mark.parametrize(
    "case",
    [
        _PutGetCase(WalkBagRegister.IN, {"action": "mutate"}),
        _PutGetCase(WalkBagRegister.ASK, {"kind": "ASK_HUMAN"}),
        _PutGetCase(WalkBagRegister.ANS, {"approvals": {"d": "a1"}}),
        _PutGetCase(WalkBagRegister.OUT, FileArtifact(path="/tmp/out.bin")),
        _PutGetCase(WalkBagRegister.OUT, FileArtifact(url="https://ex/a")),
    ],
    ids=lambda c: f"{c.key}:{type(c.value).__name__}",
)
def test_walk_bag_put_get_require(case: _PutGetCase) -> None:
    bag = WalkBag()
    bag.put(case.key, case.value)
    assert bag.get(case.key) == case.value
    assert bag.require(case.key) == case.value
    assert case.key in bag


def test_walk_bag_require_missing() -> None:
    bag = WalkBag()
    with pytest.raises(KeyError, match="missing key"):
        bag.require(WalkBagRegister.ASK)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"path": "/a", "url": "https://b"},
        {"path": "", "url": ""},
    ],
    ids=["neither", "both", "empty"],
)
def test_file_artifact_needs_exactly_one_location(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        FileArtifact.model_validate(kwargs)


def test_graph_run_context_default_bag() -> None:
    from mechaharness.budget import Budget, BudgetPolicy
    from mechaharness.graph import ExecutionGraph
    from mechaharness.graph_executor import GraphRunContext

    ctx = GraphRunContext(
        graph=ExecutionGraph(goal="g"),
        run_id="r",
        agent_id="a",
        budget=Budget(BudgetPolicy.unlimited()),
    )
    ctx.bag.put(WalkBagRegister.CTX, {"epoch": 1})
    assert ctx.bag.require(WalkBagRegister.CTX) == {"epoch": 1}
