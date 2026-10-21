"""Product CLI verb: decision-plane case plans for JEV / host judgement walks.

One verb (``decision_case``) loads a human-readable YAML plan whose ``case:``
field selects the check — JEV cases, recipe shape, projection, policy,
shadow, telemetry, or model soft-point binding. Stories and hosts share the
same document shape under ``plans/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Union, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.cli_verb import CliVerb
from mechaharness.core.access import AccessPolicy
from mechaharness.decision_plane_runtime import (
    assemble_context_within_budget,
    build_decision_plane_telemetry,
    compare_shadow_decision,
    project_decision_state,
    run_decision_plane_policy,
)
from mechaharness.graph_templates import (
    DecisionPlaneTemplate,
    GraphTemplateParams,
    IndependentReviewTemplate,
)

CaseKind = Literal[
    "citation_support",
    "context_budget",
    "requirements_gap",
    "task_route",
    "action_safety",
    "plane_recipe",
    "projection",
    "policy",
    "shadow",
    "telemetry",
    "model_policy",
]

_LEGACY_PROBE_NAMES: dict[str, CaseKind] = {
    "citation_support_case": "citation_support",
    "context_budget_case": "context_budget",
    "requirements_gap_case": "requirements_gap",
    "task_route_case": "task_route",
    "action_safety_case": "action_safety",
    "decision_plane_recipe": "plane_recipe",
    "decision_plane_projection": "projection",
    "decision_plane_policy_case": "policy",
    "decision_plane_shadow": "shadow",
    "decision_plane_telemetry": "telemetry",
    "decision_plane_model_policy": "model_policy",
}


class CitationSupportCase(BaseModel):
    """Bounded support choice → claim_verified (MH-JEV citation)."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["citation_support"] = "citation_support"
    summary: str = ""
    questions: list[dict[str, Any]] = Field(default_factory=list)
    action_question_id: str = "support"
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_floor: float = 0.7

    async def run(self) -> dict[str, Any]:
        result = await run_decision_plane_policy(
            questions=list(self.questions),
            answers=dict(self.answers),
            confidence=self.confidence,
            confidence_floor=self.confidence_floor,
            action_question_id=self.action_question_id,
        )
        claim_verified = not result.escalate and result.final_action == "supported"
        return {
            "summary": self.summary,
            "claim_verified": claim_verified,
            "escalate": result.escalate,
            "final_action": result.final_action,
        }


class ContextBudgetCase(BaseModel):
    """Pack scored RAG candidates under host thresholds (DP-04)."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["context_budget"] = "context_budget"
    summary: str = ""
    token_budget: int
    min_relevance: float = 0.0
    min_trust: float = 0.0
    min_freshness: float = 0.0
    candidates: list[dict[str, Any]] = Field(default_factory=list)

    async def run(self) -> dict[str, Any]:
        selected = assemble_context_within_budget(
            list(self.candidates),
            token_budget=self.token_budget,
            min_relevance=self.min_relevance,
            min_trust=self.min_trust,
            min_freshness=self.min_freshness,
        )
        by_id = {str(c["id"]): c for c in self.candidates}
        total = sum(int(by_id[cid]["tokens"]) for cid in selected)
        return {
            "summary": self.summary,
            "selected_ids": selected,
            "token_total": total,
            "within_budget": total <= self.token_budget,
        }


class RequirementsGapCase(BaseModel):
    """Independent-review shape + decision_plane coverage/gap outcome."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["requirements_gap"] = "requirements_gap"
    summary: str = ""
    reviewer_count: int = 1
    acceptance: list[Any] = Field(default_factory=list)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    action_question_id: str = "coverage"
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_floor: float = 0.7
    facts: dict[str, Any] = Field(default_factory=dict)

    async def run(self) -> dict[str, Any]:
        review_graph = IndependentReviewTemplate().instantiate(
            GraphTemplateParams(
                goal="requirements review",
                inputs={"reviewer_count": self.reviewer_count},
                acceptance=list(self.acceptance),
            )
        )
        reviews = [n for n in review_graph.nodes if n.startswith("review_")]
        result = await run_decision_plane_policy(
            questions=list(self.questions),
            answers=dict(self.answers),
            confidence=self.confidence,
            confidence_floor=self.confidence_floor,
            action_question_id=self.action_question_id,
        )
        facts = dict(self.facts)
        if result.escalate or result.final_action in {"gap", "unclear"}:
            outcome = "request_tests"
        elif not facts.get("crash_tests_present", True):
            outcome = "request_tests"
        elif result.final_action == "covered":
            outcome = "continue_review"
        else:
            outcome = "request_tests"
        return {
            "summary": self.summary,
            "template_name": review_graph.template_name,
            "omit_producer_reasoning": review_graph.nodes[reviews[0]].payload.get(
                "omit_producer_reasoning"
            ),
            "outcome": outcome,
            "final_action": result.final_action,
            "escalate": result.escalate,
        }


