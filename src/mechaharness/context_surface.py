"""Product library-surface runners (former context_management_probes.py)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

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


class ContextManagementParams(BaseModel):
    """Open params bag — each probe validates only what it needs."""

    model_config = ConfigDict(extra="allow")


def run_context_compiler_deficit(inputs: dict[str, Any]) -> dict[str, Any]:
    compiler = ContextCompiler(token_budget=int(inputs.get("token_budget", 8)))
    compiled = compiler.compile(
        state_revision=inputs.get("state_revision", "r1"),
        operation=inputs.get("operation", "chat"),
        sources=inputs.get("sources", {}),
        mandatory=inputs.get("mandatory", []),
        blockers=inputs.get("blockers", []),
        verification_obligations=inputs.get("verification_obligations", []),
    )
    return {
        "deficit": compiled.deficit,
        "unresolved_gaps": compiled.manifest.unresolved_gaps,
        "blockers": compiled.manifest.blockers,
        "silent_truncate": (
            not compiled.deficit
            and any(m in compiled.manifest.omitted for m in inputs.get("mandatory", []))
        ),
    }


def run_context_observation_chain(_inputs: dict[str, Any]) -> dict[str, Any]:
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
    return {
        "fabricated_receipt": bool(fake.fabricated),
        "fused": fused == ["edit", "test"],
        "compacted": len(compacted) < 10,
    }


def run_derived_memory(_inputs: dict[str, Any]) -> dict[str, Any]:
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
    return {
        "authority_outranks_popularity": bool(auth) and all(r.authority for r in auth),
        "idempotent": idempotent,
    }


def run_repo_topology(_inputs: dict[str, Any]) -> dict[str, Any]:
    topo = RepositoryTopologyProvider()
    view = topo.index(
        revision="r1",
        files={"a.py": "def foo():\n  pass\n", "b.py": "x"},
        budget=1,
    )
    return {
        "has_omissions_or_entries": bool(view.entries) or bool(view.omissions),
    }


def run_cache_layout_experiment(_inputs: dict[str, Any]) -> dict[str, Any]:
    layout = compile_cache_aware_layout(
        policy_blocks=["policy"],
        relevant=["ctx"],
        dynamic=["q"],
        flags=CtxFlags(cache_aware_layout=True),
        policy_version="v2",
    )
    return {"enabled_has_stable_prefix": bool(layout.stable_prefix)}


def run_context_provider_discovery(inputs: dict[str, Any]) -> dict[str, Any]:
    provider = StaticContextProvider(
        str(inputs["provider_id"]),
        {str(inputs["ref"]): str(inputs["content"])},
    )
    entries = provider.index(budget=8)
    chunks = provider.load([str(inputs["ref"])])
    return {
        "index_count": len(entries),
        "loaded_provider_id": chunks[0].provider_id if chunks else None,
        "token_estimate": chunks[0].token_estimate if chunks else 0,
    }


def run_instruction_gotcha_metrics(inputs: dict[str, Any]) -> dict[str, Any]:
    catalog = InstructionCatalog()
    gotcha = catalog.append_gotcha(
        str(inputs["title"]),
        str(inputs["body"]),
        provenance={"source": "client"},
    )
    if inputs.get("over_trigger"):
        gotcha.record_trigger(used=True, appropriate=False)
    else:
        gotcha.record_trigger(used=True, appropriate=True)
    catalog.promote(gotcha.id)
    return {
        "over_trigger_count": gotcha.over_trigger_count,
        "status_after_promote": gotcha.status,
        "active_gotcha_count": len(catalog.active(kind="gotcha")),
    }


def run_context_layers_project(inputs: dict[str, Any]) -> dict[str, Any]:
    shared = GraphSharedState(data=dict(inputs.get("shared") or {}))
    private = project_node_context(
        shared, needs=list(inputs.get("needs") or []), node_id="n1"
    )
    private.export_to_shared(shared, dict(inputs.get("exports") or {}))
    return {
        "projected_keys": list(private.data.keys()),
        "shared_has_result": "result" in shared.data,
        "projected_has_notes": "notes" in private.data,
    }


def run_context_compaction_staged(inputs: dict[str, Any]) -> dict[str, Any]:
    result = DefaultStagedCompaction().compact(
        CompactionInput(messages=list(inputs.get("messages") or []))
    )
    return {"discarded_classes": result.discarded_classes}


def run_context_structured_tool_delivery(inputs: dict[str, Any]) -> dict[str, Any]:
    """S1 produced→delivered check for structured tool evidence (MH-CTX-ATTR-01).

    Applies a character budget the same way distill truncation does, then
    fail-closes: invalid JSON after truncation is a disclosed deficit, never a
    silent success. Required fields missing from a valid delivery are named.
    """
    produced = inputs.get("produced")
    required_fields = [str(f) for f in (inputs.get("required_fields") or [])]
    max_chars = inputs.get("max_chars")
    observation_id = str(inputs.get("observation_id") or "obs:synthetic")
    structured = bool(inputs.get("structured", True))

    if isinstance(produced, (dict, list)):
        produced_text = json.dumps(produced, separators=(",", ":"), ensure_ascii=False)
    else:
        produced_text = str(produced if produced is not None else "")

    truncated = False
    delivered_text = produced_text
    budget = int(max_chars) if max_chars is not None else None
    if budget is not None and len(produced_text) > budget:
        # Match DefaultStagedCompaction distill: hard prefix + ellipsis.
        delivered_text = produced_text[:budget] + "…"
        truncated = True

    omitted_fields: list[str] = []
    payload_valid: bool | None = None
    deficit = False
    incomplete = False
    silent_truncate = False

    if structured:
        try:
            delivered_obj = json.loads(delivered_text)
            payload_valid = True
            if isinstance(delivered_obj, dict):
                for field in required_fields:
                    if field not in delivered_obj:
                        omitted_fields.append(field)
            elif required_fields:
                omitted_fields.extend(required_fields)
            if omitted_fields:
                deficit = True
                incomplete = True
        except json.JSONDecodeError:
            payload_valid = False
            deficit = True
            incomplete = True
            omitted_fields = list(required_fields)
            # Truncation that breaks JSON is disclosed, not silent.
            silent_truncate = False
    else:
        payload_valid = None
        if truncated:
            # Plain text may truncate; still record it as an explicit reduction.
            incomplete = True

    delivery_ok = (not deficit) and (payload_valid is not False)
    return {
        "observation_id": observation_id,
        "produced_chars": len(produced_text),
        "delivered_chars": len(delivered_text),
        "delivered_content": delivered_text,
        "truncated": truncated,
        "payload_valid": payload_valid,
        "omitted_fields": omitted_fields,
        "deficit": deficit,
        "incomplete": incomplete,
        "silent_truncate": silent_truncate,
        "delivery_ok": delivery_ok,
    }


def run_context_evidence_survival(inputs: dict[str, Any]) -> dict[str, Any]:
    """Boundary counts for evidence survival (MH-CTX-ATTR-02).

    Deterministic fixture probe: hosts pass produced/delivered/retained/
    transferred/persisted observation ids. A transferred id that was never
    produced is a false transfer. Yield is unique transferred / unique produced.
    """
    def _unique(ids: Any) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in ids or []:
            item = str(raw)
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    produced = _unique(inputs.get("produced_ids"))
    delivered = _unique(inputs.get("delivered_ids"))
    retained = _unique(inputs.get("retained_ids"))
    transferred = _unique(inputs.get("transferred_ids"))
    persisted = _unique(inputs.get("persisted_ids"))

    produced_set = set(produced)
    false_transferred = [t for t in transferred if t not in produced_set]
    transfer_yield = (len(transferred) / len(produced)) if produced else 0.0

    return {
        "produced_count": len(produced),
        "delivered_count": len(delivered),
        "retained_count": len(retained),
        "transferred_count": len(transferred),
        "persisted_count": len(persisted),
        "false_transfer": bool(false_transferred),
        "false_transferred_ids": false_transferred,
        "transfer_yield": transfer_yield,
        "payload_valid": bool(inputs.get("payload_valid", True)),
        "required_field_survival": bool(inputs.get("required_field_survival", True)),
    }


def run_anchor_evidence_require(inputs: dict[str, Any]) -> dict[str, Any]:
    req = AnchorRequirement(
        kinds=list(inputs.get("kinds") or []),
        min_count=int(inputs.get("min_count") or 1),
    )
    anchors = [AnchorEvidence.model_validate(a) for a in inputs.get("anchors") or []]
    return {"satisfied": anchors_satisfied(req, anchors)}


def run_instruction_scope_metadata(inputs: dict[str, Any]) -> dict[str, Any]:
    comp = InstructionComponent(
        kind="procedure",
        title=str(inputs.get("title") or "t"),
        body=str(inputs.get("body") or ""),
        scope=inputs.get("scope"),
        authority=inputs.get("authority"),
        estimated_context_cost=inputs.get("estimated_context_cost"),
    )
    return {
        "scope": comp.scope,
        "estimated_context_cost": comp.estimated_context_cost,
    }


CONTEXT_MANAGEMENT_HANDLERS: dict[str, Any] = {
    "context_compiler_deficit": run_context_compiler_deficit,
    "context_observation_chain": run_context_observation_chain,
    "derived_memory": run_derived_memory,
    "repo_topology": run_repo_topology,
    "cache_layout_experiment": run_cache_layout_experiment,
    "context_provider_discovery": run_context_provider_discovery,
    "instruction_gotcha_metrics": run_instruction_gotcha_metrics,
    "context_layers_project": run_context_layers_project,
    "context_compaction_staged": run_context_compaction_staged,
    "context_structured_tool_delivery": run_context_structured_tool_delivery,
    "context_evidence_survival": run_context_evidence_survival,
    "anchor_evidence_require": run_anchor_evidence_require,
    "instruction_scope_metadata": run_instruction_scope_metadata,
}


__all__ = ['CONTEXT_MANAGEMENT_HANDLERS', 'ContextManagementParams']
