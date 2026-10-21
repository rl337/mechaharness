"""JobLaneBroker: run sequence selectors, exposure, grants, handoff (JL-*)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from mechaharness.handoff_record import HandoffRecord
from mechaharness.job_lane_broker import (
    ExposureRule,
    IsolationViolation,
    JobLane,
    JobLaneBroker,
    ObserveSelector,
    job_lane_broker_from_mapping,
)
from mechaharness.walk_bag import FileArtifact

T0 = datetime(2026, 10, 21, 10, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 10, 21, 14, 0, 0, tzinfo=timezone.utc)


def _assets_billing(*, asset_mode: str = "deny_all", meta_mode: str = "deny_all") -> JobLaneBroker:
    asset_rule = (
        ExposureRule(mode="allow_lanes", lanes=["billing.settle"])
        if asset_mode == "allow_lanes"
        else ExposureRule(mode=asset_mode)  # type: ignore[arg-type]
    )
    meta_rule = (
        ExposureRule(mode="allow_lanes", lanes=["billing.settle"])
        if meta_mode == "allow_lanes"
        else ExposureRule(mode=meta_mode)  # type: ignore[arg-type]
    )
    return JobLaneBroker(
        lanes={
            "assets.generate": JobLane(
                lane_id="assets.generate",
                meta=meta_rule,
                keys={"asset_urls": asset_rule},
            ),
            "billing.settle": JobLane(
                lane_id="billing.settle",
                meta=ExposureRule(mode="open"),
                keys={},
            ),
        }
    )


@dataclass(frozen=True)
class ObserveCase:
    id: str
    caller: str
    target: str
    selector: dict
    key: str | None
    meta: bool
    expect_status: str
    expect_run_id: str | None = None
    setup: str = "default"


@pytest.mark.parametrize(
    "case",
    [
        ObserveCase(
            id="same_lane_lineage",
            caller="assets.generate",
            target="assets.generate",
            selector={"latest": True},
            key="asset_urls",
            meta=False,
            expect_status="ok",
            expect_run_id="gen-late",
        ),
        ObserveCase(
            id="cross_deny",
            caller="billing.settle",
            target="assets.generate",
            selector={"latest": True},
            key="asset_urls",
            meta=False,
            expect_status="denied",
            expect_run_id="gen-late",
        ),
        ObserveCase(
            id="allow_lanes_key",
            caller="billing.settle",
            target="assets.generate",
            selector={"latest": True},
            key="asset_urls",
            meta=False,
            expect_status="ok",
            expect_run_id="gen-late",
            setup="allow_lanes",
        ),
        ObserveCase(
            id="before_selector",
            caller="assets.generate",
            target="assets.generate",
            selector={"before": "2026-10-21T12:00:00Z"},
            key="asset_urls",
            meta=False,
            expect_status="ok",
            expect_run_id="gen-early",
        ),
        ObserveCase(
            id="run_id_selector",
            caller="assets.generate",
            target="assets.generate",
            selector={"run_id": "gen-early"},
            key="asset_urls",
            meta=False,
            expect_status="ok",
            expect_run_id="gen-early",
        ),
        ObserveCase(
            id="meta_allowlist",
            caller="billing.settle",
            target="assets.generate",
            selector={"latest": True},
            key=None,
            meta=True,
            expect_status="ok",
            expect_run_id="gen-late",
            setup="meta_allow",
        ),
        ObserveCase(
            id="meta_deny",
            caller="billing.settle",
            target="assets.generate",
            selector={"latest": True},
            key=None,
            meta=True,
            expect_status="denied",
            expect_run_id="gen-late",
        ),
    ],
    ids=lambda c: c.id,
)
def test_observe_matrix(case: ObserveCase) -> None:
    if case.setup == "allow_lanes":
        broker = _assets_billing(asset_mode="allow_lanes")
    elif case.setup == "meta_allow":
        broker = _assets_billing(meta_mode="allow_lanes")
    else:
        broker = _assets_billing()
    broker.open_run("assets.generate", "gen-early", started_at=T0)
    broker.put(
        "assets.generate",
        "gen-early",
        "asset_urls",
        FileArtifact(url="https://cdn/early.png"),
    )
    broker.open_run("assets.generate", "gen-late", started_at=T2)
    broker.put(
        "assets.generate",
        "gen-late",
        "asset_urls",
        FileArtifact(url="https://cdn/late.png"),
    )
    broker.open_run("billing.settle", "bill-1", started_at=T1)

    result = broker.observe(
        case.caller,
        case.target,
        selector=ObserveSelector.model_validate(case.selector),
        key=case.key,
        meta=case.meta,
    )
    assert result.status == case.expect_status
    if case.expect_run_id is not None:
        assert result.run_id == case.expect_run_id
    if case.expect_status == "ok" and case.key == "asset_urls":
        assert result.value["url"].endswith(
            "early.png" if case.expect_run_id == "gen-early" else "late.png"
        )


def test_standing_grant_unlocks_deny_all_key() -> None:
    broker = _assets_billing()
    broker.open_run("assets.generate", "g1", started_at=T0)
    broker.put(
        "assets.generate",
        "g1",
        "asset_urls",
        FileArtifact(url="https://cdn/a.png"),
    )
    broker.open_run("billing.settle", "b1", started_at=T1)
    denied = broker.observe(
        "billing.settle",
        "assets.generate",
        selector=ObserveSelector(latest=True),
        key="asset_urls",
    )
    assert denied.status == "denied"
    broker.grant(
        from_lane="assets.generate",
        to_lane="billing.settle",
        keys=["asset_urls"],
    )
    allowed = broker.observe(
        "billing.settle",
        "assets.generate",
        selector=ObserveSelector(latest=True),
        key="asset_urls",
    )
    assert allowed.status == "ok"
    assert allowed.value == {"url": "https://cdn/a.png"}


def test_handoff_oneshot_share() -> None:
    broker = _assets_billing()
    broker.open_run("assets.generate", "g1", started_at=T0)
    broker.put("assets.generate", "g1", "memo:1", "secret")
    broker.put("assets.generate", "g1", "memo:2", "other")
    broker.open_run("billing.settle", "b1", started_at=T1)
    broker.handoff(
        "assets.generate",
        "billing.settle",
        HandoffRecord(evidence_refs=["memo:1"]),
    )
    assert (
        broker.observe(
            "billing.settle",
            "assets.generate",
            selector=ObserveSelector(latest=True),
            key="memo:1",
        ).status
        == "ok"
    )
    assert (
        broker.observe(
            "billing.settle",
            "assets.generate",
            selector=ObserveSelector(latest=True),
            key="memo:2",
        ).status
        == "denied"
    )
    with pytest.raises(IsolationViolation, match="unreadable"):
        broker.handoff(
            "assets.generate",
            "billing.settle",
            HandoffRecord(evidence_refs=["memo:ghost"]),
        )


def test_job_lane_broker_from_mapping_and_yaml_surface() -> None:
    broker = job_lane_broker_from_mapping(
        {
            "assets.generate": {
                "meta": {"mode": "allow_lanes", "lanes": ["billing.settle"]},
                "keys": {
                    "asset_urls": {
                        "mode": "allow_lanes",
                        "lanes": ["billing.settle"],
                    }
                },
            },
            "billing.settle": {"meta": {"mode": "open"}, "keys": {}},
        },
        lane_grants=[],
    )
    assert set(broker.lanes()) == {"assets.generate", "billing.settle"}
    broker.open_run("assets.generate", "r1", started_at=T0)
    broker.put(
        "assets.generate",
        "r1",
        "asset_urls",
        FileArtifact(url="https://cdn/x.png"),
    )
    broker.open_run("billing.settle", "b1", started_at=T1)
    result = broker.observe(
        "billing.settle",
        "assets.generate",
        selector=ObserveSelector(latest=True),
        key="asset_urls",
    )
    assert result.status == "ok"


def test_at_or_before_includes_boundary() -> None:
    broker = _assets_billing(asset_mode="open")
    broker.open_run("assets.generate", "g1", started_at=T1)
    broker.put("assets.generate", "g1", "asset_urls", FileArtifact(url="https://cdn/m.png"))
    broker.open_run("billing.settle", "b1", started_at=T2)
    result = broker.observe(
        "billing.settle",
        "assets.generate",
        selector=ObserveSelector(at_or_before="2026-10-21T12:00:00Z"),
        key="asset_urls",
    )
    assert result.status == "ok"
    assert result.run_id == "g1"
