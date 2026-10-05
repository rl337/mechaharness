from mechaharness.resume_cost import ResumeCostMetrics, summarize_resume_cost

def test_sum():
    assert summarize_resume_cost(ResumeCostMetrics(rebuild_tokens=1))["rebuild_tokens"]==1
