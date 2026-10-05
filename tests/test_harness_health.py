from mechaharness.harness_health import HarnessHealthSnapshot, needs_cleanup

def test_clean():
    assert needs_cleanup(HarnessHealthSnapshot(unused_extensions=["x"]))