class TaskRouteCase(BaseModel):
    """Bounded route choice with optional host quality override."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["task_route"] = "task_route"
    summary: str = ""
    questions: list[dict[str, Any]] = Field(default_factory=list)
    action_question_id: str = "route"
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_floor: float = 0.7
    min_complexity_for_frontier: float = 0.7

    async def run(self) -> dict[str, Any]:
        result = await run_decision_plane_policy(
            questions=list(self.questions),
            answers=dict(self.answers),
            confidence=self.confidence,
            confidence_floor=self.confidence_floor,
            action_question_id=self.action_question_id,
        )
        complexity = float(self.answers.get("complexity") or 0.0)
        final_action = result.final_action
        escalate = result.escalate
        if (
            not escalate
            and final_action == "local_small"
            and complexity >= self.min_complexity_for_frontier
        ):
            final_action = "frontier"
        return {
            "summary": self.summary,
            "final_action": final_action,
            "escalate": escalate,
        }


class ActionSafetyCase(BaseModel):
    """Hard grants win over semantic risk classification (MH-JEV-05)."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["action_safety"] = "action_safety"
    summary: str = ""
    questions: list[dict[str, Any]] = Field(default_factory=list)
    action_question_id: str = "semantic_risk"
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_floor: float = 0.7
    grants: list[Any] = Field(default_factory=list)
    required_grants: list[Any] = Field(default_factory=list)

    async def run(self) -> dict[str, Any]:
        policy = AccessPolicy(grants=list(self.grants))
        required = list(self.required_grants)
        grants_ok = policy.allows(required) if required else True
        result = await run_decision_plane_policy(
            questions=list(self.questions),
            answers=dict(self.answers),
            confidence=self.confidence,
            confidence_floor=self.confidence_floor,
            action_question_id=self.action_question_id,
        )
        risk = result.final_action
        if not grants_ok:
            decision = "deny"
            hard_won = True
        elif result.escalate or risk == "high":
            decision = "escalate_review"
            hard_won = False
        else:
            decision = "allow"
            hard_won = False
        return {
            "summary": self.summary,
            "decision": decision,
            "hard_won": hard_won,
            "grants_unchanged": list(policy.grants) == list(self.grants),
            "escalate": result.escalate,
            "final_action": result.final_action,
        }


class PlaneRecipeCase(BaseModel):
    """Instantiate Agentic Recipe ``decision_plane`` and inspect shape."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["plane_recipe"] = "plane_recipe"
    summary: str = ""
    goal: str = "decision_plane"
    state_projection: dict[str, Any] = Field(default_factory=dict)
    facts: dict[str, Any] = Field(default_factory=dict)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    confidence_floor: float = 0.7
    shadow_mode: bool = False

    async def run(self) -> dict[str, Any]:
        graph = DecisionPlaneTemplate().instantiate(
            GraphTemplateParams(
                goal=self.goal,
                inputs={
                    "state_projection": dict(self.state_projection),
                    "facts": dict(self.facts),
                    "questions": list(self.questions),
                    "confidence_floor": self.confidence_floor,
                    "shadow_mode": self.shadow_mode,
                },
            )
        )
        ask = graph.nodes["ask_batch"]
        project = graph.nodes["project_state"]
        return {
            "summary": self.summary,
            "template_name": graph.template_name,
            "nodes": sorted(graph.nodes),
            "ask_batch_question_count": len(ask.payload.get("questions") or []),
            "facts_on_project_not_ask": "facts" in project.payload
            and "facts" not in ask.payload,
            "confidence_floor": ask.payload.get("confidence_floor"),
        }


class ProjectionCase(BaseModel):
    """Project decision state and facts without calling a model."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["projection"] = "projection"
    summary: str = ""
    raw_context: dict[str, Any] = Field(default_factory=dict)
    project_keys: list[str] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)

    async def run(self) -> dict[str, Any]:
        proj = project_decision_state(
            dict(self.raw_context),
            project_keys=list(self.project_keys),
            facts=dict(self.facts),
        )
        return {
            "summary": self.summary,
            "projection": proj.state,
            "facts": list(proj.facts),
            "projection_has_secret": "secret" in proj.state,
            "no_model_invocation": True,
            "facts_fingerprint_nonempty": bool(proj.facts_fingerprint),
        }


