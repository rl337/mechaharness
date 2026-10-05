import pytest

from mechaharness.trace_envelope import (
    TraceEnvelope,
    envelope_complete,
    require_trace_envelope,
)


def test_complete_envelope() -> None:
    env = TraceEnvelope(
        config_fingerprint="c",
        graph_version="1",
        node_id="n",
        routing_decision="reason",
        context_provenance=["a"],
        capability_envelope_ref="e",
    )
    assert envelope_complete(env)
    assert require_trace_envelope(env) is env


def test_incomplete_raises() -> None:
    with pytest.raises(ValueError, match="incomplete"):
        require_trace_envelope(TraceEnvelope())
