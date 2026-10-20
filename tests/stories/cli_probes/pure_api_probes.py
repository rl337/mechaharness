"""CLI probes for former ``pure_api`` library-surface stories."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel, ConfigDict

from mechaharness.advisor import (
    AdvisorContextContract,
    AdvisorRequest,
    DefaultAdvisorPolicy,
    RejectAdvisor,
    consult_advisor,
)
from mechaharness.cli_verb import CliProbe
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


class PureApiParams(BaseModel):
    """Open params bag — each pure_api probe validates only what it needs."""

    model_config = ConfigDict(extra="allow")


async def run_sparse_advisor(inputs: dict[str, Any]) -> dict[str, Any]:
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


def run_verification_outcome(inputs: dict[str, Any]) -> dict[str, Any]:
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


def run_wip_policy(inputs: dict[str, Any]) -> dict[str, Any]:
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


def run_fan_in_policy(inputs: dict[str, Any]) -> dict[str, Any]:
    policy = FanInPolicy(
        strategy=str(inputs.get("strategy") or "all"),
        quorum=inputs.get("quorum"),
    )
    return {"accepted": accept_fan_in(policy, results=list(inputs.get("results") or []))}


def run_exit_clean_state(inputs: dict[str, Any]) -> dict[str, Any]:
    report = evaluate_exit(
        CleanStateContract(require_handoff_record=bool(inputs.get("require_handoff_record"))),
        pending_nodes=list(inputs.get("pending_nodes") or []),
        checkpoint_durable=bool(inputs.get("checkpoint_durable")),
        unresolved_effects=list(inputs.get("unresolved_effects") or []),
        handoff_record_ref=inputs.get("handoff_record_ref"),
    )
    return {"ok": report.ok, "issues": report.issues}


def run_resume_cost(inputs: dict[str, Any]) -> dict[str, Any]:
    return summarize_resume_cost(ResumeCostMetrics.model_validate(inputs))


def run_coordination_cost(inputs: dict[str, Any]) -> dict[str, Any]:
    return summarize_coordination_cost(CoordinationCostMetrics.model_validate(inputs))


def run_loop_health(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"wind_down": should_wind_down(LoopHealthSignals.model_validate(inputs))}


def run_harness_health(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"needs_cleanup": needs_cleanup(HarnessHealthSnapshot.model_validate(inputs))}


def run_rule_promotion(inputs: dict[str, Any]) -> dict[str, Any]:
    rec = PromotionRecord(
        observed_pattern=str(inputs.get("observed_pattern") or ""),
        hypothesis=str(inputs.get("hypothesis") or ""),
        experiment_ref=inputs.get("experiment_ref"),
        soft_instruction_ref=inputs.get("soft_instruction_ref"),
    )
    hard_ref = str(inputs.get("hard_invariant_ref") or "h")
    hard = promote_soft_to_hard(rec, hard_invariant_ref=hard_ref)
    return {"stage": hard.stage}


def run_handoff_record(inputs: dict[str, Any]) -> dict[str, Any]:
    rec = HandoffRecord.model_validate(inputs)
    return {
        "next_action": rec.next_action,
        "goals": rec.goals,
        "exclusions": rec.exclusions,
        "verdict_kind": (rec.verdict or {}).get("kind"),
    }


def run_operation_compensation(inputs: dict[str, Any]) -> dict[str, Any]:
    contract = OperationContract.model_validate(inputs)
    return {
        "idempotent": contract.idempotent,
        "compensation_strategy": contract.compensation_strategy,
    }


def run_environment_delta(inputs: dict[str, Any]) -> dict[str, Any]:
    before = EnvironmentSnapshot.model_validate(inputs["before"])
    after = EnvironmentSnapshot.model_validate(inputs["after"])
    rebuilt = apply_deltas(before, [emit_delta(before, after)])
    return {"cwd": rebuilt.data.get("cwd")}


def run_specification_debt(inputs: dict[str, Any]) -> dict[str, Any]:
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


PURE_API_HANDLERS: dict[str, Any] = {
    "sparse_advisor": run_sparse_advisor,
    "verification_outcome": run_verification_outcome,
    "wip_policy": run_wip_policy,
    "fan_in_policy": run_fan_in_policy,
    "exit_clean_state": run_exit_clean_state,
    "resume_cost": run_resume_cost,
    "coordination_cost": run_coordination_cost,
    "loop_health": run_loop_health,
    "harness_health": run_harness_health,
    "rule_promotion": run_rule_promotion,
    "handoff_record": run_handoff_record,
    "operation_compensation": run_operation_compensation,
    "environment_delta": run_environment_delta,
    "specification_debt": run_specification_debt,
}


def _pure_api_probe(name: str, fn: Any) -> type[CliProbe]:
    class _P(CliProbe):
        async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
            del runtime
            assert isinstance(params, PureApiParams)
            out = fn(params.model_dump())
            if inspect.isawaitable(out):
                out = await out
            return out

    _P.name = name
    _P.params_model = PureApiParams
    _P.__name__ = f"{name}_probe"
    _P.__qualname__ = _P.__name__
    return _P


def pure_api_cli_probe_classes() -> dict[str, type[CliProbe]]:
    return {name: _pure_api_probe(name, fn) for name, fn in PURE_API_HANDLERS.items()}


__all__ = ["PURE_API_HANDLERS", "PureApiParams", "pure_api_cli_probe_classes"]
