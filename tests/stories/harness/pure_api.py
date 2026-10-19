"""``pure_api`` harness: build / call / assert dict — no graph or HTTP substrate."""

from __future__ import annotations

import inspect
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
from mechaharness.graph import GraphNode, VerificationOracle
from mechaharness.handoff_record import HandoffRecord
from mechaharness.harness_health import HarnessHealthSnapshot, needs_cleanup
from mechaharness.loop_health import LoopHealthSignals, should_wind_down
from mechaharness.operation_registry import OperationContract
from mechaharness.outcome_contract import OutcomeContract
from mechaharness.resume_cost import ResumeCostMetrics, summarize_resume_cost
from mechaharness.rule_promotion import (
    PromotionRecord,
    SpecificationDebtLedger,
    capture_correction,
    promote_soft_to_hard,
)
from mechaharness.verification_policy import DefaultVerificationPolicy
from mechaharness.work_in_progress_policy import WorkInProgressPolicy
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.harness.base import PureApiOp, assert_expect, split_request


async def _sparse_advisor(inputs: dict[str, Any]) -> dict[str, Any]:
    policy = DefaultAdvisorPolicy(max_consultations=int(inputs.get("max_consultations", 1)))
    observations: list[Any] = []
    trigger = inputs.get("trigger", "consequential_planning")
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
    return {
        "first_consult_ok": first is not None,
        "second_consult_blocked": second is None,
        "observation_count": len(observations),
    }


def _verification_outcome(inputs: dict[str, Any]) -> dict[str, Any]:
    outcome = OutcomeContract(
        require_verification=bool(inputs.get("require_verification", True))
    )
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
    return {
        "before_verify_completion": before,
        "after_verify_completion": result.completion,
        "verification_passed": result.passed,
    }


def _wip_policy(inputs: dict[str, Any]) -> dict[str, Any]:
    policy = WorkInProgressPolicy(
        max_active_nodes=inputs.get("max_active_nodes"),
        max_per_write_scope=inputs.get("max_per_write_scope"),
    )
    active = int(inputs.get("active_nodes") or 0)
    return {
        "allows_new_scope": policy.allows(
            active_nodes=active, write_scope="other", active_in_scope=0
        ),
        "allows_same_scope": policy.allows(
            active_nodes=active,
            write_scope="repo",
            active_in_scope=int(inputs.get("active_in_scope") or 0),
        ),
    }


def _fan_in_policy(inputs: dict[str, Any]) -> dict[str, Any]:
    policy = FanInPolicy(
        strategy=str(inputs.get("strategy") or "all"),
        quorum=inputs.get("quorum"),
    )
    return {"accepted": accept_fan_in(policy, results=list(inputs.get("results") or []))}


def _exit_clean_state(inputs: dict[str, Any]) -> dict[str, Any]:
    report = evaluate_exit(
        CleanStateContract(require_handoff_record=bool(inputs.get("require_handoff_record"))),
        pending_nodes=list(inputs.get("pending_nodes") or []),
        checkpoint_durable=bool(inputs.get("checkpoint_durable")),
        unresolved_effects=list(inputs.get("unresolved_effects") or []),
        handoff_record_ref=inputs.get("handoff_record_ref"),
    )
    return {"ok": report.ok, "issues": report.issues}


def _resume_cost(inputs: dict[str, Any]) -> dict[str, Any]:
    return summarize_resume_cost(ResumeCostMetrics.model_validate(inputs))


def _coordination_cost(inputs: dict[str, Any]) -> dict[str, Any]:
    return summarize_coordination_cost(CoordinationCostMetrics.model_validate(inputs))


def _loop_health(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"wind_down": should_wind_down(LoopHealthSignals.model_validate(inputs))}


def _harness_health(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"needs_cleanup": needs_cleanup(HarnessHealthSnapshot.model_validate(inputs))}


def _rule_promotion(inputs: dict[str, Any]) -> dict[str, Any]:
    rec = PromotionRecord(
        observed_pattern=str(inputs.get("observed_pattern") or ""),
        hypothesis=str(inputs.get("hypothesis") or ""),
        experiment_ref=inputs.get("experiment_ref"),
        soft_instruction_ref=inputs.get("soft_instruction_ref"),
    )
    hard_ref = str(inputs.get("hard_invariant_ref") or "h")
    hard = promote_soft_to_hard(rec, hard_invariant_ref=hard_ref)
    return {"stage": hard.stage}


