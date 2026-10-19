from mechaharness.handoff_record import HandoffRecord


def test_fields():
    assert HandoffRecord(next_action="go").next_action=="go"


def test_goals_exclusions_and_verdict_are_first_class() -> None:
    rec = HandoffRecord(
        goals=["ship report"],
        exclusions=["no customer email"],
        verdict={"kind": "ASK_HUMAN", "policyVersion": "1"},
    )
    assert rec.goals == ["ship report"]
    assert rec.exclusions == ["no customer email"]
    assert rec.verdict == {"kind": "ASK_HUMAN", "policyVersion": "1"}
    assert {"goals", "exclusions", "verdict"} <= set(HandoffRecord.model_fields)


def test_old_handoff_payload_still_validates() -> None:
    rec = HandoffRecord.model_validate({"completed": ["a"], "detail": {"goals": ["legacy"]}})
    assert rec.goals == [] and rec.verdict is None and rec.detail["goals"] == ["legacy"]
