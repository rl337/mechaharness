from mechaharness.decision_log import DecisionRecord, export_offline_dataset
from mechaharness.learning_export import build_learning_export


def test_learning_export_pack() -> None:
    decisions = export_offline_dataset(
        [
            DecisionRecord(
                eventId="e1",
                stateHash="s",
                policyVersion="1",
                verdict="allow",
            )
        ],
        split="train",
    )
    pack = build_learning_export(
        decisions=decisions,
        harness_fingerprint="fp:1",
        rollout_graph_ref="rollout:1",
        evaluation_outcomes=[{"kind": "success"}],
    )
    assert pack.schema_version == "1"
    assert pack.harness_fingerprint == "fp:1"
    assert pack.decisions is not None
