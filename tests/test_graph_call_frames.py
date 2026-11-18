"""Push, return and restart through the public executor interface."""

from pathlib import Path

import pytest

from mechaharness.budget import BudgetPolicy
from tests.support.graph_call_frames import walk_project_frames


@pytest.mark.parametrize(
    "depth,crash,fail_leaf,missing_output,stepped",
    [
        (1, False, False, False, False),
        (3, True, False, False, False),
        (20, False, False, False, False),
        (3, False, False, False, True),
        (3, False, True, False, False),
        (3, False, False, True, False),
    ],
)
async def test_project_call_stack(
    tmp_path: Path,
    depth: int,
    crash: bool,
    fail_leaf: bool,
    missing_output: bool,
    stepped: bool,
) -> None:
    out = await walk_project_frames(
        tmp_path,
        depth,
        crash=crash,
        fail_leaf=fail_leaf,
        missing_output=missing_output,
        stepped=stepped,
    )
    assert out["visited"] == list(range(1, depth + 1))
    assert out["leaf_calls"] == 1
    assert out["root_stack"] == []
    assert out["recovered"] == crash
    if fail_leaf or missing_output:
        assert out["status"] == "failed"
        assert "out" not in out["root_bag"]
    else:
        assert out["status"] == "ok"
        assert out["spent"] == 2 * depth + 1
        if stepped:
            assert max(out["pauses"]) == depth
        assert out["accepted"] == list(range(depth, 0, -1))
        assert out["root_bag"]["out"] == {"proof": depth}
        if depth > 1:
            assert out["root_bag"]["in"] == {"goal": "project"}


@pytest.mark.parametrize(
    "limit,status", [("soft_limit", "soft_exhausted"), ("hard_limit", "failed")]
)
async def test_child_exhausts_shared_budget(tmp_path: Path, limit: str, status: str) -> None:
    out = await walk_project_frames(tmp_path, 3, policy=BudgetPolicy(**{limit: 4}))
    assert out["status"] == status
    assert out["spent"] == 4
    assert out["leaf_calls"] == 1
    assert out["accepted"] == []
    assert out["root_stack"] == []
    assert "out" not in out["root_bag"]
