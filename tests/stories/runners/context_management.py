"""Context compiler, provider, instruction, and compaction story runners."""

from __future__ import annotations

from mechaharness.anchor_evidence import AnchorEvidence, AnchorRequirement, anchors_satisfied
from mechaharness.context_compaction import CompactionInput, DefaultStagedCompaction
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
from mechaharness.context_layers import GraphSharedState, project_node_context
from mechaharness.context_provider import StaticContextProvider
from mechaharness.instruction_component import InstructionCatalog, InstructionComponent
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.runners._support import StoryRunner, _assert_expect


async def _run_context_compiler_deficit(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    compiler = ContextCompiler(token_budget=int(request.get("token_budget", 8)))
    compiled = compiler.compile(
        state_revision=request.get("state_revision", "r1"),
        operation=request.get("operation", "chat"),
        sources=request.get("sources", {}),
        mandatory=request.get("mandatory", []),
        blockers=request.get("blockers", []),
        verification_obligations=request.get("verification_obligations", []),
    )
    actual = {
        "deficit": compiled.deficit,
        "unresolved_gaps_include": compiled.manifest.unresolved_gaps,
        "blockers_include": compiled.manifest.blockers,
        "silent_truncate": (
            not compiled.deficit
            and any(m in compiled.manifest.omitted for m in request.get("mandatory", []))
        ),
    }
    _assert_expect(actual, expect)


async def _run_context_observation_chain(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    store = ObservationStore()
    store.put(ObservationRef(tool_name="comfy", content="raw bytes"))
    flags = CtxFlags(
        evidence_reduction=True, economic_compaction=True, action_fusion=True
    )
    fake = reduce_evidence(store, "obs:missing", summary="lie", flags=flags)
    fused = fuse_actions(
        ["edit", "test"], allowed_sequences=[["edit", "test"]], flags=flags
    )
    compacted = compact_at_boundary(
        [{"role": "user", "content": str(i)} for i in range(10)],
        flags=flags,
        keep_last=2,
    )
    actual = {
        "fabricated_receipt": bool(fake.fabricated),
        "fused": fused == ["edit", "test"],
        "compacted": len(compacted) < 10,
    }
    _assert_expect(actual, expect)


async def _run_derived_memory(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    store = DerivedMemoryStore()
    events = [
        {"id": "e1", "content": "Redis"},
        {"id": "e2", "content": "Dragonfly"},
        {"id": "e3", "content": "Redis"},
    ]
    store.consolidate_from(events, up_to=2)
    first = len(store.current())
    store.consolidate_from(events, up_to=2)
    idempotent = len(store.current()) == first
    popular = DerivedMemoryRecord(content="rumor", retrieval_rank=99, authority=False)
    rule = DerivedMemoryRecord(content="approval-rule", retrieval_rank=0, authority=True)
    store.apply("add", popular)
    store.apply("add", rule)
    store._published[popular.id] = popular
    store._published[rule.id] = rule
    auth = store.current(authoritative_only=True)
    actual = {
        "authority_outranks_popularity": bool(auth) and all(r.authority for r in auth),
        "idempotent": idempotent,
    }
    _assert_expect(actual, expect)


async def _run_repo_topology(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    topo = RepositoryTopologyProvider()
    view = topo.index(
        revision="r1",
        files={"a.py": "def foo():\n  pass\n", "b.py": "x"},
        budget=1,
    )
    actual = {
        "has_omissions_or_entries": bool(view.entries) or bool(view.omissions),
    }
    _assert_expect(actual, expect)


async def _run_cache_layout_experiment(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    layout = compile_cache_aware_layout(
        policy_blocks=["policy"],
        relevant=["ctx"],
        dynamic=["q"],
        flags=CtxFlags(cache_aware_layout=True),
        policy_version="v2",
    )
    actual = {"enabled_has_stable_prefix": bool(layout.stable_prefix)}
    _assert_expect(actual, expect)


async def _run_context_provider_discovery(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    provider = StaticContextProvider(
        str(request["provider_id"]),
        {str(request["ref"]): str(request["content"])},
    )
    entries = provider.index(budget=8)
    chunks = provider.load([str(request["ref"])])
    actual = {
        "index_count": len(entries),
        "loaded_provider_id": chunks[0].provider_id if chunks else None,
        "token_estimate_min": chunks[0].token_estimate if chunks else 0,
    }
    _assert_expect(actual, expect)


async def _run_instruction_gotcha_metrics(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    catalog = InstructionCatalog()
    gotcha = catalog.append_gotcha(
        str(request["title"]),
        str(request["body"]),
        provenance={"source": "client"},
    )
    if request.get("over_trigger"):
        gotcha.record_trigger(used=True, appropriate=False)
    else:
        gotcha.record_trigger(used=True, appropriate=True)
    catalog.promote(gotcha.id)
    actual = {
        "over_trigger_count": gotcha.over_trigger_count,
        "status_after_promote": gotcha.status,
        "active_gotcha_count": len(catalog.active(kind="gotcha")),
    }
    _assert_expect(actual, expect)


async def _run_context_layers_project(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    shared = GraphSharedState(data=dict(request.get("shared") or {}))
    private = project_node_context(
        shared, needs=list(request.get("needs") or []), node_id="n1"
    )
    private.export_to_shared(shared, dict(request.get("exports") or {}))
    actual = {
        "projected_keys_include": list(private.data.keys()),
        "shared_has_result": "result" in shared.data,
        "projected_has_notes": "notes" in private.data,
    }
    _assert_expect(actual, expect)


async def _run_context_compaction_staged(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    result = DefaultStagedCompaction().compact(
        CompactionInput(messages=list(request.get("messages") or []))
    )
    actual = {"discarded_include": result.discarded_classes}
    _assert_expect(actual, expect)


async def _run_anchor_evidence_require(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    req = AnchorRequirement(
        kinds=list(request.get("kinds") or []),
        min_count=int(request.get("min_count") or 1),
    )
    anchors = [AnchorEvidence.model_validate(a) for a in request.get("anchors") or []]
    actual = {"satisfied": anchors_satisfied(req, anchors)}
    _assert_expect(actual, expect)


async def _run_instruction_scope_metadata(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    comp = InstructionComponent(
        kind="procedure",
        title=str(request.get("title") or "t"),
        body=str(request.get("body") or ""),
        scope=request.get("scope"),
        authority=request.get("authority"),
        estimated_context_cost=request.get("estimated_context_cost"),
    )
    actual = {
        "scope": comp.scope,
        "estimated_context_cost": comp.estimated_context_cost,
    }
    _assert_expect(actual, expect)



RUNNERS: dict[str, StoryRunner] = {
    "context_compiler_deficit": _run_context_compiler_deficit,
    "context_observation_chain": _run_context_observation_chain,
    "derived_memory": _run_derived_memory,
    "repo_topology": _run_repo_topology,
    "cache_layout_experiment": _run_cache_layout_experiment,
    "context_provider_discovery": _run_context_provider_discovery,
    "instruction_gotcha_metrics": _run_instruction_gotcha_metrics,
    "context_layers_project": _run_context_layers_project,
    "context_compaction_staged": _run_context_compaction_staged,
    "anchor_evidence_require": _run_anchor_evidence_require,
    "instruction_scope_metadata": _run_instruction_scope_metadata,
}
