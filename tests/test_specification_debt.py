"""Correction → specification-debt ledger (MH-PA-07)."""

from __future__ import annotations

import pytest

from mechaharness.rule_promotion import (
    PromotionRecord,
    SpecificationDebtLedger,
    capture_correction,
)


def test_capture_links_promotion_and_requires_review() -> None:
    promotion = PromotionRecord(record_id="promo:7", observed_pattern="wrong thread")
    item = capture_correction(
        "Reply on the original thread.",
        failing_scenarios=["scenario:a", "scenario:b"],
        promotion=promotion,
    )
    assert item.review_required is True
    assert item.status == "open"
    assert item.promotion_record_id == "promo:7"
    assert item.failing_scenario_refs == ["scenario:a", "scenario:b"]
    assert item.generated_test_ref is None


def test_explicit_promotion_id_wins_over_record_and_absent_link_is_none() -> None:
    promotion = PromotionRecord(record_id="promo:7", observed_pattern="x")
    assert (
        capture_correction("c", promotion=promotion, promotion_record_id="promo:9")
        .promotion_record_id
        == "promo:9"
    )
    assert capture_correction("c").promotion_record_id is None


def test_blank_correction_is_refused() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        capture_correction("   ")


def test_host_links_a_test_then_a_human_closes_the_debt() -> None:
    ledger = SpecificationDebtLedger()
    item = ledger.add(capture_correction("c", promotion_record_id="promo:1"))
    linked = ledger.update(item.link_test("tests/test_reply.py::test_thread"))
    assert linked.status == "test_linked" and linked.review_required is True
    assert [r.id for r in ledger.pending_review()] == [item.id]
    ledger.update(linked.approve())
    assert ledger.pending_review() == []
    assert ledger.get(item.id).status == "closed"
    assert [r.id for r in ledger.for_promotion("promo:1")] == [item.id]


def test_update_of_unknown_record_fails() -> None:
    with pytest.raises(KeyError):
        SpecificationDebtLedger().update(capture_correction("c"))