class PolicyCase(BaseModel):
    """Code-owned final action with escalation (DP-02 / DP-03)."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["policy"] = "policy"
    summary: str = ""
    questions: list[dict[str, Any]] = Field(default_factory=list)
    escalation_route: str = "host_policy"
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    confidence_floor: float = 0.7
    action_question_id: str | None = None

    async def run(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "questions": list(self.questions),
            "answers": dict(self.answers),
            "confidence": self.confidence,
            "confidence_floor": self.confidence_floor,
            "escalation_route": self.escalation_route,
        }
        if self.action_question_id is not None:
            kwargs["action_question_id"] = self.action_question_id
        result = await run_decision_plane_policy(**kwargs)
        return {
            "summary": self.summary,
            "final_action": result.final_action,
            "escalate": result.escalate,
            "escalation_reason": result.escalation_reason,
            "escalation_route": result.escalation_route,
            "batch_invocation_count": result.batch_invocation_count,
        }


class ShadowCase(BaseModel):
    """Shadow a candidate model without giving it control (DP-07)."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["shadow"] = "shadow"
    summary: str = ""
    questions: list[dict[str, Any]] = Field(default_factory=list)
    production_answers: dict[str, Any] = Field(default_factory=dict)
    shadow_answers: dict[str, Any] | None = None
    confidence: float | None = None
    confidence_floor: float = 0.7

    async def run(self) -> dict[str, Any]:
        cmp = await compare_shadow_decision(
            questions=list(self.questions),
            production_answers=dict(self.production_answers),
            shadow_answers=self.shadow_answers,
            confidence=self.confidence,
            confidence_floor=self.confidence_floor,
        )
        return {
            "summary": self.summary,
            "production_action": cmp.production.final_action,
            "shadow_controls_execution": cmp.shadow_controls_execution,
            "both_outcomes_recorded": cmp.shadow is not None,
            "agreement": cmp.agreement,
            "shadow_unavailable": cmp.shadow_unavailable,
            "shadow_action": cmp.shadow.final_action if cmp.shadow is not None else None,
        }


