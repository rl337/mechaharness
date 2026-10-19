"""Small inspiration-primitive story runners (policies, schemas, summaries)."""

from __future__ import annotations

from typing import Any

from mechaharness.advisor import (
    AdvisorContextContract,
    AdvisorRequest,
    DefaultAdvisorPolicy,
    RejectAdvisor,
    consult_advisor,
)
from mechaharness.coordination_cost import CoordinationCostMetrics, summarize_coordination_cost
from mechaharness.environment_delta import EnvironmentSnapshot, apply_deltas, emit_delta
from mechaharness.exit_contract import CleanStateContract, evaluate_exit
from mechaharness.fan_in_policy import FanInPolicy, accept_fan_in
from mechaharness.graph import (
    GraphNode,
    VerificationOracle,
)
from mechaharness.handoff_record import HandoffRecord
from mechaharness.harness_health import HarnessHealthSnapshot, needs_cleanup
from mechaharness.loop_health import LoopHealthSignals, should_wind_down
from mechaharness.operation_registry import (
    OperationContract,
)
from mechaharness.outcome_contract import OutcomeContract
from mechaharness.resume_cost import ResumeCostMetrics, summarize_resume_cost
from mechaharness.rule_promotion import PromotionRecord, promote_soft_to_hard
from mechaharness.verification_policy import DefaultVerificationPolicy
from mechaharness.work_in_progress_policy import WorkInProgressPolicy
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.runners._support import StoryRunner, _assert_expect


