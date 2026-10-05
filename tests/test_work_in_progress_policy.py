from mechaharness.work_in_progress_policy import WorkInProgressPolicy


def test_wip():
    p = WorkInProgressPolicy(max_active_nodes=2, max_per_write_scope=1)
    assert p.allows(active_nodes=1, write_scope="a", active_in_scope=0)
    assert not p.allows(active_nodes=1, write_scope="a", active_in_scope=1)
