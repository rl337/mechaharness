"""Pure classifier edges kept as unit tests (not durable user_story walks)."""

from mechaharness.instruction_plan import classify_mode


def test_classify_mode_auto_list() -> None:
    instructions = "1. add helper\n2. add test\n3. update docs"
    assert classify_mode({"instructions": instructions}) == "list"


def test_classify_mode_oneshot_goal() -> None:
    assert classify_mode({"goal": "do thing"}) == "oneshot"


def test_classify_mode_explicit_list() -> None:
    assert (
        classify_mode(
            {"instruction_mode": "list", "instructions": ["item1", "item2"]}
        )
        == "list"
    )
