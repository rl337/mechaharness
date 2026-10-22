from mechaharness.instruction_plan import build_instruction_plan, classify_mode

def test_oneshot_from_goal():
    result = build_instruction_plan({"goal": "do thing"})
    assert result.plan is not None
    assert result.plan.mode == "oneshot"
    assert len(result.plan.items) == 1
    assert result.plan.items[0].instruction == "do thing"

def test_list_from_numbered_instructions():
    result = build_instruction_plan({
        "instructions": "1. add helper\n2. add test\n3. update docs"
    })
    assert result.plan.mode == "list"
    assert len(result.plan.items) == 3
    assert result.plan.items[0].instruction == "add helper"
    assert result.plan.items[1].instruction == "add test"
    assert result.plan.items[2].instruction == "update docs"

def test_conflicting_instructions():
    result = build_instruction_plan({
        "instructions": ["delete foo", "keep foo"]
    })
    assert result.plan is None
    assert len(result.guidance) == 1
    assert result.guidance[0].context_version == "list_refinement"

def test_explicit_list_mode():
    result = build_instruction_plan({
        "instruction_mode": "list",
        "instructions": ["item1", "item2"]
    })
    assert result.plan.mode == "list"

def test_classify_mode_auto_list():
    instructions = "1. add helper\n2. add test\n3. update docs"
    assert classify_mode({"instructions": instructions}) == "list"