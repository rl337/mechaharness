from mechaharness.discriminative_value import discriminative_report
from mechaharness.eval_trial import Trial
from mechaharness.exposure_accounting import ExposureLedger, ExposureSample


def test_exposure_and_ties() -> None:
    ledger = ExposureLedger()
    ledger.record(ExposureSample(arm="treatment", rollouts=1, model_calls=4, tokens_out=800))
    ledger.record(ExposureSample(arm="control", rollouts=1, model_calls=1, tokens_out=100))
    summary = ledger.summarize()
    assert summary["arms"]["treatment"]["model_calls"] == 4
    report = discriminative_report(
        [Trial(trial_id="1", success=True), Trial(trial_id="2", success=True)]
    )
    assert report.all_success_tie
