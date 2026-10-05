from mechaharness.context_compaction import CompactionInput, DefaultStagedCompaction


def test_dedupe() -> None:
    messages = [
        {"role": "user", "content": "a"},
        {"role": "user", "content": "a"},
    ]
    result = DefaultStagedCompaction().compact(CompactionInput(messages=messages))
    assert "deduplicated" in result.discarded_classes