async def _run_sparse_advisor_consult(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    policy = DefaultAdvisorPolicy(max_consultations=int(request.get("max_consultations", 1)))
    observations: list[Any] = []
    trigger = request.get("trigger", "consequential_planning")
    first = await consult_advisor(
        RejectAdvisor(),
        policy,
        AdvisorRequest(
            trigger=trigger,
            context=AdvisorContextContract(summary="plan boundary"),
        ),
        observations=observations,
    )
    second = await consult_advisor(
        RejectAdvisor(),
        policy,
        AdvisorRequest(trigger=trigger),
        observations=observations,
    )
    actual = {
        "first_consult_ok": first is not None,
        "second_consult_blocked": second is None,
        "observation_count": len(observations),
    }
    _assert_expect(actual, expect)


async def _run_verification_outcome_gate(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    outcome = OutcomeContract(require_verification=bool(request.get("require_verification", True)))
    before = outcome.evaluate(answer_generated=True, verification_passed=None)
    policy = DefaultVerificationPolicy()
    node = GraphNode(id="n", kind="compute")

    def good(_node: GraphNode) -> tuple[bool, dict[str, Any]]:
        return True, {"ok": True}

    result = policy.verify(
        node,
        oracles=[VerificationOracle(name="exec", strength="executable")],
        verifiers=[good],
        outcome=outcome,
        answer_generated=True,
    )
    actual = {
        "before_verify_completion": before,
        "after_verify_completion": result.completion,
        "verification_passed": result.passed,
    }
    _assert_expect(actual, expect)


async def _run_wip_policy_allows(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    policy = WorkInProgressPolicy(
        max_active_nodes=request.get("max_active_nodes"),
        max_per_write_scope=request.get("max_per_write_scope"),
    )
    active = int(request.get("active_nodes") or 0)
    actual = {
        "allows_new_scope": policy.allows(
            active_nodes=active, write_scope="other", active_in_scope=0
        ),
        "allows_same_scope": policy.allows(
            active_nodes=active,
            write_scope="repo",
            active_in_scope=int(request.get("active_in_scope") or 0),
        ),
    }
    _assert_expect(actual, expect)


async def _run_fan_in_policy_accept(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    policy = FanInPolicy(
        strategy=str(request.get("strategy") or "all"),
        quorum=request.get("quorum"),
    )
    actual = {"accepted": accept_fan_in(policy, results=list(request.get("results") or []))}
    _assert_expect(actual, expect)


async def _run_exit_clean_state_eval(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    report = evaluate_exit(
        CleanStateContract(require_handoff_record=bool(request.get("require_handoff_record"))),
        pending_nodes=list(request.get("pending_nodes") or []),
        checkpoint_durable=bool(request.get("checkpoint_durable")),
        unresolved_effects=list(request.get("unresolved_effects") or []),
        handoff_record_ref=request.get("handoff_record_ref"),
    )
    actual = {"ok": report.ok, "issues": report.issues}
    _assert_expect(actual, expect)


async def _run_resume_cost_summarize(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    actual = summarize_resume_cost(ResumeCostMetrics.model_validate(request))
    _assert_expect(actual, expect)


async def _run_coordination_cost_summarize(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    actual = summarize_coordination_cost(CoordinationCostMetrics.model_validate(request))
    _assert_expect(actual, expect)


async def _run_loop_health_wind_down(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    actual = {"wind_down": should_wind_down(LoopHealthSignals.model_validate(request))}
    _assert_expect(actual, expect)


async def _run_harness_health_cleanup(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    actual = {"needs_cleanup": needs_cleanup(HarnessHealthSnapshot.model_validate(request))}
    _assert_expect(actual, expect)


async def _run_rule_promotion_hard(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    rec = PromotionRecord(
        observed_pattern=str(request.get("observed_pattern") or ""),
        hypothesis=str(request.get("hypothesis") or ""),
        experiment_ref=request.get("experiment_ref"),
        soft_instruction_ref=request.get("soft_instruction_ref"),
    )
    hard_ref = str(request.get("hard_invariant_ref") or "h")
    hard = promote_soft_to_hard(rec, hard_invariant_ref=hard_ref)
    actual = {"stage": hard.stage}
    _assert_expect(actual, expect)


async def _run_handoff_record_fields(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    rec = HandoffRecord.model_validate(request)
    actual = {
        "next_action": rec.next_action,
        "goals": rec.goals,
        "exclusions": rec.exclusions,
        "verdict_kind": (rec.verdict or {}).get("kind"),
    }
    actual = {k: v for k, v in actual.items() if k in expect}
    _assert_expect(actual, expect)


async def _run_operation_compensation_meta(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    op = OperationContract.model_validate(request)
    actual = {
        "idempotent": op.idempotent,
        "compensation_strategy": op.compensation_strategy,
    }
    _assert_expect(actual, expect)


async def _run_environment_delta_apply(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    before = EnvironmentSnapshot.model_validate(request["before"])
    after = EnvironmentSnapshot.model_validate(request["after"])
    rebuilt = apply_deltas(before, [emit_delta(before, after)])
    actual = {"cwd": rebuilt.data.get("cwd")}
    _assert_expect(actual, expect)


async def _run_specification_debt_capture(case: StoryCase, backend: StoryBackend) -> None:
    """Corrections become reviewable debt linked to a promotion record (MH-PA-07)."""
    del backend
    from mechaharness.rule_promotion import (
        PromotionRecord,
        SpecificationDebtLedger,
        capture_correction,
    )

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    promotion = PromotionRecord.model_validate(request["promotion"])
    ledger = SpecificationDebtLedger()
    item = ledger.add(
        capture_correction(
            request["correction"],
            failing_scenarios=request["failing_scenarios"],
            promotion=promotion,
        )
    )
    captured = {
        "status": item.status,
        "review_required": item.review_required,
        "promotion_record_id": item.promotion_record_id,
        "failing_scenario_refs": item.failing_scenario_refs,
        "generated_test_ref": item.generated_test_ref,
    }
    pending_at_capture = len(ledger.pending_review())
    linked = ledger.update(item.link_test(request["host_test_ref"]))
    pending_after_test = len(ledger.pending_review())
    closed = ledger.update(linked.approve())
    try:
        capture_correction("  ")
        blank_refused = False
    except ValueError:
        blank_refused = True
    actual = {
        "captured": captured,
        "pending_at_capture": pending_at_capture,
        "status_after_test": linked.status,
        "pending_after_test": pending_after_test,
        "status_after_review": closed.status,
        "pending_after_review": len(ledger.pending_review()),
        "linked_to_promotion": [r.id for r in ledger.for_promotion(promotion.record_id or "")]
        == [item.id],
        "blank_refused": blank_refused,
    }
    _assert_expect(actual, expect)



RUNNERS: dict[str, StoryRunner] = {
    "sparse_advisor_consult": _run_sparse_advisor_consult,
    "verification_outcome_gate": _run_verification_outcome_gate,
    "wip_policy_allows": _run_wip_policy_allows,
    "fan_in_policy_accept": _run_fan_in_policy_accept,
    "exit_clean_state_eval": _run_exit_clean_state_eval,
    "resume_cost_summarize": _run_resume_cost_summarize,
    "coordination_cost_summarize": _run_coordination_cost_summarize,
    "loop_health_wind_down": _run_loop_health_wind_down,
    "harness_health_cleanup": _run_harness_health_cleanup,
    "rule_promotion_hard": _run_rule_promotion_hard,
    "handoff_record_fields": _run_handoff_record_fields,
    "operation_compensation_meta": _run_operation_compensation_meta,
    "environment_delta_apply": _run_environment_delta_apply,
    "specification_debt_capture": _run_specification_debt_capture,
}
