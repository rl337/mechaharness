from mechaharness.cross_harness_failure import classify_cross_harness_failure


def test_classify_axes() -> None:
    assert classify_cross_harness_failure("unknown tool foobar").kind == "invalid_tool_name"
    assert classify_cross_harness_failure("schema validation error").kind == "invalid_tool_schema"
    assert classify_cross_harness_failure("wrong answer").kind == "semantic_task_failure"
    claim = classify_cross_harness_failure("unsupported capability").to_claim()
    assert claim.detail["cross_harness_kind"] == "unsupported_capability"
