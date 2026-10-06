import pytest

from mechaharness.harness_fingerprint import (
    HarnessFingerprint,
    build_harness_fingerprint,
    require_eval_provenance,
)


def test_digest_changes_with_config() -> None:
    a = build_harness_fingerprint(
        model_revision="m@1",
        harness_family="react",
        harness_version="1",
        config_fingerprint="cfg:a",
        tool_surface=["Read"],
        evaluator_id="e",
        environment_profile="local",
        task_id="t1",
    )
    b = a.model_copy(update={"config_fingerprint": "cfg:b"})
    assert a.digest() != b.digest()


def test_require_eval_provenance_refuses_model_only() -> None:
    with pytest.raises(ValueError, match="model-only"):
        require_eval_provenance({"model": "x"}, fingerprint=None, require=True)
    fp = HarnessFingerprint(
        model_revision="m",
        harness_family="react",
        harness_version="1",
        config_fingerprint="c",
        tool_surface=["Read"],
        evaluator_id="e",
        environment_profile="local",
        task_id="t",
    )
    out = require_eval_provenance({"model": "x"}, fingerprint=fp)
    assert out["harness_fingerprint"] == fp.digest()
