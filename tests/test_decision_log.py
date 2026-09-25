"""Decision log export and topology metrics (OBS-*)."""

from __future__ import annotations

from mechaharness.decision_log import (
    DecisionLog,
    DecisionRecord,
    TopologySpan,
    compute_topology_metrics,
    export_offline_dataset,
)


def test_offline_export_excludes_future_outcomes() -> None:
    log = DecisionLog()
    rec = DecisionRecord(
        eventId="d1",
        stateHash="h",
        policyVersion="p1",
        verdict="ALLOW",
        outcomeId="late-1",
        allowedCandidates=["a", "b"],
        excludedCandidates={"c": "unauthorized"},
    )
    log.record(rec)
    export = export_offline_dataset([rec], split="train", include_outcomes=False)
    assert export.records[0]["outcomeId"] is None
    with_out = export_offline_dataset([rec], split="eval", include_outcomes=True)
    assert with_out.records[0]["outcomeId"] == "late-1"


def test_topology_metrics_distinguish_work_and_elapsed() -> None:
    metrics = compute_topology_metrics(
        [
            TopologySpan(name="a", start_ms=0, end_ms=10),
            TopologySpan(name="b", start_ms=0, end_ms=10),
            TopologySpan(name="c", start_ms=10, end_ms=15, parent="a"),
        ],
        graph_version="g1",
        worker_count=2,
    )
    assert metrics.total_node_work_ms == 25
    assert metrics.elapsed_ms == 15
    assert metrics.observed_concurrency > 1
    assert any("worker_count" in n for n in metrics.notes)
