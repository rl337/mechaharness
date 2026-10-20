"""Product-facing CLI verbs registered on ``MechaHarnessConfig.cli_verb_classes``.

Clocks and story probes are test-Config only (see ``TestHarnessCliConfig``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.cli_commands import InferCommand, RunRecipeCommand, ToolLoopCommand
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
from mechaharness.cli_verb import CliVerb
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


class InferVerb(CliVerb):
    name = "infer"
    params_model = InferCommand

    async def run(self, params: BaseModel, runtime: Any) -> Any:
        return await runtime.run_infer(params)


class ToolLoopVerb(CliVerb):
    name = "tool_loop"
    params_model = ToolLoopCommand

    async def run(self, params: BaseModel, runtime: Any) -> Any:
        return await runtime.run_tool_loop(params)


class RunRecipeVerb(CliVerb):
    name = "run_recipe"
    params_model = RunRecipeCommand

    async def run(self, params: BaseModel, runtime: Any) -> Any:
        return await runtime.run_recipe(params)


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


class JudgeRouteVerb(CliVerb):
    name = "judge_route"
    params_model = JudgeRouteCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = params
        assert isinstance(body, JudgeRouteCommand)
        provider = runtime.judge_provider
        if provider is None:
            raise RuntimeError(
                "judge_route requires CliInstrumentor(judge_provider=...)"
            )
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


class ReplayModelInputVerb(CliVerb):
    name = "replay_model_input"
    params_model = ReplayModelInputCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        return run_replay_model_input(params)  # type: ignore[arg-type]


class RouteCapabilitiesVerb(CliVerb):
    name = "route_capabilities"
    params_model = RouteCapabilitiesCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        return run_route_capabilities(params)  # type: ignore[arg-type]


class CheckModelAffinityVerb(CliVerb):
    name = "check_model_affinity"
    params_model = CheckModelAffinityCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        return run_check_model_affinity(params)  # type: ignore[arg-type]


class CompareRunParityVerb(CliVerb):
    name = "compare_run_parity"
    params_model = CompareRunParityCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        return run_compare_run_parity(params)  # type: ignore[arg-type]


class ShadowDecisionBackendsVerb(CliVerb):
    name = "shadow_decision_backends"
    params_model = ShadowDecisionBackendsCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        del runtime
        return run_shadow_decision_backends(params)  # type: ignore[arg-type]


def default_cli_verb_classes() -> dict[str, type[CliVerb]]:
    """Host CLI catalog (infer / tools / recipes / diagnostics / judge / durable)."""
    from mechaharness.cli_durable_verbs import durable_cli_verb_classes

    verbs: dict[str, type[CliVerb]] = {
        InferVerb.name: InferVerb,
        ToolLoopVerb.name: ToolLoopVerb,
        RunRecipeVerb.name: RunRecipeVerb,
        JudgeRouteVerb.name: JudgeRouteVerb,
        ReplayModelInputVerb.name: ReplayModelInputVerb,
        RouteCapabilitiesVerb.name: RouteCapabilitiesVerb,
        CheckModelAffinityVerb.name: CheckModelAffinityVerb,
        CompareRunParityVerb.name: CompareRunParityVerb,
        ShadowDecisionBackendsVerb.name: ShadowDecisionBackendsVerb,
    }
    verbs.update(durable_cli_verb_classes())
    return verbs


__all__ = [
    "CheckModelAffinityVerb",
    "CompareRunParityVerb",
    "InferVerb",
    "JudgeRouteCommand",
    "JudgeRouteVerb",
    "ReplayModelInputVerb",
    "RouteCapabilitiesVerb",
    "RunRecipeVerb",
    "ShadowDecisionBackendsVerb",
    "ToolLoopVerb",
    "default_cli_verb_classes",
]
