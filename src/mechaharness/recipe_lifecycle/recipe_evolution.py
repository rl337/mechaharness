"""Registry-bounded recipe evolution helpers (MH-SR-06).

Pure structure for hosts (for example June) that own the campaign: this module
turns a trace summary into **soft-binding candidates only**, validates them
against the registry and the evolvable allowlist, and selects among scored
candidates under an explicit :class:`~mechaharness.objective_policy.ObjectivePolicy`
result. It calls no model, runs no evaluation, and never builds free-form
graphs; isolated evaluation and promotion stay with the host and the
:class:`~mechaharness.research.ResearchLab` / registry final-test gates.

::

    >>> from mechaharness.graph_templates import default_graph_templates
    >>> from mechaharness.recipe_lifecycle.recipe_evolution import (
    ...     RecipeTraceSummary, SoftBindingSuggestion, propose_candidates,
    ... )
    >>> summary = RecipeTraceSummary(
    ...     recipe="produce_critique_refine",
    ...     runs=40,
    ...     suggestions=[
    ...         SoftBindingSuggestion(soft_point="max_rounds", value=3, support=12),
    ...         SoftBindingSuggestion(soft_point="refine_kind", value="x", support=30),
    ...     ],
    ... )
    >>> proposal = propose_candidates([summary], default_graph_templates())
    >>> [c.soft_bindings for c in proposal.candidates]
    [{'max_rounds': 3}]
    >>> [r.reason for r in proposal.rejected]
    ['soft_point_not_evolvable:refine_kind']
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.graph_templates.base import GraphTemplateRegistry
from mechaharness.objective_policy import ObjectiveResult


class SoftBindingSuggestion(BaseModel):
    """One trace-derived hint: bind ``soft_point`` to ``value``."""

    model_config = ConfigDict(extra="allow")

    soft_point: str
    value: Any
    support: int = 0
    reason: str = ""


class RecipeTraceSummary(BaseModel):
    """Host-computed summary of immutable traces for one recipe."""

    model_config = ConfigDict(extra="allow")

    recipe: str
    runs: int = 0
    failure_classes: dict[str, int] = Field(default_factory=dict)
    suggestions: list[SoftBindingSuggestion] = Field(default_factory=list)


class RecipeCandidate(BaseModel):
    """A bounded candidate: one recipe plus soft bindings, never a graph."""

    model_config = ConfigDict(extra="allow")

    id: str
    recipe: str
    base_version: str | None = None
    soft_bindings: dict[str, Any] = Field(default_factory=dict)
    support: int = 0


class RejectedSuggestion(BaseModel):
    recipe: str
    soft_point: str
    reason: str


class EvolutionProposal(BaseModel):
    candidates: list[RecipeCandidate] = Field(default_factory=list)
    rejected: list[RejectedSuggestion] = Field(default_factory=list)


class ScoredCandidate(BaseModel):
    """A candidate with the objective result a host computed in isolation."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    candidate: RecipeCandidate
    result: ObjectiveResult


def validate_candidate(
    candidate: RecipeCandidate,
    registry: GraphTemplateRegistry,
    *,
    allowlist: Mapping[str, Collection[str]] | None = None,
) -> list[str]:
    """Reasons a candidate is outside the registry / allowlist (empty when valid)."""
    template = registry.get(candidate.recipe)
    if template is None:
        return [f"unknown_recipe:{candidate.recipe}"]
    issues: list[str] = []
    declared = {p.name for p in template.soft_points}
    evolvable = set(template.evolvable_soft_point_names())
    permitted = (
        set(allowlist[candidate.recipe])
        if allowlist and candidate.recipe in allowlist
        else None
    )
    if not candidate.soft_bindings:
        issues.append("empty_bindings")
    for name in candidate.soft_bindings:
        if name not in declared:
            issues.append(f"unknown_soft_point:{name}")
        elif name not in evolvable:
            issues.append(f"soft_point_not_evolvable:{name}")
        elif permitted is not None and name not in permitted:
            issues.append(f"soft_point_not_allowlisted:{name}")
    return issues


def propose_candidates(
    summaries: Sequence[RecipeTraceSummary],
    registry: GraphTemplateRegistry,
    *,
    allowlist: Mapping[str, Collection[str]] | None = None,
    max_candidates: int = 8,
) -> EvolutionProposal:
    """Turn trace suggestions into validated single-soft-point candidates.

    Candidates are ordered by ``support`` (descending), then recipe and soft
    point name, and capped at ``max_candidates``. Suggestions that fail
    validation are reported in ``rejected`` instead of being silently dropped.
    """
    ranked: list[tuple[RecipeTraceSummary, SoftBindingSuggestion]] = [
        (summary, suggestion)
        for summary in summaries
        for suggestion in summary.suggestions
    ]
    ranked.sort(key=lambda pair: (-pair[1].support, pair[0].recipe, pair[1].soft_point))
    proposal = EvolutionProposal()
    for summary, suggestion in ranked:
        candidate = RecipeCandidate(
            id=f"{summary.recipe}:{suggestion.soft_point}={suggestion.value!r}",
            recipe=summary.recipe,
            base_version=registry.active_version(summary.recipe),
            soft_bindings={suggestion.soft_point: suggestion.value},
            support=suggestion.support,
        )
        issues = validate_candidate(candidate, registry, allowlist=allowlist)
        if issues:
            proposal.rejected.append(
                RejectedSuggestion(
                    recipe=summary.recipe,
                    soft_point=suggestion.soft_point,
                    reason=issues[0],
                )
            )
        elif len(proposal.candidates) < max_candidates:
            proposal.candidates.append(candidate)
    return proposal


def select_candidate(
    scored: Sequence[ScoredCandidate],
    *,
    baseline_scalar: float | None = None,
) -> RecipeCandidate | None:
    """Pick the best gate-satisfying candidate by objective scalar.

    Candidates whose objective result is unscored, failed a gate, or did not
    beat ``baseline_scalar`` are ineligible. Ties go to higher trace support,
    then candidate id, so selection is deterministic.
    """
    eligible = [
        s
        for s in scored
        if s.result.scored
        and s.result.gates_satisfied
        and s.result.scalar is not None
        and (baseline_scalar is None or s.result.scalar > baseline_scalar)
    ]
    if not eligible:
        return None
    best = min(
        eligible,
        key=lambda s: (-(s.result.scalar or 0.0), -s.candidate.support, s.candidate.id),
    )
    return best.candidate
