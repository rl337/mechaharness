"""Product-facing CLI verbs registered on ``MechaHarnessConfig.cli_verb_classes``.

Clocks and story probes are test-Config only (see ``TestHarnessCliConfig``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
from mechaharness.core.access import AccessPolicy
from mechaharness.decision_plane_runtime import assemble_context_within_budget
from mechaharness.inference.judge import (
    ChoiceOption,
    ChoiceQuestion,
    ChoiceSignal,
    JudgeRequest,
    NoulQuestion,
    NoulSignal,
    ScoreSignal,
    hash_state,
    judge,
)
from mechaharness.judgement_policy import (
    JudgementFacts,
    JudgementPolicy,
    JudgementThreshold,
    decide,
)
from mechaharness.recipe_bind import InstantiateRecipeCommand, TileRecipeCommand
from mechaharness.recipe_plan import RecipePlanCommand


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


class InstantiateRecipeVerb(CliVerb):
    """Expand a RecipeBind (inline or path) into a concrete graph."""

    name = "instantiate_recipe"
    params_model = InstantiateRecipeCommand

    async def run(self, params: BaseModel, runtime: Any) -> Any:
        return await runtime.instantiate_recipe(params)


class TileRecipeVerb(CliVerb):
    """Tile a catalog recipe under multiple instance keys."""

    name = "tile_recipe"
    params_model = TileRecipeCommand

    async def run(self, params: BaseModel, runtime: Any) -> Any:
        return await runtime.tile_recipe(params)


class RecipePlanVerb(CliVerb):
    """Run a lifecycle plan document (soft evolution / ports / compose)."""

    name = "recipe_plan"
    params_model = RecipePlanCommand

    async def run(self, params: BaseModel, runtime: Any) -> Any:
        return await runtime.recipe_plan(params)


class JudgeCommand(BaseModel):
    """Judge-lane one-shot (infer twin): typed questions over state via JudgeProvider."""

    model_config = ConfigDict(extra="forbid")

    state: str | None = None
    state_path: str | None = None
    questions: list[dict[str, Any]] = Field(default_factory=list)
    question_set_version: str = "story"
    # Optional host-policy derivation over one choice answer (citation / route).
    action_question_id: str | None = None
    confidence_floor: float | None = None
    verified_selected: str | None = None
    # Optional facts for code-owned gates (requirements crash_tests, complexity).
    facts: dict[str, Any] = Field(default_factory=dict)
    quality_complexity_floor: float | None = None
    quality_override_action: str | None = None
    # Action-safety: hard AccessPolicy over required abilities + semantic risk.
    required_abilities: list[str] = Field(default_factory=list)
    grants: list[str] = Field(default_factory=list)
    risk_question_id: str | None = None

    @model_validator(mode="after")
    def _state_source(self) -> JudgeCommand:
        if not (self.state or self.state_path):
            raise ValueError("judge requires state or state_path")
        return self


class JudgeRouteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    questions: list[dict[str, Any]] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=dict)
    question_set_version: str = "story"


class AssembleContextCommand(BaseModel):
    """Deterministic RAG pack under token/trust floors (code-owned; no model)."""

    model_config = ConfigDict(extra="forbid")

    token_budget: int
    min_relevance: float = 0.0
    min_trust: float = 0.0
    min_freshness: float = 0.0
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    path: str | None = None


def _build_questions(raw: list[dict[str, Any]]) -> list[Any]:
    out: list[Any] = []
    for item in raw:
        kind = item["kind"]
        if kind == "choice":
            options_raw = item.get("options") or []
            options: list[ChoiceOption] = []
            for o in options_raw:
                if isinstance(o, str):
                    options.append(ChoiceOption(id=o, description=o))
                else:
                    oid = str(o["id"])
                    options.append(
                        ChoiceOption(
                            id=oid,
                            description=str(o.get("description") or o.get("label") or oid),
                        )
                    )
            out.append(
                ChoiceQuestion(
                    id=item["id"],
                    instructions=item.get("instructions", ""),
                    options=options,
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


def _resolve_state(body: JudgeCommand, runtime: Any) -> str:
    if body.state_path:
        base = getattr(runtime, "bind_base_dir", None)
        path = Path(body.state_path)
        if not path.is_absolute():
            if base is None:
                raise RuntimeError("judge state_path requires bind_base_dir")
            path = Path(base) / path
        return path.read_text(encoding="utf-8")
    assert body.state is not None
    return body.state


def _choice_confidence(signal: ChoiceSignal) -> float | None:
    if signal.selected in signal.probabilities:
        return float(signal.probabilities[signal.selected])
    if signal.probabilities:
        return float(max(signal.probabilities.values()))
    return None


def _signal_payload(signal: Any) -> dict[str, Any]:
    if isinstance(signal, ChoiceSignal):
        return {
            "kind": "choice",
            "selected": signal.selected,
            "probabilities": dict(signal.probabilities),
            "confidence": _choice_confidence(signal),
        }
    if isinstance(signal, NoulSignal):
        return {"kind": "noul", "p_true": signal.p_true}
    if isinstance(signal, ScoreSignal):
        return {"kind": "score", "value": signal.value}
    return {"kind": "unknown"}


async def _run_judge(body: JudgeCommand, runtime: Any) -> dict[str, Any]:
    provider = runtime.judge_provider
    if provider is None:
        raise RuntimeError("judge requires CliInstrumentor(judge_provider=...)")
    state = _resolve_state(body, runtime)
    judgement = await judge(
        JudgeRequest(
            state=state,
            state_hash=hash_state(state),
            questions=_build_questions(body.questions),
            question_set_version=body.question_set_version,
        ),
        provider=provider,
    )
    by_id = {a.id: a for a in judgement.answers}
    answers = {qid: _signal_payload(sig) for qid, sig in by_id.items()}
    out: dict[str, Any] = {
        "answer_count": len(judgement.answers),
        "answers": answers,
        "error_count": len(judgement.errors),
    }
    action_id = body.action_question_id
    if action_id:
        signal = by_id.get(action_id)
        selected = signal.selected if isinstance(signal, ChoiceSignal) else None
        confidence = (
            _choice_confidence(signal) if isinstance(signal, ChoiceSignal) else None
        )
        escalate = bool(
            body.confidence_floor is not None
            and confidence is not None
            and confidence < body.confidence_floor
        )
        final_action = selected
        if (
            not escalate
            and body.quality_complexity_floor is not None
            and body.quality_override_action
            and float(body.facts.get("complexity", 0)) >= body.quality_complexity_floor
            and selected != body.quality_override_action
        ):
            final_action = body.quality_override_action
        # Disallowed invented lanes: selected not in question options → escalate
        if isinstance(signal, ChoiceSignal) and action_id:
            q = next(
                (item for item in body.questions if item.get("id") == action_id),
                None,
            )
            if q is not None:
                allowed = {
                    (o if isinstance(o, str) else o["id"]) for o in (q.get("options") or [])
                }
                # options may be {id, label} from plans
                allowed = set()
                for o in q.get("options") or []:
                    if isinstance(o, str):
                        allowed.add(o)
                    else:
                        allowed.add(str(o["id"]))
                allowed_actions = q.get("allowed_actions")
                if allowed_actions:
                    allowed = set(str(a) for a in allowed_actions)
                if selected is not None and selected not in allowed:
                    escalate = True
                    final_action = None
        claim_verified = False
        if body.verified_selected is not None:
            claim_verified = (
                not escalate and selected == body.verified_selected
            )
        out.update(
            {
                "final_action": final_action,
                "confidence": confidence,
                "escalate": escalate,
                "claim_verified": claim_verified,
                f"{action_id}_selected": selected,
            }
        )
        # Requirements-gap outcome from coverage choice + crash_tests fact
        if action_id == "coverage" or "crash_tests_present" in body.facts:
            facts = dict(body.facts)
            if escalate or final_action in {"gap", "unclear", None}:
                outcome = "request_tests"
            elif not facts.get("crash_tests_present", True):
                outcome = "request_tests"
            elif final_action == "covered":
                outcome = "continue_review"
            else:
                outcome = "request_tests"
            out["outcome"] = outcome
        # Action safety: hard grants win over semantic risk
        if body.risk_question_id or body.required_abilities:
            from mechaharness.core.access import FsRead, FsWrite

            grant_objs: list[object] = []
            for g in body.grants:
                if g in ("core:fs.write", "FsWrite", "fs.write"):
                    grant_objs.append(FsWrite)
                elif g in ("core:fs.read", "FsRead", "fs.read"):
                    grant_objs.append(FsRead)
                else:
                    grant_objs.append(g)
            policy = AccessPolicy(grants=grant_objs)
            required: list[object] = []
            for a in body.required_abilities:
                if a in ("core:fs.write", "fs.write", "FsWrite"):
                    required.append(FsWrite)
                elif a in ("core:fs.read", "fs.read", "FsRead"):
                    required.append(FsRead)
                else:
                    required.append(a)
            hard_allows = policy.allows(required) if required else True
            risk_id = body.risk_question_id or "risk"
            risk_sig = by_id.get(risk_id)
            risk = risk_sig.selected if isinstance(risk_sig, ChoiceSignal) else "low"
            grants_before = list(body.grants)
            if not hard_allows:
                decision = "deny"
                hard_won = True
            elif risk == "high":
                decision = "escalate_review"
                hard_won = False
            else:
                decision = "allow"
                hard_won = False
            out.update(
                {
                    "decision": decision,
                    "hard_won": hard_won,
                    "grants_unchanged": list(body.grants) == grants_before,
                }
            )
    return out


class JudgeVerb(CliVerb):
    """Judge-lane one-shot — product twin of ``infer``."""

    name = "judge"
    params_model = JudgeCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        assert isinstance(params, JudgeCommand)
        return await _run_judge(params, runtime)


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


class AssembleContextVerb(CliVerb):
    """Pack scored RAG candidates into a token budget (no model call)."""

    name = "assemble_context"
    params_model = AssembleContextCommand

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        body = params
        assert isinstance(body, AssembleContextCommand)
        candidates = list(body.candidates)
        if body.path:
            base = getattr(runtime, "bind_base_dir", None)
            path = Path(body.path)
            if not path.is_absolute():
                if base is None:
                    raise RuntimeError("assemble_context path requires bind_base_dir")
                path = Path(base) / path
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict) and "candidates" in loaded:
                candidates = list(loaded["candidates"])
                token_budget = int(loaded.get("token_budget", body.token_budget))
                min_relevance = float(loaded.get("min_relevance", body.min_relevance))
                min_trust = float(loaded.get("min_trust", body.min_trust))
                min_freshness = float(loaded.get("min_freshness", body.min_freshness))
            elif isinstance(loaded, list):
                token_budget = body.token_budget
                min_relevance = body.min_relevance
                min_trust = body.min_trust
                min_freshness = body.min_freshness
                candidates = loaded
            else:
                raise ValueError(f"assemble_context path {path} has no candidates")
        else:
            token_budget = body.token_budget
            min_relevance = body.min_relevance
            min_trust = body.min_trust
            min_freshness = body.min_freshness
        selected = assemble_context_within_budget(
            candidates,
            token_budget=token_budget,
            min_relevance=min_relevance,
            min_trust=min_trust,
            min_freshness=min_freshness,
        )
        by_id = {str(c["id"]): c for c in candidates if "id" in c}
        total = sum(int(by_id[cid]["tokens"]) for cid in selected if cid in by_id)
        return {
            "selected_ids": selected,
            "token_total": total,
            "within_budget": total <= token_budget,
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
    from mechaharness.cli_tool_lifecycle import ToolLifecycleVerb
    from mechaharness.cli_transactional_resume import TransactionalResumeVerb

    verbs: dict[str, type[CliVerb]] = {
        InferVerb.name: InferVerb,
        ToolLoopVerb.name: ToolLoopVerb,
        RunRecipeVerb.name: RunRecipeVerb,
        InstantiateRecipeVerb.name: InstantiateRecipeVerb,
        TileRecipeVerb.name: TileRecipeVerb,
        RecipePlanVerb.name: RecipePlanVerb,
        ToolLifecycleVerb.name: ToolLifecycleVerb,
        JudgeVerb.name: JudgeVerb,
        JudgeRouteVerb.name: JudgeRouteVerb,
        AssembleContextVerb.name: AssembleContextVerb,
        ReplayModelInputVerb.name: ReplayModelInputVerb,
        RouteCapabilitiesVerb.name: RouteCapabilitiesVerb,
        CheckModelAffinityVerb.name: CheckModelAffinityVerb,
        CompareRunParityVerb.name: CompareRunParityVerb,
        ShadowDecisionBackendsVerb.name: ShadowDecisionBackendsVerb,
        TransactionalResumeVerb.name: TransactionalResumeVerb,
    }
    verbs.update(durable_cli_verb_classes())
    return verbs


__all__ = [
    "AssembleContextCommand",
    "AssembleContextVerb",
    "CheckModelAffinityVerb",
    "CompareRunParityVerb",
    "InferVerb",
    "InstantiateRecipeVerb",
    "JudgeCommand",
    "JudgeRouteCommand",
    "JudgeRouteVerb",
    "JudgeVerb",
    "RecipePlanVerb",
    "ReplayModelInputVerb",
    "RouteCapabilitiesVerb",
    "RunRecipeVerb",
    "ShadowDecisionBackendsVerb",
    "TileRecipeVerb",
    "ToolLoopVerb",
    "default_cli_verb_classes",
]
