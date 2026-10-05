from mechaharness.component_ablation import ComponentAblationExperiment, ablation_delta


def test_delta():
    e=ComponentAblationExperiment(baseline_fingerprint="f",disabled_component_ids=["a"],task_corpus_ref="c",baseline_success_rate=0.8,ablated_success_rate=0.5)
    assert ablation_delta(e)["success_delta"]==-0.3
