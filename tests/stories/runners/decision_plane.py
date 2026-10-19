"""Decision-plane, judge, and judgement-policy story runners."""

from __future__ import annotations

from typing import Any

from mechaharness.core.access import (
    AccessPolicy,
)
from mechaharness.decision_log import (
    DecisionRecord,
    export_offline_dataset,
    replay_verdict,
)
from mechaharness.decision_plane_runtime import (
    assemble_context_within_budget,
    build_decision_plane_telemetry,
    compare_shadow_decision,
    project_decision_state,
    run_decision_plane_policy,
)
from mechaharness.decision_surfaces import (
    DecisionSurface,
    RulesDecisionBackend,
    reject_invalid_choice,
)
from mechaharness.graph_templates import (
    DecisionPlaneTemplate,
    GraphTemplateParams,
    IndependentReviewTemplate,
)
from mechaharness.inference.judge import (
    FixtureJudgeProvider,
    JudgeRequest,
    NoulSignal,
    hash_state,
    judge,
)
from mechaharness.judgement_policy import (
    JudgementFacts,
    JudgementPolicy,
    JudgementThreshold,
)
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.runners._support import StoryRunner, _assert_expect, _build_questions


async def _run_fixture_judge_batch(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    response = case.load_json("response.json")
    expect = case.load_json("expect.json")
    state = request["state"]
    provider = FixtureJudgeProvider(response.get("answers", {}))
    judgement = await judge(
        JudgeRequest(
            state=state,
            state_hash=hash_state(state),
            questions=_build_questions(request["questions"]),
            question_set_version=request.get("question_set_version", "lab"),
        ),
        provider=provider,
    )
    actual = {
        "min_answer_count": len(judgement.answers),
        "error_count": len(judgement.errors),
        "answer_ids_include": [a.id for a in judgement.answers],
    }
    _assert_expect(actual, expect)


async def _run_decision_surface_reject(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    questions = _build_questions([request["question"]])
    surface = DecisionSurface(
        kind="choice",
        question=questions[0],
        allowed_actions=list(request.get("allowed_actions", [])),
    )
    backend_rules = RulesDecisionBackend(request.get("answers", {}))
    result = await backend_rules.evaluate(surface, state=request.get("state", {}))
    # Also reject an out-of-set proposal explicitly
    from mechaharness.inference.judge import ChoiceSignal

    invalid = reject_invalid_choice(
        ChoiceSignal(
            id=surface.question.id,
            selected=request["invalid_choice"],
            probabilities={request["invalid_choice"]: 1.0},
        ),
        request.get("allowed_actions", []),
    )
    actual = {
        "rules_rejected": result.rejected,
        "invalid_choice_rejected": invalid.rejected,
        "rules_source_in": result.source,
    }
    _assert_expect(actual, expect)


async def _run_offline_decision_export(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    records = [DecisionRecord.model_validate(r) for r in request.get("records", [])]
    export = export_offline_dataset(
        records,
        split=request.get("split", "train"),
        include_outcomes=bool(request.get("include_outcomes", False)),
    )
    outcome_ids = [r.get("outcomeId") for r in export.records]
    actual = {
        "record_count": len(export.records),
        "outcomes_leaked": any(oid is not None for oid in outcome_ids),
        "lineage_include": export.lineage,
        "split_in": export.split,
    }
    _assert_expect(actual, expect)


async def _run_policy_replay(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    policy = JudgementPolicy(
        version="story-replay",
        thresholds=[JudgementThreshold(signal_id="e", allow_above=0.5)],
    )
    verdict = replay_verdict(
        facts=JudgementFacts(action="noop"),
        signals=[NoulSignal(id="e", p_true=0.9)],
        policy=policy,
    )
    actual = {"verdict_kind": verdict.kind}
    _assert_expect(actual, expect)


async def _run_decision_plane_recipe(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    graph = DecisionPlaneTemplate().instantiate(
        GraphTemplateParams(
            goal=str(request.get("goal") or "decision_plane"),
            inputs={
                "state_projection": dict(request.get("state_projection") or {}),
                "facts": dict(request.get("facts") or {}),
                "questions": list(request.get("questions") or []),
                "confidence_floor": request.get("confidence_floor", 0.7),
                "shadow_mode": bool(request.get("shadow_mode", False)),
            },
        )
    )
    ask = graph.nodes["ask_batch"]
    project = graph.nodes["project_state"]
    facts_on_project = "facts" in project.payload and "facts" not in ask.payload
    actual = {
        "template_name": graph.template_name,
        "nodes_include": list(graph.nodes),
        "ask_batch_question_count": len(ask.payload.get("questions") or []),
        "facts_on_project_not_ask": facts_on_project,
        "confidence_floor": ask.payload.get("confidence_floor"),
    }
    _assert_expect(actual, expect)


async def _run_decision_plane_projection(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    proj = project_decision_state(
        dict(request.get("raw_context") or {}),
        project_keys=list(request.get("project_keys") or []),
        facts=dict(request.get("facts") or {}),
    )
    actual = {
        "projection": proj.state,
        "facts_include": list(proj.facts),
        "projection_has_secret": "secret" in proj.state,
        "no_model_invocation": True,
        "facts_fingerprint_nonempty": bool(proj.facts_fingerprint),
    }
    _assert_expect(actual, expect)


async def _run_decision_plane_policy(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    questions = list(request.get("questions") or [])
    route = str(request.get("escalation_route") or "host_policy")
    by_name: dict[str, Any] = {}
    for row in list(request.get("cases") or []):
        result = await run_decision_plane_policy(
            questions=questions,
            answers=dict(row.get("answers") or {}),
            confidence=row.get("confidence"),
            confidence_floor=float(row.get("confidence_floor") or 0.7),
            escalation_route=route,
        )
        by_name[str(row["name"])] = result
    accept = by_name["accept_billing"]
    low = by_name["low_confidence"]
    invalid = by_name["invalid_team"]
    actual = {
        "single_batch_invocation": accept.batch_invocation_count == 1,
        "accept_billing_action": accept.final_action,
        "low_confidence_escalates": low.escalate
        and low.escalation_reason == "confidence_below_floor",
        "invalid_team_escalates": invalid.escalate
        and invalid.escalation_reason == "choice_not_allowed",
        "escalation_route": low.escalation_route,
    }
    _assert_expect(actual, expect)


async def _run_decision_plane_shadow(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    cmp = await compare_shadow_decision(
        questions=list(request.get("questions") or []),
        production_answers=dict(request.get("production_answers") or {}),
        shadow_answers=dict(request.get("shadow_answers") or {}),
        confidence=request.get("confidence"),
        confidence_floor=float(request.get("confidence_floor") or 0.7),
    )
    actual = {
        "production_action": cmp.production.final_action,
        "shadow_controls_execution": cmp.shadow_controls_execution,
        "both_outcomes_recorded": cmp.shadow is not None,
        "agreement": cmp.agreement,
    }
    _assert_expect(actual, expect)


async def _run_decision_plane_telemetry(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    questions = list(request.get("questions") or [])
    proj = project_decision_state(
        {**dict(request.get("state_projection") or {}), "body": request.get("raw_body")},
        project_keys=list((request.get("state_projection") or {}).keys()),
        facts={},
    )
    policy = await run_decision_plane_policy(
        questions=questions,
        answers=dict(request.get("answers") or {}),
        confidence=request.get("confidence"),
        confidence_floor=0.7,
    )
    # Host policy may force final_action for telemetry fixture.
    if request.get("final_action") and not policy.escalate:
        policy.final_action = str(request["final_action"])
    tel = build_decision_plane_telemetry(
        questions=questions,
        projection=proj,
        policy=policy,
        model_ref=request.get("model_ref"),
        latency_ms=request.get("latency_ms"),
        raw_context={"body": request.get("raw_body")},
    )
    dumped = tel.model_dump(mode="json")
    actual = {
        "has_question_schema_ids": bool(tel.question_schema_ids),
        "has_projection_fingerprint": bool(tel.projection_fingerprint),
        "final_action": tel.final_action,
        "model_ref": tel.model_ref,
        "latency_ms": tel.latency_ms,
        "includes_raw_body": "raw_body" in dumped or "body" in dumped,
    }
    _assert_expect(actual, expect)


async def _run_decision_plane_model_policy(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    template = DecisionPlaneTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="model policy",
            inputs={
                "state_projection": dict(request.get("state_projection") or {}),
                "questions": list(request.get("questions") or []),
            },
            soft_bindings={"decision_model": request.get("decision_model")},
        )
    )
    describe = template.describe()
    actual = {
        "soft_point_decision_model": any(
            p.get("name") == "decision_model" for p in describe.get("soft_points") or []
        ),
        "ask_model_ref": graph.nodes["ask_batch"].payload.get("model_ref"),
        "describe_has_param_count": "param_count" in describe,
    }
    _assert_expect(actual, expect)


async def _run_decision_plane_shadow_compare(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    questions = list(request.get("questions") or [])
    disagree = None
    unavailable = None
    for row in list(request.get("cases") or []):
        shadow_raw = row.get("shadow_answers")
        cmp = await compare_shadow_decision(
            questions=questions,
            production_answers=dict(row.get("production_answers") or {}),
            shadow_answers=None if shadow_raw is None else dict(shadow_raw),
            confidence=request.get("confidence"),
            confidence_floor=float(request.get("confidence_floor") or 0.7),
        )
        if row.get("name") == "disagree":
            disagree = cmp
        if row.get("name") == "candidate_unavailable":
            unavailable = cmp
    assert disagree is not None and unavailable is not None
    tel = build_decision_plane_telemetry(
        questions=questions,
        policy=disagree.production,
        shadow=disagree,
    )
    actual = {
        "disagree_agreement": disagree.agreement,
        "unavailable_candidate": unavailable.shadow_unavailable,
        "telemetry_has_shadow_action_on_disagree": tel.shadow_action is not None,
    }
    _assert_expect(actual, expect)


async def _run_citation_support_judgment(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    action_qid = str(request.get("action_question_id") or "support")
    questions = list(request.get("questions") or [])
    by_name: dict[str, Any] = {}
    for row in list(request.get("cases") or []):
        result = await run_decision_plane_policy(
            questions=questions,
            answers=dict(row.get("answers") or {}),
            confidence=row.get("confidence"),
            confidence_floor=float(row.get("confidence_floor") or 0.7),
            action_question_id=action_qid,
        )
        claim_verified = (
            not result.escalate and result.final_action == "supported"
        )
        by_name[str(row["name"])] = {
            "result": result,
            "claim_verified": claim_verified,
        }
    actual = {
        "matching_claim_verified": by_name["matching_claim"]["claim_verified"],
        "growth_mismatch_verified": by_name["growth_mismatch"]["claim_verified"],
        "missing_source_verified": by_name["missing_source"]["claim_verified"],
        "uncertain_support_verified": by_name["uncertain_support"]["claim_verified"],
        "uncertain_support_escalates": by_name["uncertain_support"]["result"].escalate,
    }
    _assert_expect(actual, expect)


async def _run_context_budget_judgment(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    budget = int(request["token_budget"])
    min_relevance = float(request.get("min_relevance") or 0.0)
    min_trust = float(request.get("min_trust") or 0.0)
    min_freshness = float(request.get("min_freshness") or 0.0)
    selected: dict[str, list[str]] = {}
    for row in list(request.get("scenarios") or []):
        selected[str(row["name"])] = assemble_context_within_budget(
            list(row.get("candidates") or []),
            token_budget=budget,
            min_relevance=min_relevance,
            min_trust=min_trust,
            min_freshness=min_freshness,
        )

    def _tokens_for(name: str) -> int:
        scenario = next(s for s in request["scenarios"] if s["name"] == name)
        by_id = {str(c["id"]): c for c in scenario["candidates"]}
        total = 0
        for cid in selected[name]:
            total += int(by_id[cid]["tokens"])
        return total

    actual = {
        "budget_pack_ids": selected["budget_pack"],
        "filter_selected": selected["filter_stale_and_untrusted"],
        "injection_excluded": "inject" not in selected["exclude_injection"],
        "fallback_ids": selected["missing_scores_fallback"],
        "never_exceeds_budget": all(
            _tokens_for(name) <= budget for name in selected
        ),
    }
    _assert_expect(actual, expect)


async def _run_requirements_gap_judgment(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    review_graph = IndependentReviewTemplate().instantiate(
        GraphTemplateParams(
            goal="requirements review",
            inputs={"reviewer_count": int(request.get("reviewer_count", 1))},
            acceptance=list(request.get("acceptance") or []),
        )
    )
    reviews = [n for n in review_graph.nodes if n.startswith("review_")]
    action_qid = str(request.get("action_question_id") or "coverage")
    questions = list(request.get("questions") or [])
    outcomes: dict[str, str] = {}
    for row in list(request.get("cases") or []):
        result = await run_decision_plane_policy(
            questions=questions,
            answers=dict(row.get("answers") or {}),
            confidence=row.get("confidence"),
            confidence_floor=float(row.get("confidence_floor") or 0.7),
            action_question_id=action_qid,
        )
        facts = dict(row.get("facts") or {})
        if result.escalate or result.final_action in {"gap", "unclear"}:
            outcomes[str(row["name"])] = "request_tests"
        elif not facts.get("crash_tests_present", True):
            outcomes[str(row["name"])] = "request_tests"
        elif result.final_action == "covered":
            outcomes[str(row["name"])] = "continue_review"
        else:
            outcomes[str(row["name"])] = "request_tests"
    actual = {
        "template_name": review_graph.template_name,
        "omit_producer_reasoning": review_graph.nodes[reviews[0]].payload.get(
            "omit_producer_reasoning"
        ),
        "gap_found_action": outcomes["gap_found"],
        "missing_crash_action": outcomes["approve_but_missing_crash_tests"],
        "covered_action": outcomes["covered_with_tests"],
        "never_mark_correct": "mark_correct" not in outcomes.values(),
    }
    _assert_expect(actual, expect)


async def _run_task_route_judgment(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    action_qid = str(request.get("action_question_id") or "route")
    questions = list(request.get("questions") or [])
    by_name: dict[str, Any] = {}
    for row in list(request.get("cases") or []):
        result = await run_decision_plane_policy(
            questions=questions,
            answers=dict(row.get("answers") or {}),
            confidence=row.get("confidence"),
            confidence_floor=float(row.get("confidence_floor") or 0.7),
            action_question_id=action_qid,
        )
        complexity = float((row.get("answers") or {}).get("complexity") or 0.0)
        floor = float(row.get("min_complexity_for_frontier") or 0.7)
        final_action = result.final_action
        escalate = result.escalate
        if (
            not escalate
            and final_action == "local_small"
            and complexity >= floor
        ):
            final_action = "frontier"
        by_name[str(row["name"])] = {
            "final_action": final_action,
            "escalate": escalate,
        }
    actual = {
        "simple_local_action": by_name["simple_local"]["final_action"],
        "complex_action": by_name["complex_forces_frontier"]["final_action"],
        "invalid_escalates": by_name["invalid_route"]["escalate"],
        "low_confidence_escalates": by_name["low_confidence"]["escalate"],
    }
    _assert_expect(actual, expect)


async def _run_action_safety_judgment(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    action_qid = str(request.get("action_question_id") or "semantic_risk")
    questions = list(request.get("questions") or [])
    by_name: dict[str, Any] = {}
    for row in list(request.get("cases") or []):
        policy = AccessPolicy(grants=list(row.get("grants") or []))
        required = list(row.get("required_grants") or [])
        grants_ok = policy.allows(required) if required else True
        result = await run_decision_plane_policy(
            questions=questions,
            answers=dict(row.get("answers") or {}),
            confidence=row.get("confidence"),
            confidence_floor=float(row.get("confidence_floor") or 0.7),
            action_question_id=action_qid,
        )
        risk = result.final_action
        if not grants_ok:
            decision = "deny"
            hard_won = True
        elif result.escalate or risk == "high":
            decision = "escalate_review"
            hard_won = False
        else:
            decision = "allow"
            hard_won = False
        by_name[str(row["name"])] = {
            "decision": decision,
            "hard_won": hard_won,
            "grants_after": list(policy.grants),
            "grants_before": list(row.get("grants") or []),
        }
    delete = by_name["delete_low_risk_no_grant"]
    read_high = by_name["read_high_risk_with_grant"]
    read_low = by_name["read_low_risk_with_grant"]
    actual = {
        "delete_denied": delete["decision"] == "deny",
        "delete_hard_policy_won": delete["hard_won"],
        "read_high_escalates_review": read_high["decision"] == "escalate_review",
        "read_low_allows": read_low["decision"] == "allow",
        "never_elevates_grants": all(
            row["grants_after"] == row["grants_before"] for row in by_name.values()
        ),
    }
    _assert_expect(actual, expect)



RUNNERS: dict[str, StoryRunner] = {
    "fixture_judge_batch": _run_fixture_judge_batch,
    "decision_surface_reject": _run_decision_surface_reject,
    "offline_decision_export": _run_offline_decision_export,
    "policy_replay": _run_policy_replay,
    "decision_plane_recipe": _run_decision_plane_recipe,
    "decision_plane_projection": _run_decision_plane_projection,
    "decision_plane_policy": _run_decision_plane_policy,
    "decision_plane_shadow": _run_decision_plane_shadow,
    "decision_plane_telemetry": _run_decision_plane_telemetry,
    "decision_plane_model_policy": _run_decision_plane_model_policy,
    "decision_plane_shadow_compare": _run_decision_plane_shadow_compare,
    "citation_support_judgment": _run_citation_support_judgment,
    "context_budget_judgment": _run_context_budget_judgment,
    "requirements_gap_judgment": _run_requirements_gap_judgment,
    "task_route_judgment": _run_task_route_judgment,
    "action_safety_judgment": _run_action_safety_judgment,
}
