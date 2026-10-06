"""Cross-harness failure taxonomy (MH-MHRL-18).

FineEnvs notes that leaving a native harness may produce invalid tool calls,
which differs from merely solving fewer tasks
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#when-a-model-leaves-the-harness-it-was-trained-in).

MechaHarness classifies semantic task failure separately from protocol /
schema / termination / context / capability failures::

    >>> from mechaharness.cross_harness_failure import classify_cross_harness_failure
    >>> classify_cross_harness_failure("unknown tool foobar").kind
    'invalid_tool_name'
    >>> classify_cross_harness_failure("wrong answer").kind
    'semantic_task_failure'
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.eval_evidence import Claim

# Open vocabulary; hosts may emit additional namespaced kinds.
CROSS_HARNESS_KINDS = (
    "semantic_task_failure",
    "invalid_tool_name",
    "invalid_tool_schema",
    "malformed_protocol",
    "termination_failure",
    "context_dependence",
    "unsupported_capability",
)


class CrossHarnessFailure(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str
    message: str
    evidence_refs: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)

    def to_claim(self, *, claim_id: str = "cross_harness") -> Claim:
        status = "fail" if self.kind != "semantic_task_failure" else "fail"
        return Claim(
            id=claim_id,
            statement=self.message,
            status=status,
            evidence_refs=list(self.evidence_refs),
            detail={"cross_harness_kind": self.kind, **self.detail},
        )


def classify_cross_harness_failure(
    message: str,
    *,
    evidence_refs: list[str] | None = None,
) -> CrossHarnessFailure:
    lowered = message.lower()
    if any(tok in lowered for tok in ("unknown tool", "invalid tool name", "no such tool")):
        kind = "invalid_tool_name"
    elif any(tok in lowered for tok in ("schema", "argument", "validation error", "json schema")):
        kind = "invalid_tool_schema"
    elif any(tok in lowered for tok in ("malformed", "parse error", "protocol", "role")):
        kind = "malformed_protocol"
    elif any(tok in lowered for tok in ("did not terminate", "termination", "max turns", "no stop")):
        kind = "termination_failure"
    elif any(tok in lowered for tok in ("context", "compaction", "missing history", "lost state")):
        kind = "context_dependence"
    elif any(tok in lowered for tok in ("unsupported", "capability", "not available", "grant denied")):
        kind = "unsupported_capability"
    else:
        kind = "semantic_task_failure"
    return CrossHarnessFailure(
        kind=kind,
        message=message,
        evidence_refs=list(evidence_refs or ()),
    )
