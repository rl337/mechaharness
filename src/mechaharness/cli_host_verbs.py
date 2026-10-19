"""Product-facing CLI verbs registered on ``MechaHarnessConfig.cli_verb_classes``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.cli_commands import (
    AdvanceClockCommand,
    InferCommand,
    RunRecipeCommand,
    SetClockCommand,
    ToolLoopCommand,
)
from mechaharness.cli_diagnostic_verbs import (
    CheckModelAffinityCommand,
    CompareRunParityCommand,
    ReplayModelInputCommand,
    RouteCapabilitiesCommand,
    ShadowDecisionBackendsCommand,
    run_check_model_affinity,
    run_compare_run_parity,
    run_replay_model_input,
    run_route_capabilities,
    run_shadow_decision_backends,
)
from mechaharness.cli_verb import CliVerb, make_probe_verb, make_runtime_verb
from mechaharness.inference.judge import (
    ChoiceOption,
    ChoiceQuestion,
    ChoiceSignal,
    JudgeRequest,
    NoulQuestion,
    hash_state,
    judge,
)
from mechaharness.judgement_policy import (
    JudgementFacts,
    JudgementPolicy,
    JudgementThreshold,
    decide,
)


class JudgeRouteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    questions: list[dict[str, Any]] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=dict)
    question_set_version: str = "story"


def _build_questions(raw: list[dict[str, Any]]) -> list[Any]:
    out: list[Any] = []
    for item in raw:
        kind = item["kind"]
        if kind == "choice":
            out.append(
                ChoiceQuestion(
                    id=item["id"],
                    instructions=item.get("instructions", ""),
                    options=[
                        ChoiceOption(
                            id=o["id"], description=o.get("description", "")
                        )
                        for o in item["options"]
                    ],
                )
            )
        elif kind == "noul":
            out.append(
                NoulQuestion(id=item["id"], instructions=item.get("instructions", ""))
            )
        else:
            raise ValueError(f"unsupported question kind {kind!r}")
    return out


def _policy_from_mapping(raw: dict[str, Any]) -> JudgementPolicy:
    thresholds = [JudgementThreshold(**t) for t in raw.get("thresholds", [])]
    return JudgementPolicy(
        version=str(raw.get("version") or "story"),
        thresholds=thresholds,
        ignore_unknown_signals=bool(raw.get("ignore_unknown_signals", False)),
    )


async def _run_judge_route(body: JudgeRouteCommand, runtime: Any) -> dict[str, Any]:
    provider = runtime.judge_provider
    if provider is None:
        raise RuntimeError("judge_route requires CliInstrumentor(judge_provider=...)")
    judgement = await judge(
        JudgeRequest(
            state=body.state,
            state_hash=hash_state(body.state),
            questions=_build_questions(body.questions),
            question_set_version=body.question_set_version,
        ),
        provider=provider,
    )
    by_id = {a.id: a for a in judgement.answers}
    route = by_id.get("route")
    selected = route.selected if isinstance(route, ChoiceSignal) else None
    verdict = decide(
        JudgementFacts(action="route"),
        judgement,
        _policy_from_mapping(body.policy),
    )
    return {
        "route_selected": selected,
        "verdict": verdict.kind,
        "answer_count": len(judgement.answers),
    }


def default_cli_verb_classes() -> dict[str, type[CliVerb]]:
    """Host CLI catalog (infer / tools / recipes / diagnostics / clocks / judge)."""
    return {
        "infer": make_runtime_verb("infer", InferCommand, lambda p, r: r.run_infer(p)),
        "tool_loop": make_runtime_verb(
            "tool_loop", ToolLoopCommand, lambda p, r: r.run_tool_loop(p)
        ),
        "run_recipe": make_runtime_verb(
            "run_recipe", RunRecipeCommand, lambda p, r: r.run_recipe(p)
        ),
        "set_clock": make_runtime_verb(
            "set_clock", SetClockCommand, lambda p, r: r.run_set_clock(p)
        ),
        "advance_clock": make_runtime_verb(
            "advance_clock",
            AdvanceClockCommand,
            lambda p, r: r.run_advance_clock(p),
        ),
        "replay_model_input": make_probe_verb(
            "replay_model_input",
            ReplayModelInputCommand,
            run_replay_model_input,
        ),
        "route_capabilities": make_probe_verb(
            "route_capabilities",
            RouteCapabilitiesCommand,
            run_route_capabilities,
        ),
        "check_model_affinity": make_probe_verb(
            "check_model_affinity",
            CheckModelAffinityCommand,
            run_check_model_affinity,
        ),
        "compare_run_parity": make_probe_verb(
            "compare_run_parity",
            CompareRunParityCommand,
            run_compare_run_parity,
        ),
        "shadow_decision_backends": make_probe_verb(
            "shadow_decision_backends",
            ShadowDecisionBackendsCommand,
            run_shadow_decision_backends,
        ),
        "judge_route": make_runtime_verb(
            "judge_route", JudgeRouteCommand, _run_judge_route
        ),
    }


__all__ = ["JudgeRouteCommand", "default_cli_verb_classes"]
