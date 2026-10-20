"""Product CLI verb: decision-plane case plans for JEV / host judgement walks.

One verb (``decision_case``) loads a human-readable YAML plan whose ``case:``
field selects the check — citation support, context budget packing,
requirements-gap review, task routing, or action-safety vs hard grants.
Stories and hosts share the same document shape under ``plans/``.
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
    run_decision_plane_policy,
)
from mechaharness.graph_templates import GraphTemplateParams, IndependentReviewTemplate

CaseKind = Literal[
    "citation_support",
    "context_budget",
    "requirements_gap",
    "task_route",
    "action_safety",
]


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


DecisionCaseDocument = Union[
    CitationSupportCase,
    ContextBudgetCase,
    RequirementsGapCase,
    TaskRouteCase,
    ActionSafetyCase,
]

_CASE_MODELS: dict[str, type[BaseModel]] = {
    "citation_support": CitationSupportCase,
    "context_budget": ContextBudgetCase,
    "requirements_gap": RequirementsGapCase,
    "task_route": TaskRouteCase,
    "action_safety": ActionSafetyCase,
}


def load_decision_case(raw: dict[str, Any]) -> DecisionCaseDocument:
    case = raw.get("case")
    if case is None and "name" in raw:
        # Legacy probe plan name → case id (citation_support_case → citation_support).
        name = str(raw["name"])
        case = name[: -len("_case")] if name.endswith("_case") else name
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
    "RequirementsGapCase",
    "TaskRouteCase",
    "load_decision_case",
    "load_decision_case_path",
    "run_decision_case_document",
]