class TelemetryCase(BaseModel):
    """Evaluation-ready telemetry without raw sensitive context (DP-08)."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["telemetry"] = "telemetry"
    summary: str = ""
    questions: list[dict[str, Any]] = Field(default_factory=list)
    state_projection: dict[str, Any] = Field(default_factory=dict)
    answers: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    final_action: str | None = None
    model_ref: str | None = None
    latency_ms: float | None = None
    raw_body: Any = None

    async def run(self) -> dict[str, Any]:
        questions = list(self.questions)
        proj = project_decision_state(
            {**dict(self.state_projection), "body": self.raw_body},
            project_keys=list(self.state_projection.keys()),
            facts={},
        )
        policy = await run_decision_plane_policy(
            questions=questions,
            answers=dict(self.answers),
            confidence=self.confidence,
            confidence_floor=0.7,
        )
        if self.final_action and not policy.escalate:
            policy.final_action = self.final_action
        tel = build_decision_plane_telemetry(
            questions=questions,
            projection=proj,
            policy=policy,
            model_ref=self.model_ref,
            latency_ms=self.latency_ms,
            raw_context={"body": self.raw_body},
        )
        dumped = tel.model_dump(mode="json")
        return {
            "summary": self.summary,
            "has_question_schema_ids": bool(tel.question_schema_ids),
            "has_projection_fingerprint": bool(tel.projection_fingerprint),
            "final_action": tel.final_action,
            "model_ref": tel.model_ref,
            "latency_ms": tel.latency_ms,
            "includes_raw_body": "raw_body" in dumped or "body" in dumped,
        }


class ModelPolicyCase(BaseModel):
    """Bind ``decision_model`` soft point without baking size into the recipe."""

    model_config = ConfigDict(extra="forbid")

    case: Literal["model_policy"] = "model_policy"
    summary: str = ""
    state_projection: dict[str, Any] = Field(default_factory=dict)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    decision_model: Any = None

    async def run(self) -> dict[str, Any]:
        template = DecisionPlaneTemplate()
        graph = template.instantiate(
            GraphTemplateParams(
                goal="model policy",
                inputs={
                    "state_projection": dict(self.state_projection),
                    "questions": list(self.questions),
                },
                soft_bindings={"decision_model": self.decision_model},
            )
        )
        describe = template.describe()
        return {
            "summary": self.summary,
            "soft_point_decision_model": any(
                p.get("name") == "decision_model"
                for p in describe.get("soft_points") or []
            ),
            "ask_model_ref": graph.nodes["ask_batch"].payload.get("model_ref"),
            "describe_has_param_count": "param_count" in describe,
        }


DecisionCaseDocument = Union[
    CitationSupportCase,
    ContextBudgetCase,
    RequirementsGapCase,
    TaskRouteCase,
    ActionSafetyCase,
    PlaneRecipeCase,
    ProjectionCase,
    PolicyCase,
    ShadowCase,
    TelemetryCase,
    ModelPolicyCase,
]

_CASE_MODELS: dict[str, type[BaseModel]] = {
    "citation_support": CitationSupportCase,
    "context_budget": ContextBudgetCase,
    "requirements_gap": RequirementsGapCase,
    "task_route": TaskRouteCase,
    "action_safety": ActionSafetyCase,
    "plane_recipe": PlaneRecipeCase,
    "projection": ProjectionCase,
    "policy": PolicyCase,
    "shadow": ShadowCase,
    "telemetry": TelemetryCase,
    "model_policy": ModelPolicyCase,
}


def load_decision_case(raw: dict[str, Any]) -> DecisionCaseDocument:
    case = raw.get("case")
    if case is None and "name" in raw:
        name = str(raw["name"])
        case = _LEGACY_PROBE_NAMES.get(name, name)
        raw = {**raw, "case": case}
        raw.pop("name", None)
    if case not in _CASE_MODELS:
        known = ", ".join(sorted(_CASE_MODELS))
        raise ValueError(f"unknown decision case {case!r}; known: {known}")
    return cast(DecisionCaseDocument, _CASE_MODELS[case].model_validate(raw))


def load_decision_case_path(path: str | Path) -> DecisionCaseDocument:
    file_path = Path(path)
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: decision case root must be a mapping")
    return load_decision_case(data)


async def run_decision_case_document(document: DecisionCaseDocument) -> dict[str, Any]:
    return await document.run()


class DecisionCaseCommand(BaseModel):
    """CLI verb body: ``path`` to a case plan, or inline ``case:`` document."""

    model_config = ConfigDict(extra="allow")

    path: str | None = None
    case: CaseKind | None = None

    @model_validator(mode="after")
    def _path_or_inline(self) -> DecisionCaseCommand:
        if self.path:
            return self
        if not self.case:
            raise ValueError("decision_case requires path= or case=")
        return self

    async def resolve_and_run(self, *, base_dir: Path | None = None) -> dict[str, Any]:
        if self.path:
            file_path = Path(self.path)
            if not file_path.is_absolute():
                root = base_dir if base_dir is not None else Path.cwd()
                file_path = (root / file_path).resolve()
            document = load_decision_case_path(file_path)
        else:
            document = load_decision_case(self.model_dump(exclude={"path"}))
        return await run_decision_case_document(document)


class DecisionCaseVerb(CliVerb):
    """Product verb: run a decision-plane case plan."""

    name = "decision_case"
    params_model = DecisionCaseCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = params
        assert isinstance(body, DecisionCaseCommand)
        return await body.resolve_and_run(base_dir=runtime.bind_base_dir)


__all__ = [
    "ActionSafetyCase",
    "CaseKind",
    "CitationSupportCase",
    "ContextBudgetCase",
    "DecisionCaseCommand",
    "DecisionCaseDocument",
    "DecisionCaseVerb",
    "ModelPolicyCase",
    "PlaneRecipeCase",
    "PolicyCase",
    "ProjectionCase",
    "RequirementsGapCase",
    "ShadowCase",
    "TaskRouteCase",
    "TelemetryCase",
    "load_decision_case",
    "load_decision_case_path",
    "run_decision_case_document",
]
