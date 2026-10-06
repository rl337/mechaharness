"""Eval-facing harness/config provenance fingerprint (MH-MHRL-01).

FineEnvs shows that changing only the harness can materially change model
performance; evaluation results must not be represented as properties of a
model alone when harness provenance is known
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#benchmark-scores-now-come-with-a-harness-attached).

MechaHarness binds model revision, harness family/version, graph/template/
config digests, routing/context/tool surface, evaluator, environment, and
task/corpus identity into one digestable object::

    >>> from mechaharness.harness_fingerprint import (
    ...     HarnessFingerprint, require_eval_provenance,
    ... )
    >>> a = HarnessFingerprint(
    ...     model_revision="model@r1",
    ...     harness_family="react",
    ...     harness_version="2026.10",
    ...     config_fingerprint="cfg:aaa",
    ...     graph_version="1",
    ...     template_version="verify_repair@1",
    ...     routing_surface="reason",
    ...     context_surface=["ctx:goal"],
    ...     tool_surface=["Read"],
    ...     evaluator_id="demo:exists",
    ...     evaluator_version="1",
    ...     environment_profile="local",
    ...     task_id="task-1",
    ...     corpus_id="corpus-a",
    ... )
    >>> b = a.model_copy(update={"config_fingerprint": "cfg:bbb"})
    >>> a.digest() != b.digest()
    True
    >>> require_eval_provenance({"model": "x"}, fingerprint=a)["harness_fingerprint"] == a.digest()
    True
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.model_input_manifest import content_digest


class HarnessFingerprint(BaseModel):
    """Effective harness configuration identity for evaluation provenance."""

    model_config = ConfigDict(extra="allow")

    version: str = "1"
    model_revision: str | None = None
    harness_family: str | None = None
    harness_version: str | None = None
    config_fingerprint: str | None = None
    graph_version: str | None = None
    template_version: str | None = None
    routing_surface: str | None = None
    context_surface: list[str] = Field(default_factory=list)
    tool_surface: list[str] = Field(default_factory=list)
    evaluator_id: str | None = None
    evaluator_version: str | None = None
    environment_profile: str | None = None
    task_id: str | None = None
    corpus_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def canonical_parts(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "model_revision": self.model_revision,
            "harness_family": self.harness_family,
            "harness_version": self.harness_version,
            "config_fingerprint": self.config_fingerprint,
            "graph_version": self.graph_version,
            "template_version": self.template_version,
            "routing_surface": self.routing_surface,
            "context_surface": list(self.context_surface),
            "tool_surface": sorted(self.tool_surface),
            "evaluator_id": self.evaluator_id,
            "evaluator_version": self.evaluator_version,
            "environment_profile": self.environment_profile,
            "task_id": self.task_id,
            "corpus_id": self.corpus_id,
        }

    def digest(self) -> str:
        return content_digest(self.canonical_parts())

    def missing_fields(self) -> list[str]:
        required = {
            "model_revision": self.model_revision,
            "harness_family": self.harness_family,
            "harness_version": self.harness_version,
            "config_fingerprint": self.config_fingerprint,
            "evaluator_id": self.evaluator_id,
            "environment_profile": self.environment_profile,
            "task_id": self.task_id,
        }
        missing = [name for name, value in required.items() if not value]
        if not self.tool_surface:
            missing.append("tool_surface")
        return missing


def build_harness_fingerprint(
    *,
    model_revision: str | None = None,
    harness_family: str | None = None,
    harness_version: str | None = None,
    config_fingerprint: str | None = None,
    graph_version: str | None = None,
    template_version: str | None = None,
    routing_surface: str | None = None,
    context_surface: Sequence[str] | None = None,
    tool_surface: Sequence[str] | None = None,
    evaluator_id: str | None = None,
    evaluator_version: str | None = None,
    environment_profile: str | None = None,
    task_id: str | None = None,
    corpus_id: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> HarnessFingerprint:
    """Construct a fingerprint from already-resolved provenance fragments."""
    return HarnessFingerprint(
        model_revision=model_revision,
        harness_family=harness_family,
        harness_version=harness_version,
        config_fingerprint=config_fingerprint,
        graph_version=graph_version,
        template_version=template_version,
        routing_surface=routing_surface,
        context_surface=list(context_surface or ()),
        tool_surface=list(tool_surface or ()),
        evaluator_id=evaluator_id,
        evaluator_version=evaluator_version,
        environment_profile=environment_profile,
        task_id=task_id,
        corpus_id=corpus_id,
        extra=dict(extra or {}),
    )


def require_eval_provenance(
    summary: Mapping[str, Any],
    *,
    fingerprint: HarnessFingerprint | None,
    require: bool = True,
) -> dict[str, Any]:
    """Attach fingerprint digest; refuse model-only summaries when required."""
    out = dict(summary)
    if fingerprint is None:
        if require and "model" in out and "harness_fingerprint" not in out:
            raise ValueError(
                "evaluation summary is model-only; harness fingerprint required"
            )
        return out
    digest = fingerprint.digest()
    out["harness_fingerprint"] = digest
    out["harness_fingerprint_parts"] = fingerprint.canonical_parts()
    return out
