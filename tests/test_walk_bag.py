"""WalkBag register ABI, paths, deep serialize, and FileArtifact contracts."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from mechaharness.walk_bag import (
    FileArtifact,
    WalkBag,
    WalkBagPathError,
    WalkBagRegister,
    WalkBagSerializeError,
)


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


def test_walk_bag_path_get_put_require() -> None:
    bag = WalkBag()
    bag.path_put("acc.discovery.status", "found")
    assert bag.path_get("acc.discovery.status") == "found"
    assert bag.path_require("acc.discovery.status") == "found"
    assert bag.require("acc") == {"discovery": {"status": "found"}}


def test_walk_bag_path_missing() -> None:
    bag = WalkBag()
    with pytest.raises(WalkBagPathError, match="missing path"):
        bag.path_get("acc.discovery.status")


def test_walk_bag_serialize_roundtrip_file_artifact() -> None:
    bag = WalkBag()
    bag.put("out", FileArtifact(path="/tmp/a.bin", media_type="application/octet-stream"))
    bag.put("acc", {"discovery": {"status": "found"}})
    restored = WalkBag.deserialize(bag.serialize())
    assert restored.path_get("acc.discovery.status") == "found"
    out = restored.require("out")
    assert isinstance(out, FileArtifact)
    assert out.path == "/tmp/a.bin"


def test_walk_bag_deep_snapshot_isolates_nested_mutation() -> None:
    bag = WalkBag()
    bag.put("acc", {"n": 1})
    snap = bag.deep_snapshot()
    bag.path_put("acc.n", 2)
    assert snap.path_get("acc.n") == 1


def test_walk_bag_serialize_rejects_unsupported() -> None:
    bag = WalkBag()
    bag.put("acc", {"fn": lambda: None})  # type: ignore[dict-item]
    with pytest.raises(WalkBagSerializeError):
        bag.serialize()


def test_walk_bag_staged_writes_atomic_on_encode_failure() -> None:
    bag = WalkBag()
    bag.put("acc", {"ok": True})
    batch = bag.staged_writes().put("acc.n", 1)
    with pytest.raises(WalkBagSerializeError):
        batch.put("acc.bad", object())  # type: ignore[arg-type]
    assert bag.require("acc") == {"ok": True}
    assert "n" not in bag.require("acc")


def test_walk_bag_staged_writes_commit() -> None:
    bag = WalkBag()
    bag.staged_writes().put("acc.a", 1).put("acc.b", 2).commit()
    assert bag.path_get("acc.a") == 1
    assert bag.path_get("acc.b") == 2
