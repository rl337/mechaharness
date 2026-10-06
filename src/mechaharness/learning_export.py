"""Versioned learning trajectory export packs (MH-MHRL-16).

FineEnvs reuses successful trajectories for SFT as well as RL; MechaHarness
exports provenance-rich packs without owning SFT/RL recipes
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#sft-vs-rl)::

    >>> from mechaharness.learning_export import build_learning_export
    >>> pack = build_learning_export(
    ...     harness_fingerprint="fp:1",
    ...     rollout_graph_ref="rollout:1",
    ...     split="train",
    ... )
    >>> pack.schema_version
    '1'
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.decision_log import OfflineDecisionExport


class LearningExportPack(BaseModel):
    """Bundle of MH execution artifacts for downstream learning consumers."""

    model_config = ConfigDict(extra="allow")

    schema_version: str = "1"
    split: str = "train"
    harness_fingerprint: str | None = None
    rollout_graph_ref: str | None = None
    model_input_manifest_refs: list[str] = Field(default_factory=list)
    evaluation_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    decisions: OfflineDecisionExport | None = None
    event_lineage: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)


def build_learning_export(
    *,
    decisions: OfflineDecisionExport | None = None,
    harness_fingerprint: str | None = None,
    rollout_graph_ref: str | None = None,
    model_input_manifest_refs: Sequence[str] | None = None,
    evaluation_outcomes: Sequence[Mapping[str, Any]] | None = None,
    event_lineage: Sequence[str] | None = None,
    split: str | None = None,
    detail: Mapping[str, Any] | None = None,
) -> LearningExportPack:
    return LearningExportPack(
        split=split or (decisions.split if decisions else "train"),
        harness_fingerprint=harness_fingerprint,
        rollout_graph_ref=rollout_graph_ref,
        model_input_manifest_refs=list(model_input_manifest_refs or ()),
        evaluation_outcomes=[dict(item) for item in (evaluation_outcomes or ())],
        decisions=decisions,
        event_lineage=list(event_lineage or (decisions.lineage if decisions else ())),
        detail=dict(detail or {}),
    )
