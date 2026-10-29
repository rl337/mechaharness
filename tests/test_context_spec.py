"""ContextSpec freeze / compile / publish (gastronomic M2)."""

from __future__ import annotations

import pytest

from mechaharness.context_spec import (
    ContextRead,
    ContextResponseSpec,
    ContextSpec,
    ContextSpecError,
    compile_context_spec,
    freeze_bag_snapshot,
    publish_response_to_bag,
)
from mechaharness.walk_bag import WalkBag, WalkBagPathError


def _seed_bag() -> WalkBag:
    bag = WalkBag()
    bag.path_put("in.goal", "bootstrap calculator")
    bag.path_put(
        "out.discovery",
        {"status": "found", "files": ["calc.py"], "hypotheses": ["literals"]},
    )
    bag.path_put("out.verified", {"discovery_status": "found", "files_ok": True})
    bag.path_put("ctx.noise", {"secret": "do-not-send"})
    return bag


def test_compile_includes_declared_paths_and_omits_noise() -> None:
    bag = _seed_bag()
    snapshot_id, frozen = freeze_bag_snapshot(bag)
    spec = ContextSpec(
        reads=[
            ContextRead(path="in.goal"),
            ContextRead(path="out.discovery"),
            ContextRead(path="out.verified"),
        ],
        system="Plan from bag evidence only.",
        response=ContextResponseSpec(writes="out.plan"),
    )
    compiled = compile_context_spec(
        frozen, spec, snapshot_id=snapshot_id, model="mock", node_id="plan"
    )
    assert compiled.included_paths == ["in.goal", "out.discovery", "out.verified"]
    assert "ctx.noise" not in compiled.included_paths
    user = compiled.messages[-1].content
    assert "bootstrap calculator" in user
    assert "calc.py" in user
    assert "files_ok" in user
    assert "do-not-send" not in user
    assert compiled.content_hash
    assert compiled.manifest.extra["snapshot_id"] == snapshot_id


def test_compile_is_deterministic_for_same_snapshot() -> None:
    bag = _seed_bag()
    snapshot_id, frozen = freeze_bag_snapshot(bag)
    spec = ContextSpec(
        reads=[ContextRead(path="in.goal"), ContextRead(path="out.discovery")],
        response=ContextResponseSpec(writes="out.plan"),
    )
    a = compile_context_spec(frozen, spec, snapshot_id=snapshot_id)
    b = compile_context_spec(frozen, spec, snapshot_id=snapshot_id)
    assert a.content_hash == b.content_hash
    assert [m.content for m in a.messages] == [m.content for m in b.messages]


def test_required_missing_path_fails_before_messages() -> None:
    bag = WalkBag()
    bag.path_put("in.goal", "x")
    snapshot_id, frozen = freeze_bag_snapshot(bag)
    spec = ContextSpec(
        reads=[ContextRead(path="out.discovery", required=True)],
        response=ContextResponseSpec(writes="out.plan"),
    )
    with pytest.raises(ContextSpecError, match="out.discovery"):
        compile_context_spec(frozen, spec, snapshot_id=snapshot_id)


def test_publish_json_writes_live_bag_without_mutating_snapshot() -> None:
    live = _seed_bag()
    snapshot_id, frozen = freeze_bag_snapshot(live)
    publish_response_to_bag(
        live,
        ContextResponseSpec(writes="out.plan", parse="json"),
        '{"plan":"add parser"}',
    )
    assert live.path_get("out.plan") == {"plan": "add parser"}
    with pytest.raises(WalkBagPathError):
        frozen.path_get("out.plan")
    assert snapshot_id


def test_publish_rejects_invalid_json() -> None:
    bag = WalkBag()
    with pytest.raises(ContextSpecError, match="JSON"):
        publish_response_to_bag(
            bag,
            ContextResponseSpec(writes="out.plan", parse="json"),
            "not-json",
        )
