from mechaharness.coordination_cost import CoordinationCostMetrics, summarize_coordination_cost


def test_sum():
    assert summarize_coordination_cost(CoordinationCostMetrics(branch_count=2))["branch_count"]==2
