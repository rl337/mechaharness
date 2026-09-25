"""CTX context-experiment tests including CTX-05–09."""

from __future__ import annotations

from mechaharness.context_experiments import (
    ContextCompiler,
    CtxFlags,
    DerivedMemoryRecord,
    DerivedMemoryStore,
    ObservationRef,
    ObservationStore,
    RepositoryTopologyProvider,
    compact_at_boundary,
    compile_cache_aware_layout,
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


def test_context_compiler_overflow_and_deterministic() -> None:
    compiler = ContextCompiler(token_budget=5)
    compiled = compiler.compile(
        state_revision="r1",
        operation="chat",
        sources={"big": "word " * 40, "must": "also large " * 40},
        mandatory=["must"],
    )
    assert compiled.deficit is True
    assert "must" in compiled.manifest.unresolved_gaps
    det = compiler.compile(
        state_revision="r1",
        operation="parse",
        sources={},
        needs_prompt=False,
    )
    assert det.payload.get("deterministic") is True


def test_derived_memory_rebuild_and_authority() -> None:
    store = DerivedMemoryStore()
    events = [
        {"id": "e1", "content": "Redis"},
        {"id": "e2", "content": "Dragonfly"},
        {"id": "e3", "content": "Redis"},
    ]
    store.consolidate_from(events, up_to=2)
    assert len(store.current()) == 2
    store.consolidate_from(events, up_to=2)  # idempotent
    assert len(store.current()) == 2
    store.rebuild(events)
    assert len(store.current()) == 3
    popular = DerivedMemoryRecord(content="rumor", retrieval_rank=99, authority=False)
    rule = DerivedMemoryRecord(content="approval-rule", retrieval_rank=0, authority=True)
    store.apply("add", popular)
    store.apply("add", rule)
    store._published[popular.id] = popular
    store._published[rule.id] = rule
    ranked = store.retrieval_candidates()
    assert ranked[0].content == "rumor"
    auth = store.current(authoritative_only=True)
    assert all(r.authority for r in auth)


def test_topology_and_cache_layout() -> None:
    topo = RepositoryTopologyProvider()
    view = topo.index(
        revision="r1",
        files={"a.py": "def foo():\n  pass\n", "b.py": "x"},
        budget=1,
    )
    assert len(view.entries) == 1
    assert "b.py" in view.omissions
    assert topo.source("r1", "a.py") is not None
    layout = compile_cache_aware_layout(
        policy_blocks=["policy"],
        relevant=["ctx"],
        dynamic=["q"],
        flags=CtxFlags(cache_aware_layout=True),
        policy_version="v2",
    )
    assert layout.stable_prefix == ["policy"]
    assert layout.prefix_identity == "policy:v2"
