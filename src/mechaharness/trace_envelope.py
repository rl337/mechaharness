"""Required provenance envelope for run/node traces.

WalkingLabs L11 requires traces that reconstruct the decision path; DeepSeek
adds that model-visible and execution-affecting state must be observable
(https://walkinglabs.github.io/learn-harness-engineering/en/lectures/lecture-11-why-observability-belongs-inside-the-harness/,
https://walkinglabs.github.io/learn-harness-engineering/en/harness-designs/deepseek/).

MechaHarness defines a required ``TraceEnvelope`` checked before accepting a
trace event as complete::

    >>> from mechaharness.trace_envelope import TraceEnvelope, envelope_complete
    >>> env = TraceEnvelope(
    ...     config_fingerprint="cfg:abc",
    ...     graph_version="1",
    ...     template_version="fan_out@2",
    ...     node_id="verify",
    ...     routing_decision="reason",
    ...     context_provenance=["ctx:goal"],
    ...     capability_envelope_ref="env:1",
    ...     verification_plan_ref="vp:1",
    ...     extension_versions={"acme:watch": "1.0"},
    ...     parent_run_id=None,
    ...     child_run_ids=[],
    ... )
    >>> envelope_complete(env)
    True
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TraceEnvelope(BaseModel):
    """Harness/config/context/extension provenance attached to a trace."""

    model_config = ConfigDict(extra="allow")

    version: str = "1"
    config_fingerprint: str | None = None
    harness_version: str | None = None
    graph_version: str | None = None
    template_version: str | None = None
    node_id: str | None = None
    routing_decision: str | None = None
    context_provenance: list[str] = Field(default_factory=list)
    capability_envelope_ref: str | None = None
    verification_plan_ref: str | None = None
    extension_versions: dict[str, str] = Field(default_factory=dict)
    parent_run_id: str | None = None
    child_run_ids: list[str] = Field(default_factory=list)
    model_input_manifest_ref: str | None = None
    harness_fingerprint: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def missing_fields(self) -> list[str]:
        required = {
            "config_fingerprint": self.config_fingerprint,
            "graph_version": self.graph_version,
            "node_id": self.node_id,
            "routing_decision": self.routing_decision,
            "capability_envelope_ref": self.capability_envelope_ref,
        }
        missing = [name for name, value in required.items() if not value]
        if not self.context_provenance:
            missing.append("context_provenance")
        return missing


def envelope_complete(envelope: TraceEnvelope) -> bool:
    return not envelope.missing_fields()


def require_trace_envelope(envelope: TraceEnvelope) -> TraceEnvelope:
    missing = envelope.missing_fields()
    if missing:
        raise ValueError(f"incomplete trace envelope: {', '.join(missing)}")
    return envelope