def _handoff_record(inputs: dict[str, Any]) -> dict[str, Any]:
    rec = HandoffRecord.model_validate(inputs)
    return {
        "next_action": rec.next_action,
        "goals": rec.goals,
        "exclusions": rec.exclusions,
        "verdict_kind": (rec.verdict or {}).get("kind"),
    }


def _operation_compensation(inputs: dict[str, Any]) -> dict[str, Any]:
    contract = OperationContract.model_validate(inputs)
    return {
        "idempotent": contract.idempotent,
        "compensation_strategy": contract.compensation_strategy,
    }


def _environment_delta(inputs: dict[str, Any]) -> dict[str, Any]:
    before = EnvironmentSnapshot.model_validate(inputs["before"])
    after = EnvironmentSnapshot.model_validate(inputs["after"])
    rebuilt = apply_deltas(before, [emit_delta(before, after)])
    return {"cwd": rebuilt.data.get("cwd")}


def _specification_debt(inputs: dict[str, Any]) -> dict[str, Any]:
    promotion = PromotionRecord.model_validate(inputs["promotion"])
    ledger = SpecificationDebtLedger()
    item = ledger.add(
        capture_correction(
            inputs["correction"],
            failing_scenarios=inputs["failing_scenarios"],
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
    linked = ledger.update(item.link_test(inputs["host_test_ref"]))
    pending_after_test = len(ledger.pending_review())
    closed = ledger.update(linked.approve())
    try:
        capture_correction("  ")
        blank_refused = False
    except ValueError:
        blank_refused = True
    return {
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


# Stable op ids (fixtures use these; not the old kind strings).
PURE_API_OPS: dict[str, PureApiOp] = {
    "sparse_advisor": _sparse_advisor,
    "verification_outcome": _verification_outcome,
    "wip_policy": _wip_policy,
    "fan_in_policy": _fan_in_policy,
    "exit_clean_state": _exit_clean_state,
    "resume_cost": _resume_cost,
    "coordination_cost": _coordination_cost,
    "loop_health": _loop_health,
    "harness_health": _harness_health,
    "rule_promotion": _rule_promotion,
    "handoff_record": _handoff_record,
    "operation_compensation": _operation_compensation,
    "environment_delta": _environment_delta,
    "specification_debt": _specification_debt,
}

# Old kind → op (fixture migration / docs).
PURE_API_KIND_TO_OP: dict[str, str] = {
    "sparse_advisor_consult": "sparse_advisor",
    "verification_outcome_gate": "verification_outcome",
    "wip_policy_allows": "wip_policy",
    "fan_in_policy_accept": "fan_in_policy",
    "exit_clean_state_eval": "exit_clean_state",
    "resume_cost_summarize": "resume_cost",
    "coordination_cost_summarize": "coordination_cost",
    "loop_health_wind_down": "loop_health",
    "harness_health_cleanup": "harness_health",
    "rule_promotion_hard": "rule_promotion",
    "handoff_record_fields": "handoff_record",
    "operation_compensation_meta": "operation_compensation",
    "environment_delta_apply": "environment_delta",
    "specification_debt_capture": "specification_debt",
}


class PureApiHarness:
    """Harness family ``pure_api``."""

    name = "pure_api"

    def known_ops(self) -> frozenset[str]:
        return frozenset(PURE_API_OPS)

    async def run(self, case: StoryCase, backend: StoryBackend) -> None:
        del backend
        request = case.load_json("request.json")
        expect = case.load_json("expect.json")
        op, inputs = split_request(request)
        try:
            handler = PURE_API_OPS[op]
        except KeyError as exc:
            known = ", ".join(sorted(PURE_API_OPS))
            raise ValueError(
                f"{case.label}: unknown op {op!r} for harness pure_api; known: {known}"
            ) from exc
        result = handler(inputs)
        if inspect.isawaitable(result):
            actual = await result
        else:
            actual = result
        if op == "handoff_record":
            actual = {k: v for k, v in actual.items() if k in expect}
        assert_expect(actual, expect)
