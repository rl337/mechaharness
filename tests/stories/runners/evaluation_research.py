"""Evaluation, experiment, trace, and research story runners."""

from __future__ import annotations

from mechaharness.component_ablation import ComponentAblationExperiment, ablation_delta
from mechaharness.cross_harness_failure import classify_cross_harness_failure
from mechaharness.discriminative_value import discriminative_report
from mechaharness.efficiency_scorecard import build_efficiency_scorecard
from mechaharness.eval_evidence import Claim, compose_claims
from mechaharness.eval_matrix import EvalMatrix
from mechaharness.eval_trial import Trial, pass_at_k, trial_cost_rollup
from mechaharness.evaluator import (
    CallableEvaluator,
    EvaluatorResult,
    evaluate_claims,
)
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
from mechaharness.learning_export import build_learning_export
from mechaharness.objective_policy import ObjectivePolicy, aggregate_objective
from mechaharness.research import EvalProtocol, ResearchLab
from mechaharness.trace_envelope import TraceEnvelope, envelope_complete
from mechaharness.trace_reconciliation import ObservationSurface, reconcile_traces
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.runners._support import StoryRunner, _assert_expect


async def _run_atk_research_reject(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    lab = ResearchLab(
        EvalProtocol(task_split=request.get("task_split", "story-atk")),
        baseline_metric=float(request.get("baseline_metric", 0.9)),
    )
    for row in request.get("candidates", []):
        cand = lab.propose(row["hypothesis"], row.get("change_set", {}))
        lab.evaluate(
            cand,
            metric=float(row["metric"]),
            safety_ok=bool(row.get("safety_ok", True)),
            whole_task_cost=row.get("whole_task_cost"),
            ablations=row.get("ablations"),
        )
    accepted = [c for c in lab.candidates if c.status.value == "accepted"]
    if accepted:
        lab.promote(
            accepted[0],
            final_test=EvaluatorResult(
                evaluator_id="story:final_test", version="1", held_out=True, passed=True
            ),
        )
    report = lab.report()
    actual = {
        "rejected_cheap_nonempty": bool(report.rejected_cheap_failures),
        "promoted_nonempty": bool(report.promoted_id),
        "negative_results_nonempty": bool(report.negative_results),
    }
    _assert_expect(actual, expect)


async def _run_harness_experiment_retire(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    runner = HarnessExperimentRunner()
    exp = runner.propose(
        HarnessExperiment(
            hypothesis=str(request["hypothesis"]),
            intervention=str(request["intervention"]),
            failure_mode="token_bloat",
            evidence="inspiration:req-1",
        )
    )
    treatment = float(request.get("treatment_success", 0.7))
    control = float(request.get("control_success", 0.9))
    runner.evaluate(
        exp,
        with_intervention=lambda: {"task_success_rate": treatment},
        without_intervention=lambda: {"task_success_rate": control},
    )
    actual = {
        "status": exp.status,
        "retirement_candidates_nonempty": bool(runner.retirement_candidates()),
    }
    _assert_expect(actual, expect)


async def _run_failure_attribution_trace(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    attrs = [attribute_error(err) for err in request.get("errors") or []]
    actual = {
        "categories_include": [a.category for a in attrs],
        "repeated_classes_include": detect_repeated_failure_classes(attrs),
    }
    _assert_expect(actual, expect)


async def _run_trace_envelope_complete(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    env = TraceEnvelope.model_validate(request)
    actual = {"complete": envelope_complete(env), "missing": env.missing_fields()}
    _assert_expect(actual, expect)


async def _run_eval_claims_compose(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    claims = [Claim.model_validate(c) for c in request.get("claims") or []]
    actual = compose_claims(claims)
    _assert_expect(actual, expect)


async def _run_evaluator_compose_run(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    ev = CallableEvaluator(
        lambda subject: [
            Claim(
                id="exists",
                statement="exists",
                status="pass" if subject.get("exists") else "fail",
            )
        ],
        evaluator_id="story:exists",
        held_out=bool(request.get("held_out")),
    )
    result = evaluate_claims(ev, request)
    actual = {"passed": result.passed, "held_out": result.held_out}
    _assert_expect(actual, expect)


async def _run_trial_reliability_metrics(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    trials = [Trial.model_validate(t) for t in request.get("trials") or []]
    k = int(request.get("k") or 1)
    rollup = trial_cost_rollup(trials)
    actual = {
        "pass_at_k_positive": pass_at_k(trials, k=k) > 0,
        "trials": rollup["trials"],
    }
    _assert_expect(actual, expect)


async def _run_component_ablation_delta(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    exp = ComponentAblationExperiment.model_validate(request)
    actual = {"success_delta": ablation_delta(exp)["success_delta"]}
    _assert_expect(actual, expect)


async def _run_harness_fingerprint_digest(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    a = build_harness_fingerprint(**request["a"])
    b = build_harness_fingerprint(**request["b"])
    stamped = require_eval_provenance(request["summary"], fingerprint=a)
    actual = {
        "digests_differ": a.digest() != b.digest(),
        "has_fingerprint": "harness_fingerprint" in stamped,
    }
    _assert_expect(actual, expect)


async def _run_evaluation_outcome_filter(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    trials = [Trial.model_validate(t) for t in request.get("trials") or []]
    k = int(request.get("k") or 1)
    rollup = trial_cost_rollup(trials)
    actual = {
        "task_trials": int(rollup["task_trials"]),
        "non_task_trials": int(rollup["non_task_trials"]),
        "pass_at_k_is_one": pass_at_k(trials, k=k) == 1.0,
    }
    _assert_expect(actual, expect)


async def _run_objective_policy_aggregate(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    policy = ObjectivePolicy.model_validate(request["policy"])
    claims = [Claim.model_validate(c) for c in request.get("claims") or []]
    result = aggregate_objective(policy, claims)
    actual = {
        "scored": result.scored,
        "scalar": result.scalar,
        "policy_id": result.policy_id,
    }
    _assert_expect(actual, expect)


async def _run_experiment_lineage_resume(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    ckpt = ExperimentCheckpoint(
        experiment_id=request["experiment_id"],
        assignment=request.get("assignment") or "treatment",
    )
    for case_id in request.get("consume") or []:
        ckpt = ckpt.consume(case_id, evidence_digest=f"digest:{case_id}")
    duplicate_refused = False
    try:
        ckpt.consume((request.get("consume") or ["x"])[0])
    except ValueError:
        duplicate_refused = True
    actual = {
        "remaining": ckpt.remaining(list(request.get("corpus") or [])),
        "duplicate_refused": duplicate_refused,
    }
    _assert_expect(actual, expect)


async def _run_trace_reconciliation_check(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    surfaces = [ObservationSurface.model_validate(s) for s in request.get("surfaces") or []]
    report = reconcile_traces(surfaces)
    actual = {"status": report.status, "ok": report.ok}
    _assert_expect(actual, expect)


async def _run_eval_matrix_aggregate(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    matrix = EvalMatrix()
    for raw in request.get("trials") or []:
        trial = Trial(trial_id=raw["trial_id"], success=bool(raw["success"]))
        matrix.add_trial(
            trial,
            model=raw["model"],
            harness_fingerprint=raw["harness_fingerprint"],
            task_family=raw["task_family"],
        )
    agg = matrix.aggregate()
    actual = {
        "cell_count": agg["cell_count"],
        "fingerprints_include": [c["harness_fingerprint"] for c in agg["cells"]],
    }
    _assert_expect(actual, expect)


async def _run_cross_harness_failure_classify(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    failure = classify_cross_harness_failure(str(request.get("message") or ""))
    actual = {"kind": failure.kind}
    _assert_expect(actual, expect)


async def _run_learning_export_pack(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    pack = build_learning_export(
        harness_fingerprint=request.get("harness_fingerprint"),
        rollout_graph_ref=request.get("rollout_graph_ref"),
        split=request.get("split") or "train",
    )
    actual = {
        "schema_version": pack.schema_version,
        "harness_fingerprint": pack.harness_fingerprint,
    }
    _assert_expect(actual, expect)


async def _run_experiment_dimensions_digest(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    dims = ExperimentDimensions(
        fixed=dict(request.get("fixed") or {}),
        varying=dict(request.get("varying") or {}),
    )
    fields = require_dimension_trace_fields({}, dimensions=dims)
    actual = {
        "has_digest": bool(fields.get("experiment_dimensions_digest")),
        "varying_tools_include": dims.fingerprint_parts()["varying"].get(
            "tool_surface", []
        ),
    }
    _assert_expect(actual, expect)


async def _run_gated_objective_evaluate(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    runner = HarnessExperimentRunner()
    exp = runner.propose(
        HarnessExperiment(hypothesis="gated", intervention="x", failure_mode="y")
    )
    policy = ObjectivePolicy.model_validate(request["policy"])
    result = runner.evaluate(
        exp,
        with_intervention=lambda: dict(request["treatment"]),
        without_intervention=lambda: dict(request["control"]),
        objective_policy=policy,
    )
    actual = {"status": result.status}
    _assert_expect(actual, expect)


async def _run_exposure_discriminative_report(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    ledger = ExposureLedger()
    for raw in request.get("exposure") or []:
        ledger.record(ExposureSample.model_validate(raw))
    trials = [Trial.model_validate(t) for t in request.get("trials") or []]
    summary = ledger.summarize()
    report = discriminative_report(trials)
    actual = {
        "treatment_model_calls": int(summary["arms"]["treatment"]["model_calls"]),
        "all_success_tie": report.all_success_tie,
    }
    _assert_expect(actual, expect)


async def _run_efficiency_scorecard_build(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    card = build_efficiency_scorecard(**request)
    actual = {
        "tool_calls": card.dimensions.get("tool_calls"),
        "tokens_out": card.dimensions.get("tokens_out"),
    }
    _assert_expect(actual, expect)



RUNNERS: dict[str, StoryRunner] = {
    "atk_research_reject": _run_atk_research_reject,
    "harness_experiment_retire": _run_harness_experiment_retire,
    "failure_attribution_trace": _run_failure_attribution_trace,
    "trace_envelope_complete": _run_trace_envelope_complete,
    "eval_claims_compose": _run_eval_claims_compose,
    "evaluator_compose_run": _run_evaluator_compose_run,
    "trial_reliability_metrics": _run_trial_reliability_metrics,
    "component_ablation_delta": _run_component_ablation_delta,
    "harness_fingerprint_digest": _run_harness_fingerprint_digest,
    "evaluation_outcome_filter": _run_evaluation_outcome_filter,
    "objective_policy_aggregate": _run_objective_policy_aggregate,
    "experiment_lineage_resume": _run_experiment_lineage_resume,
    "trace_reconciliation_check": _run_trace_reconciliation_check,
    "eval_matrix_aggregate": _run_eval_matrix_aggregate,
    "cross_harness_failure_classify": _run_cross_harness_failure_classify,
    "learning_export_pack": _run_learning_export_pack,
    "experiment_dimensions_digest": _run_experiment_dimensions_digest,
    "gated_objective_evaluate": _run_gated_objective_evaluate,
    "exposure_discriminative_report": _run_exposure_discriminative_report,
    "efficiency_scorecard_build": _run_efficiency_scorecard_build,
}
