from mechaharness.fan_in_policy import FanInPolicy, accept_fan_in


def test_quorum():
    assert accept_fan_in(FanInPolicy(strategy="quorum", quorum=2), results=[True, True, False])
