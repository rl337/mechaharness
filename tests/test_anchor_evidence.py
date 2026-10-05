from mechaharness.anchor_evidence import (
    AnchorEvidence,
    AnchorRequirement,
    anchors_satisfied,
)


def test_anchor() -> None:
    req = AnchorRequirement(kinds=["external_observation"], min_count=1)
    anchors = [AnchorEvidence(kind="external_observation", ref="o")]
    assert anchors_satisfied(req, anchors)
