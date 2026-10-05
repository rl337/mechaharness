from mechaharness.rule_promotion import PromotionRecord, promote_soft_to_hard


def test_promo():
    r=promote_soft_to_hard(PromotionRecord(observed_pattern="p"), hard_invariant_ref="h")
    assert r.stage=="hard"
