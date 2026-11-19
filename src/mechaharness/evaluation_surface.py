"""Product library-surface runners (former evaluation_research_probes.py)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.component_ablation import ComponentAblationExperiment, ablation_delta
from mechaharness.cross_harness_failure import classify_cross_harness_failure
from mechaharness.discriminative_value import discriminative_report
from mechaharness.efficiency_scorecard import build_efficiency_scorecard
from mechaharness.eval_evidence import Claim, all_passed, compose_claims
from mechaharness.eval_matrix import EvalMatrix
from mechaharness.eval_trial import Trial, pass_at_k, trial_cost_rollup
from mechaharness.evaluator import EvaluatorResult
from mechaharness.experiment_dimensions import (
    ExperimentDimensions,
    require_dimension_trace_fields,
)
from mechaharness.experiment_lineage import ExperimentCheckpoint
from mechaharness.exposure_accounting import ExposureLedger, ExposureSample
from mechaharness.failure_attribution import (
    attribute_error,
    detect_repeated_failure_classes,
)
from mechaharness.harness_experiment import HarnessExperiment, HarnessExperimentRunner
from mechaharness.harness_fingerprint import (
    build_harness_fingerprint,
    require_eval_provenance,
)
from mechaharness.layered_verdict import score_layers
from mechaharness.learning_export import build_learning_export
from mechaharness.model_input_manifest import content_digest
from mechaharness.objective_policy import ObjectivePolicy, aggregate_objective
from mechaharness.research import EvalProtocol, ResearchLab
from mechaharness.trace_envelope import TraceEnvelope, envelope_complete
from mechaharness.trace_reconciliation import ObservationSurface, reconcile_traces


class EvaluationResearchParams(BaseModel):
    """Open params bag — each probe validates only what it needs."""

    model_config = ConfigDict(extra="allow")


class ResearchObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hypothesis: str
    metric: float
    change_set: dict[str, Any] = Field(default_factory=dict)
    safety_ok: bool = True
    whole_task_cost: float | None = None
    ablations: dict[str, float] | None = None


class ResearchEvaluationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_split: str
    baseline_metric: float
    candidates: list[ResearchObservation]
    final_test: EvaluatorResult | None = None
    final_test_hypothesis: str | None = None
    final_test_candidate_digest: str | None = None

    def candidate_digests(self) -> dict[str, str]:
        return {
            row.hypothesis: content_digest(
                {
                    "hypothesis": row.hypothesis,
                    "change_set": row.change_set,
                    "task_split": self.task_split,
                    "baseline_metric": self.baseline_metric,
                }
            )
            for row in self.candidates
        }


class EvaluatorComposeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluator_id: str
    version: str
    held_out: bool = False
    claims: list[Claim] = Field(min_length=1)


def run_atk_research_reject(inputs: dict[str, Any]) -> dict[str, Any]:
    """Evaluate supplied research observations; never invent a final-test success."""
    params = ResearchEvaluationParams.model_validate(inputs)
    if len({row.hypothesis for row in params.candidates}) != len(params.candidates):
        raise ValueError("candidate hypotheses must uniquely identify supplied observations")
    lab = ResearchLab(
        EvalProtocol(task_split=params.task_split), baseline_metric=params.baseline_metric
    )
    for row in params.candidates:
        cand = lab.propose(row.hypothesis, row.change_set)
        lab.evaluate(
            cand,
            metric=row.metric,
            safety_ok=row.safety_ok,
            whole_task_cost=row.whole_task_cost,
            ablations=row.ablations,
        )
    accepted = [c for c in lab.candidates if c.status.value == "accepted"]
    refusal = None
    if accepted:
        final = params.final_test
        if final is None:
            refusal = "missing_final_test"
        elif (
            params.final_test_hypothesis != accepted[0].hypothesis
            or params.final_test_candidate_digest
            != params.candidate_digests()[accepted[0].hypothesis]
        ):
            refusal = "final_test_candidate_mismatch"
        elif not final.claims or not all_passed(final.claims):
            refusal = "final_test_claims_not_passed"
        elif not final.held_out or not final.passed:
            refusal = "final_test_not_held_out_or_passed"
        else:
            lab.promote(accepted[0], final_test=final)
    report = lab.report()
    return {
        "rejected_cheap_nonempty": bool(report.rejected_cheap_failures),
        "promoted_nonempty": bool(report.promoted_id),
        "negative_results_nonempty": bool(report.negative_results),
        "promotion_refusal": refusal,
        "evidence_origin": "caller_supplied",
        "candidate_digests": params.candidate_digests(),
    }


def run_harness_experiment_retire(inputs: dict[str, Any]) -> dict[str, Any]:
    runner = HarnessExperimentRunner()
    exp = runner.propose(
        HarnessExperiment(
            hypothesis=str(inputs["hypothesis"]),
            intervention=str(inputs["intervention"]),
            failure_mode="token_bloat",
            evidence="inspiration:req-1",
        )
    )
    treatment = float(inputs.get("treatment_success", 0.7))
    control = float(inputs.get("control_success", 0.9))
    runner.evaluate(
        exp,
        with_intervention=lambda: {"task_success_rate": treatment},
        without_intervention=lambda: {"task_success_rate": control},
    )
    return {
        "status": exp.status,
        "retirement_candidates_nonempty": bool(runner.retirement_candidates()),
    }


def run_failure_attribution_trace(inputs: dict[str, Any]) -> dict[str, Any]:
    attrs = [attribute_error(err) for err in inputs.get("errors") or []]
    return {
        "categories": [a.category for a in attrs],
        "repeated_classes": detect_repeated_failure_classes(attrs),
    }


def run_trace_envelope_complete(inputs: dict[str, Any]) -> dict[str, Any]:
    env = TraceEnvelope.model_validate(inputs)
    return {"complete": envelope_complete(env), "missing": env.missing_fields()}


def run_eval_claims_compose(inputs: dict[str, Any]) -> dict[str, Any]:
    claims = [Claim.model_validate(c) for c in inputs.get("claims") or []]
    return compose_claims(claims)


def run_evaluator_compose_run(inputs: dict[str, Any]) -> dict[str, Any]:
    """Compose supplied claims without pretending to execute an independent grader."""
    params = EvaluatorComposeParams.model_validate(inputs)
    result = EvaluatorResult(
        evaluator_id=params.evaluator_id,
        version=params.version,
        held_out=params.held_out,
        claims=params.claims,
        counts=compose_claims(params.claims),
        passed=all_passed(params.claims),
    )
    return {**result.model_dump(mode="json"), "evidence_origin": "caller_supplied"}


def run_trial_reliability_metrics(inputs: dict[str, Any]) -> dict[str, Any]:
    trials = [Trial.model_validate(t) for t in inputs.get("trials") or []]
    k = int(inputs.get("k") or 1)
    rollup = trial_cost_rollup(trials)
    return {
        "pass_at_k_positive": pass_at_k(trials, k=k) > 0,
        "trials": rollup["trials"],
    }


def run_component_ablation_delta(inputs: dict[str, Any]) -> dict[str, Any]:
    exp = ComponentAblationExperiment.model_validate(inputs)
    return {"success_delta": ablation_delta(exp)["success_delta"]}


def run_harness_fingerprint_digest(inputs: dict[str, Any]) -> dict[str, Any]:
    a = build_harness_fingerprint(**inputs["a"])
    b = build_harness_fingerprint(**inputs["b"])
    stamped = require_eval_provenance(inputs["summary"], fingerprint=a)
    return {
        "digests_differ": a.digest() != b.digest(),
        "has_fingerprint": "harness_fingerprint" in stamped,
    }


def run_evaluation_outcome_filter(inputs: dict[str, Any]) -> dict[str, Any]:
    trials = [Trial.model_validate(t) for t in inputs.get("trials") or []]
    k = int(inputs.get("k") or 1)
    rollup = trial_cost_rollup(trials)
    return {
        "task_trials": int(rollup["task_trials"]),
        "non_task_trials": int(rollup["non_task_trials"]),
        "pass_at_k_is_one": pass_at_k(trials, k=k) == 1.0,
    }


def run_objective_policy_aggregate(inputs: dict[str, Any]) -> dict[str, Any]:
    policy = ObjectivePolicy.model_validate(inputs["policy"])
    claims = [Claim.model_validate(c) for c in inputs.get("claims") or []]
    result = aggregate_objective(policy, claims)
    return {
        "scored": result.scored,
        "scalar": result.scalar,
        "policy_id": result.policy_id,
    }


def run_experiment_lineage_resume(inputs: dict[str, Any]) -> dict[str, Any]:
    ckpt = ExperimentCheckpoint(
        experiment_id=inputs["experiment_id"],
        assignment=inputs.get("assignment") or "treatment",
    )
    for case_id in inputs.get("consume") or []:
        ckpt = ckpt.consume(case_id, evidence_digest=f"digest:{case_id}")
    duplicate_refused = False
    try:
        ckpt.consume((inputs.get("consume") or ["x"])[0])
    except ValueError:
        duplicate_refused = True
    return {
        "remaining": ckpt.remaining(list(inputs.get("corpus") or [])),
        "duplicate_refused": duplicate_refused,
    }


def run_trace_reconciliation_check(inputs: dict[str, Any]) -> dict[str, Any]:
    surfaces = [ObservationSurface.model_validate(s) for s in inputs.get("surfaces") or []]
    report = reconcile_traces(surfaces)
    return {"status": report.status, "ok": report.ok}


def run_eval_matrix_aggregate(inputs: dict[str, Any]) -> dict[str, Any]:
    matrix = EvalMatrix()
    for raw in inputs.get("trials") or []:
        trial = Trial(trial_id=raw["trial_id"], success=bool(raw["success"]))
        matrix.add_trial(
            trial,
            model=raw["model"],
            harness_fingerprint=raw["harness_fingerprint"],
            task_family=raw["task_family"],
        )
    agg = matrix.aggregate()
    return {
        "cell_count": agg["cell_count"],
        "fingerprints": [c["harness_fingerprint"] for c in agg["cells"]],
    }


def run_cross_harness_failure_classify(inputs: dict[str, Any]) -> dict[str, Any]:
    failure = classify_cross_harness_failure(str(inputs.get("message") or ""))
    return {"kind": failure.kind}


def run_learning_export_pack(inputs: dict[str, Any]) -> dict[str, Any]:
    pack = build_learning_export(
        harness_fingerprint=inputs.get("harness_fingerprint"),
        rollout_graph_ref=inputs.get("rollout_graph_ref"),
        split=inputs.get("split") or "train",
    )
    return {
        "schema_version": pack.schema_version,
        "harness_fingerprint": pack.harness_fingerprint,
    }


def run_experiment_dimensions_digest(inputs: dict[str, Any]) -> dict[str, Any]:
    dims = ExperimentDimensions(
        fixed=dict(inputs.get("fixed") or {}),
        varying=dict(inputs.get("varying") or {}),
    )
    fields = require_dimension_trace_fields({}, dimensions=dims)
    return {
        "has_digest": bool(fields.get("experiment_dimensions_digest")),
        "varying_tools": dims.fingerprint_parts()["varying"].get("tool_surface", []),
    }


def run_gated_objective_evaluate(inputs: dict[str, Any]) -> dict[str, Any]:
    runner = HarnessExperimentRunner()
    exp = runner.propose(HarnessExperiment(hypothesis="gated", intervention="x", failure_mode="y"))
    policy = ObjectivePolicy.model_validate(inputs["policy"])
    result = runner.evaluate(
        exp,
        with_intervention=lambda: dict(inputs["treatment"]),
        without_intervention=lambda: dict(inputs["control"]),
        objective_policy=policy,
    )
    return {"status": result.status}


def run_exposure_discriminative_report(inputs: dict[str, Any]) -> dict[str, Any]:
    ledger = ExposureLedger()
    for raw in inputs.get("exposure") or []:
        ledger.record(ExposureSample.model_validate(raw))
    trials = [Trial.model_validate(t) for t in inputs.get("trials") or []]
    summary = ledger.summarize()
    report = discriminative_report(trials)
    return {
        "treatment_model_calls": int(summary["arms"]["treatment"]["model_calls"]),
        "all_success_tie": report.all_success_tie,
    }


def run_efficiency_scorecard_build(inputs: dict[str, Any]) -> dict[str, Any]:
    card = build_efficiency_scorecard(**inputs)
    return {
        "tool_calls": card.dimensions.get("tool_calls"),
        "tokens_out": card.dimensions.get("tokens_out"),
    }


def run_layered_eval(inputs: dict[str, Any]) -> dict[str, Any]:
    """Report supplied verdicts; causal support remains the caller's assertion."""
    report: dict[str, Any] = {"evidence_origin": "caller_supplied"}
    for case in inputs.get("cases") or []:
        name = str(case["name"])
        scored = score_layers(
            task=case["task"],
            harness=case.get("harness"),
            harness_observed=bool(case.get("harness_observed", True)),
            infrastructure_failure=bool(case.get("infrastructure_failure", False)),
            trace_supports_cause=bool(case.get("trace_supports_cause", False)),
        )
        report[f"{name}_task"] = scored["task"]
        report[f"{name}_harness"] = scored["harness"]
        report[f"{name}_clean"] = scored["clean"]
        report[f"{name}_infrastructure"] = scored["infrastructure_failure"]
        report[f"{name}_attribution"] = scored["attribution"]
    return report


