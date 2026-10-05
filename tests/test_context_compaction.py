from mechaharness.context_compaction import CompactionInput, DefaultStagedCompaction

def test_dedupe():
    r = DefaultStagedCompaction().compact(CompactionInput(messages=[{"role":"user","content":"a"},{"role":"user","content":"a"}]))
    assert "deduplicated" in r.discarded_classes
