"""Derived text does not become authority."""

from __future__ import annotations

import pytest

from mechaharness.authority_admission import review_admission


def test_discovery_stays_a_candidate_and_ledger_gates_effects() -> None:
    report = review_admission(
        ledger=[{"resource_id": "repo:acme/widget", "operation": "edit"}],
        claims=[
            {
                "id": "seen_in_doc",
                "kind": "resource_candidate",
                "source_class": "discovery",
                "quote": "repo:other",
            }
        ],
        effects=[
            {
                "id": "owned",
                "resource_id": "repo:acme/widget",
                "operation": "edit",
            },
            {
                "id": "other",
                "resource_id": "repo:other",
                "operation": "edit",
            },
        ],
    )
    assert report["decisions"]["seen_in_doc"] == "candidate"
    assert report["effects"]["owned"] == "ledger_match"
    assert report["effects"]["other"] == "ledger_miss"


def test_user_requirement_without_predicate_asks_a_human() -> None:
    report = review_admission(
        ledger=[],
        claims=[
            {
                "id": "loose",
                "kind": "requirement",
                "source_class": "user",
                "quote": "make it nice",
                "predicate": "",
            }
        ],
        effects=[],
    )
    assert report["decisions"]["loose"] == "ask_human"


@pytest.mark.parametrize("kind", ["claim", "effect"])
def test_report_refuses_ambiguous_duplicate_ids(kind: str) -> None:
    claim = {"id": "same", "source_class": "user", "quote": "do it", "predicate": "check"}
    effect = {"id": "same", "resource_id": "repo", "operation": "edit"}
    with pytest.raises(ValueError, match="ids must be unique"):
        review_admission(
            ledger=[],
            claims=[claim, claim] if kind == "claim" else [],
            effects=[effect, effect] if kind == "effect" else [],
        )
