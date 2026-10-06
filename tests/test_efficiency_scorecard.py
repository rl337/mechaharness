from mechaharness.efficiency_scorecard import build_efficiency_scorecard


def test_scorecard_keeps_dimensions() -> None:
    card = build_efficiency_scorecard(
        tool_calls=3, tokens_out=1200, latency_ms=4000, coordination_cost=1.5
    )
    assert card.dimensions["tool_calls"] == 3.0
    assert card.dimensions["tokens_out"] == 1200.0
