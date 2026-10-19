"""Registry-bounded recipe evolution helpers (MH-SR-06)."""

from __future__ import annotations

from mechaharness.graph_templates import default_graph_templates
from mechaharness.objective_policy import ObjectiveResult
from mechaharness.recipe_lifecycle.recipe_evolution import (
    RecipeCandidate,
    RecipeTraceSummary,
    ScoredCandidate,
    SoftBindingSuggestion,
    propose_candidates,
    select_candidate,
    validate_candidate,
)


def _summary(recipe: str, *pairs: tuple[str, object, int]) -> RecipeTraceSummary:
    return RecipeTraceSummary(
        recipe=recipe,
        runs=10,
        suggestions=[
            SoftBindingSuggestion(soft_point=n, value=v, support=s) for n, v, s in pairs
        ],
    )


_VALIDATE = [
    ("ok", "produce_critique_refine", {"max_rounds": 3}, None, []),
    ("unknown_recipe", "nope", {"x": 1}, None, ["unknown_recipe:nope"]),
    ("unknown_soft_point", "produce_critique_refine", {"x": 1}, None, ["unknown_soft_point:x"]),
    (
        "hard_soft_point",
        "produce_critique_refine",
        {"refine_kind": "z"},
        None,
        ["soft_point_not_evolvable:refine_kind"],
    ),
    (
        "outside_host_allowlist",
        "produce_critique_refine",
        {"max_rounds": 3},
        {"produce_critique_refine": ["critique_prompt"]},
        ["soft_point_not_allowlisted:max_rounds"],
    ),
    ("empty", "produce_critique_refine", {}, None, ["empty_bindings"]),
]


def test_validate_candidate_matrix() -> None:
    registry = default_graph_templates()
    for case_id, recipe, bindings, allowlist, expected in _VALIDATE:
        candidate = RecipeCandidate(id=case_id, recipe=recipe, soft_bindings=bindings)
        assert validate_candidate(candidate, registry, allowlist=allowlist) == expected, case_id


def test_proposals_are_single_soft_point_candidates_ranked_by_support() -> None:
    registry = default_graph_templates()
    proposal = propose_candidates(
        [
            _summary(
                "produce_critique_refine",
                ("max_rounds", 3, 5),
                ("critique_prompt", "be strict", 9),
                ("refine_kind", "x", 99),
            ),
            _summary("independent_review", ("reviewer_count", 2, 7), ("ghost", 1, 1)),
        ],
        registry,
    )
    assert [c.soft_bindings for c in proposal.candidates] == [
        {"critique_prompt": "be strict"},
        {"reviewer_count": 2},
        {"max_rounds": 3},
    ]
    assert {(r.recipe, r.soft_point) for r in proposal.rejected} == {
        ("produce_critique_refine", "refine_kind"),
        ("independent_review", "ghost"),
    }
    assert all(c.base_version == "1" for c in proposal.candidates)


def test_candidate_count_is_bounded() -> None:
    registry = default_graph_templates()
    summary = _summary(
        "produce_critique_refine", ("max_rounds", 3, 5), ("critique_prompt", "p", 4)
    )
    assert len(propose_candidates([summary], registry, max_candidates=1).candidates) == 1


def test_allowlist_narrows_what_may_be_proposed() -> None:
    proposal = propose_candidates(
        [_summary("produce_critique_refine", ("max_rounds", 3, 5), ("critique_prompt", "p", 4))],
        default_graph_templates(),
        allowlist={"produce_critique_refine": ["max_rounds"]},
    )
    assert [c.soft_bindings for c in proposal.candidates] == [{"max_rounds": 3}]
    assert proposal.rejected[0].reason == "soft_point_not_allowlisted:critique_prompt"


def _scored(
    cid: str,
    scalar: float | None,
    *,
    scored: bool = True,
    gates: bool = True,
    support: int = 0,
) -> ScoredCandidate:
    return ScoredCandidate(
        candidate=RecipeCandidate(id=cid, recipe="r", soft_bindings={"a": 1}, support=support),
        result=ObjectiveResult(
            policy_id="p",
            policy_version="1",
            formula="all_pass",
            scored=scored,
            gates_satisfied=gates,
            scalar=scalar,
        ),
    )


def test_selection_is_deterministic_and_respects_gates_and_baseline() -> None:
    pool = [
        _scored("low", 0.4),
        _scored("gate_failed", 0.99, gates=False),
        _scored("unscored", None, scored=False),
        _scored("tie_b", 0.8, support=1),
        _scored("tie_a", 0.8, support=1),
        _scored("tie_more_support", 0.8, support=5),
    ]
    assert select_candidate(pool).id == "tie_more_support"
    assert select_candidate(pool[:5]).id == "tie_a"
    assert select_candidate(pool, baseline_scalar=0.8) is None
    assert select_candidate([]) is None
