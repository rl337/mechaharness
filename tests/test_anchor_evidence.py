from mechaharness.anchor_evidence import AnchorEvidence, AnchorRequirement, anchors_satisfied

def test_anchor():
    assert anchors_satisfied(AnchorRequirement(kinds=["external_observation"], min_count=1), [AnchorEvidence(kind="external_observation", ref="o")])
