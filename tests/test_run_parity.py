from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.harness.base import HarnessConfig
from mechaharness.run_parity import compare_parity, parity_from_harness_config
from mechaharness.stop_contract import StopContract


def test_material_mismatch_on_max_tokens() -> None:
    cfg_a = HarnessConfig(model="m", max_tokens=1024, temperature=0.0)
    cfg_b = HarnessConfig(model="m", max_tokens=512, temperature=0.0)
    env = CapabilityEnvelope(tool_names=["Read"])
    a = parity_from_harness_config(cfg_a, envelope=env, stop=StopContract(max_iterations=3))
    b = parity_from_harness_config(cfg_b, envelope=env, stop=StopContract(max_iterations=3))
    report = compare_parity(a, b)
    assert not report.comparable
    assert "max_tokens" in report.material_mismatches
