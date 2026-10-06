import pytest

from mechaharness.experiment_lineage import ExperimentCheckpoint, lineage_digest


def test_resume_refuses_reconsume() -> None:
    ckpt = ExperimentCheckpoint(experiment_id="e1", assignment="treatment")
    ckpt = ckpt.consume("case-a", evidence_digest="d1")
    assert ckpt.would_duplicate("case-a")
    with pytest.raises(ValueError, match="already consumed"):
        ckpt.consume("case-a")
    assert ckpt.remaining(["case-a", "case-b"]) == ["case-b"]
    assert lineage_digest(ckpt)