EVALUATION_RESEARCH_HANDLERS: dict[str, Any] = {
    "atk_research_reject": run_atk_research_reject,
    "harness_experiment_retire": run_harness_experiment_retire,
    "failure_attribution_trace": run_failure_attribution_trace,
    "trace_envelope_complete": run_trace_envelope_complete,
    "eval_claims_compose": run_eval_claims_compose,
    "evaluator_compose_run": run_evaluator_compose_run,
    "trial_reliability_metrics": run_trial_reliability_metrics,
    "component_ablation_delta": run_component_ablation_delta,
    "harness_fingerprint_digest": run_harness_fingerprint_digest,
    "evaluation_outcome_filter": run_evaluation_outcome_filter,
    "objective_policy_aggregate": run_objective_policy_aggregate,
    "experiment_lineage_resume": run_experiment_lineage_resume,
    "trace_reconciliation_check": run_trace_reconciliation_check,
    "eval_matrix_aggregate": run_eval_matrix_aggregate,
    "cross_harness_failure_classify": run_cross_harness_failure_classify,
    "learning_export_pack": run_learning_export_pack,
    "experiment_dimensions_digest": run_experiment_dimensions_digest,
    "gated_objective_evaluate": run_gated_objective_evaluate,
    "exposure_discriminative_report": run_exposure_discriminative_report,
    "efficiency_scorecard_build": run_efficiency_scorecard_build,
    "layered_eval": run_layered_eval,
}


__all__ = ["EVALUATION_RESEARCH_HANDLERS", "EvaluationResearchParams"]

EVALUATION_PARAMETER_MODELS: dict[str, type[BaseModel]] = {
    "atk_research_reject": ResearchEvaluationParams,
    "evaluator_compose_run": EvaluatorComposeParams,
}
