import pytest

from mechaharness.trace_reconciliation import (
    ObservationSurface,
    reconcile_traces,
    require_reconciled,
)


def test_agree_and_conflict() -> None:
    ok = reconcile_traces(
        [
            ObservationSurface(name="executor", event_ids=["a", "b"], digests={"a": "1"}),
            ObservationSurface(name="gateway", event_ids=["a", "b"], digests={"a": "1"}),
        ]
    )
    assert ok.status == "agree"
    require_reconciled(ok)
    bad = reconcile_traces(
        [
            ObservationSurface(name="executor", event_ids=["a"], digests={"a": "1"}),
            ObservationSurface(name="gateway", event_ids=["a"], digests={"a": "2"}),
        ]
    )
    assert bad.status == "conflict"
    with pytest.raises(ValueError):
        require_reconciled(bad)
