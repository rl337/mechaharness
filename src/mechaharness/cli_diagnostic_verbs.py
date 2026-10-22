"""Host diagnostic CLI verbs (routing, parity, manifest replay, shadow).

These are product-facing diagnostics hosts may run from the CLI instrumentor;
story YAML reuses the same verbs with hard expects.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.harness.base import HarnessConfig
from mechaharness.inference.judge import NoulSignal
from mechaharness.judgement_policy import (
    JudgementFacts,
    JudgementPolicy,
    JudgementThreshold,
)
from mechaharness.model_input_manifest import (
    ModelInputManifest,
    attach_manifest_ref,
    reconstruct_messages,
)
from mechaharness.routing import (
    activate_scoped_policy,
    route_at_boundary,
    route_for_capability_needs,
    shadow_decision_backends,
)
from mechaharness.run_parity import compare_parity, parity_from_harness_config


class ReplayModelInputCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[dict[str, Any]] = Field(default_factory=list)
    tool_definitions: list[dict[str, Any]] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)


class RouteCapabilitiesCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_needs: list[str] = Field(default_factory=list)
    available_model_classes: list[str] = Field(default_factory=list)


class CheckModelAffinityCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompareRunParityCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: dict[str, Any]
    b: dict[str, Any]


class ShadowDecisionBackendsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_hash: str
    candidate_actions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    backends: dict[str, dict[str, Any]] = Field(default_factory=dict)


def run_replay_model_input(body: ReplayModelInputCommand) -> dict[str, Any]:
    messages = list(body.messages)
    manifest = ModelInputManifest.from_parts(
        messages=messages,
        tool_definitions=list(body.tool_definitions),
        instructions=list(body.instructions),
    )
    reconstructed = reconstruct_messages(manifest)
    fields = attach_manifest_ref({}, manifest)
    return {
        "hashes_ok": manifest.verify_hashes(),
        "reconstructed_equals": reconstructed == messages,
        "manifest_ref_nonempty": bool(fields.get("context_manifest_ref")),
    }


def run_route_capabilities(body: RouteCapabilitiesCommand) -> dict[str, Any]:
    route = route_for_capability_needs(
        capability_needs=list(body.capability_needs),
        available_model_classes=list(body.available_model_classes),
    )
    return {"selected_model_class": route["selected_model_class"]}


def run_check_model_affinity(_body: CheckModelAffinityCommand) -> dict[str, Any]:
    decision = route_at_boundary(boundary="task_entry", task_kind="judge")
    policy = JudgementPolicy(
        version="v1",
        thresholds=[JudgementThreshold(signal_id="e", allow_above=0.5)],
    )
    uncalibrated = activate_scoped_policy(
        facts=JudgementFacts(),
        signals=[NoulSignal(id="e", p_true=0.9)],
        policy=policy,
        calibrated=False,
    )
    return {
        "selected_lane": decision.selected.lane,
        "uncalibrated_is_null": uncalibrated is None,
    }


def _parity_surface(raw: dict[str, Any]) -> Any:
    cfg = HarnessConfig(
        model=str(raw["model"]),
        max_tokens=raw.get("max_tokens"),
        temperature=raw.get("temperature"),
        max_turns=int(raw.get("max_turns") or 8),
    )
    env = CapabilityEnvelope(tool_names=list(raw.get("tools") or []))
    return parity_from_harness_config(cfg, envelope=env)


def run_compare_run_parity(body: CompareRunParityCommand) -> dict[str, Any]:
    report = compare_parity(_parity_surface(body.a), _parity_surface(body.b))
    return {
        "comparable": report.comparable,
        "material_mismatches_exactly": list(report.material_mismatches),
    }


def run_shadow_decision_backends(
    body: ShadowDecisionBackendsCommand,
) -> dict[str, Any]:
    report = shadow_decision_backends(
        state_hash=body.state_hash,
        candidate_actions=list(body.candidate_actions),
        evidence_refs=list(body.evidence_refs),
        backends=body.backends,  # type: ignore[arg-type]
    )
    by_kind = {c.kind: c for c in report.candidates}
    unavailable = sorted(
        k for k, c in by_kind.items() if not c.available and c.latency_ms is None
    )
    available = sorted(k for k, c in by_kind.items() if c.available)
    matched = list(report.matched_inputs.get("candidate_actions") or [])
    return {
        "unavailable_exactly": unavailable,
        "available_exactly": available,
        "matched_actions_exactly": matched,
    }


__all__ = [
    "CheckModelAffinityCommand",
    "CompareRunParityCommand",
    "ReplayModelInputCommand",
    "RouteCapabilitiesCommand",
    "ShadowDecisionBackendsCommand",
    "run_check_model_affinity",
    "run_compare_run_parity",
    "run_replay_model_input",
    "run_route_capabilities",
    "run_shadow_decision_backends",
]
