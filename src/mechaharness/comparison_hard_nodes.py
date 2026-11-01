"""Deterministic gastronomic comparison hard-node runners."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.discovery_hard_nodes import (
    DiscoveryHardNodeError,
    _as_mapping,
    _payload_section,
    _read_path,
)
from mechaharness.gastronomic_comparison import (
    assemble_gastronomic_trial,
    summarize_gastronomic_comparison,
    validate_gastronomic_trial,
)
from mechaharness.graph import GraphNode, NodeStatus
from mechaharness.graph_executor import GraphNodeRunner, GraphRunContext, NodeOutcome
from mechaharness.walk_bag import WalkBag, WalkBagPathError, WalkBagSerializeError

COMPARISON_HARD_KINDS: tuple[str, ...] = (
    "comparison_assemble",
    "comparison_summarize",
    "comparison_validate",
)


class ComparisonHardNodeRunner(GraphNodeRunner):
    """Run gastronomic-comparison hard-node kinds with atomic bag writes."""

    def __init__(self, kinds: Sequence[str] | None = None) -> None:
        selected = list(kinds) if kinds is not None else list(COMPARISON_HARD_KINDS)
        unknown = [k for k in selected if k not in COMPARISON_HARD_KINDS]
        if unknown:
            raise ValueError(f"unknown comparison hard-node kinds: {unknown}")
        if not selected:
            raise ValueError("ComparisonHardNodeRunner requires at least one kind")
        self._kinds = selected

    def kinds(self) -> Sequence[str]:
        return list(self._kinds)

    async def run(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
        payload = node.payload if isinstance(node.payload, Mapping) else {}
        try:
            reads = _payload_section(payload, "reads")
            writes = _payload_section(payload, "writes")
            parameters = _payload_section(payload, "parameters")
            result = self._dispatch(
                str(node.kind),
                bag=context.bag,
                reads=reads,
                parameters=parameters,
            )
            dest = writes.get("destination")
            if not isinstance(dest, str) or not dest.strip():
                raise DiscoveryHardNodeError("writes.destination is required")
            batch = context.bag.staged_writes()
            batch.put(dest, result)
            batch.commit()
            return NodeOutcome(status=NodeStatus.SUCCEEDED)
        except (DiscoveryHardNodeError, WalkBagPathError, WalkBagSerializeError) as exc:
            return NodeOutcome(status=NodeStatus.FAILED, error=str(exc))

    def _dispatch(
        self,
        kind: str,
        *,
        bag: WalkBag,
        reads: Mapping[str, Any],
        parameters: Mapping[str, Any],
    ) -> Any:
        if kind == "comparison_assemble":
            outcome_path = str(
                reads.get("development_outcome") or "in.development_outcome"
            )
            metrics_path = str(reads.get("metrics") or "in.metrics")
            model_path = reads.get("model")
            budget_path = reads.get("budget")
            outcome_raw = _read_path(bag, outcome_path, required=False)
            metrics_raw = _read_path(bag, metrics_path, required=False)
            outcome = (
                _as_mapping(outcome_raw, label="development_outcome")
                if isinstance(outcome_raw, Mapping)
                else {}
            )
            metrics = (
                _as_mapping(metrics_raw, label="metrics")
                if isinstance(metrics_raw, Mapping)
                else {}
            )
            model = None
            if isinstance(model_path, str) and model_path.strip():
                model_raw = _read_path(bag, model_path, required=False)
                if isinstance(model_raw, Mapping):
                    model = _as_mapping(model_raw, label="model")
            budget = None
            if isinstance(budget_path, str) and budget_path.strip():
                budget_raw = _read_path(bag, budget_path, required=False)
                if isinstance(budget_raw, Mapping):
                    budget = _as_mapping(budget_raw, label="budget")
            trial_id = str(parameters.get("trial_id") or metrics.get("trial_id") or "trial")
            arm = str(parameters.get("arm") or metrics.get("arm") or "")
            recipe_id = str(parameters.get("recipe_id") or metrics.get("recipe_id") or "")
            suite_id = parameters.get("suite_id") or metrics.get("suite_id")
            notes = parameters.get("notes")
            return assemble_gastronomic_trial(
                trial_id=trial_id,
                arm=arm,
                recipe_id=recipe_id,
                development_outcome=outcome or None,
                metrics=metrics or None,
                model=model,
                budget=budget,
                suite_id=str(suite_id) if suite_id is not None else None,
                notes=str(notes) if notes is not None else None,
            )

        if kind == "comparison_summarize":
            trials_path = str(reads.get("trials") or "in.trials")
            raw = _read_path(bag, trials_path)
            if not isinstance(raw, list):
                raise DiscoveryHardNodeError("comparison_summarize requires a trials list")
            trials = [row for row in raw if isinstance(row, Mapping)]
            return summarize_gastronomic_comparison(trials)

        if kind == "comparison_validate":
            source_path = str(reads.get("source") or "out.trial")
            report = validate_gastronomic_trial(
                _as_mapping(_read_path(bag, source_path), label="trial")
            )
            if parameters.get("fail_if_invalid") and not report["ok"]:
                raise DiscoveryHardNodeError(
                    "comparison_validate failed: "
                    + ", ".join(e["path"] for e in report["errors"])
                )
            return report

        raise DiscoveryHardNodeError(f"unsupported comparison hard-node kind {kind!r}")


__all__ = [
    "COMPARISON_HARD_KINDS",
    "ComparisonHardNodeRunner",
]
