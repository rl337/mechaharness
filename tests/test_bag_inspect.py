"""Snapshot-bound inspection toolkit (gastronomic M3)."""

from __future__ import annotations

from mechaharness.bag_inspect import (
    InspectionPolicy,
    PriorResponseRecord,
    SnapshotInspectionToolkit,
)
from mechaharness.walk_bag import WalkBag


def _toolkit() -> SnapshotInspectionToolkit:
    bag = WalkBag()
    bag.path_put("out.evidence", {"status": "found", "n": 1})
    bag.path_put("ctx.secret", "nope")
    policy = InspectionPolicy(
        allowed_paths=["out.evidence"],
        max_tool_calls=5,
        max_bytes=2048,
        default_limit=64,
    )
    priors = {
        "inv-1": PriorResponseRecord(
            invocation_id="inv-1",
            snapshot_id="snap-a",
            published={"note": "prior"},
            bag_write="out.prior_note",
        )
    }
    return SnapshotInspectionToolkit(
        bag,
        snapshot_id="snap-1",
        policy=policy,
        prior_responses=priors,
    )


def test_inspect_bag_stable_after_live_mutation() -> None:
    live = WalkBag()
    live.path_put("out.evidence", {"status": "found"})
    snap = live.deep_snapshot()
    toolkit = SnapshotInspectionToolkit(
        snap,
        snapshot_id="s1",
        policy=InspectionPolicy(allowed_paths=["out.evidence"]),
    )
    first = toolkit.inspect_bag("out.evidence")
    live.path_put("out.evidence", {"status": "mutated"})
    second = toolkit.inspect_bag("out.evidence")
    assert first.status == "ok"
    assert second.status == "ok"
    assert first.value == second.value == {"status": "found"}
    assert live.path_get("out.evidence")["status"] == "mutated"


def test_inspect_bag_denies_unauthorized_path() -> None:
    toolkit = _toolkit()
    denied = toolkit.inspect_bag("ctx.secret")
    assert denied.status == "denied"
    assert denied.reason == "path_not_allowed"


def test_inspect_prior_response_reads_published_field() -> None:
    toolkit = _toolkit()
    outcome = toolkit.inspect_prior_response("inv-1", "published")
    assert outcome.status == "ok"
    assert outcome.value == {"note": "prior"}


def test_inspect_bag_truncates_large_string() -> None:
    bag = WalkBag()
    bag.path_put("out.evidence", "x" * 200)
    toolkit = SnapshotInspectionToolkit(
        bag,
        snapshot_id="s",
        policy=InspectionPolicy(allowed_paths=["out.evidence"], default_limit=10),
    )
    outcome = toolkit.inspect_bag("out.evidence", limit=10)
    assert outcome.status == "truncated"
    assert outcome.value == "x" * 10
    assert outcome.truncated is True
