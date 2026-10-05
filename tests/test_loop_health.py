from mechaharness.loop_health import LoopHealthSignals, should_wind_down

def test_wind():
    assert should_wind_down(LoopHealthSignals(iterations_since_independent_verification=9))
