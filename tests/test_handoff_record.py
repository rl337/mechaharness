from mechaharness.handoff_record import HandoffRecord


def test_fields():
    assert HandoffRecord(next_action="go").next_action=="go"
