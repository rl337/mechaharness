"""CTX context-experiment tests."""

from __future__ import annotations

from mechaharness.context_experiments import (
    CtxFlags,
    ObservationRef,
    ObservationStore,
    compact_at_boundary,
    fuse_actions,
    reduce_evidence,
)


def test_ctx_flags_default_off_and_provenance() -> None:
    store = ObservationStore()
    ref = store.put(ObservationRef(tool_name="comfy", content="raw bytes"))
    flags = CtxFlags(
        evidence_reduction=True, economic_compaction=True, action_fusion=True
    )
    receipt = reduce_evidence(store, ref.id, summary="ok", flags=flags)
    assert receipt.fabricated is False
    fake = reduce_evidence(store, "obs:missing", summary="lie", flags=flags)
    assert fake.fabricated is True
    compacted = compact_at_boundary(
        [{"role": "user", "content": str(i)} for i in range(10)],
        flags=flags,
        keep_last=2,
    )
    assert len(compacted) < 10
    assert fuse_actions(
        ["edit", "test"], allowed_sequences=[["edit", "test"]], flags=flags
    ) == ["edit", "test"]
    assert (
        fuse_actions(
            ["edit", "test"], allowed_sequences=[["edit", "test"]], flags=CtxFlags()
        )
        is None
    )
