"""Execute user-story kinds against static or live backends."""

from __future__ import annotations

import os
from typing import Annotated, Any

import httpx
import pytest
from pyiv.key import Matched, Named

from mechaharness.advisor import (
    AdvisorContextContract,
    AdvisorRequest,
    DefaultAdvisorPolicy,
    RejectAdvisor,
    consult_advisor,
)
from mechaharness.api_connection import SimpleHttpConnectionConfig
from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.config import Settings
from mechaharness.consequence import ActionConsequence, ConsequencePolicy
from mechaharness.context_experiments import (
    ContextCompiler,
    CtxFlags,
    DerivedMemoryRecord,
    DerivedMemoryStore,
    ObservationRef,
    ObservationStore,
    RepositoryTopologyProvider,
    compact_at_boundary,
    compile_cache_aware_layout,
    fuse_actions,
    reduce_evidence,
)
from mechaharness.context_provider import StaticContextProvider
from mechaharness.convergence import ConvergenceContract, ConvergenceGuard
from mechaharness.core.access import (
    Ability,
    AccessControl,
    AccessPolicy,
    CompoundPolicy,
    FsWrite,
    GraphEscalate,
    GraphExecute,
    InMemoryAccessControl,
)
from mechaharness.core.completer import Completer
from mechaharness.core.environment import (
    InferenceEnvironment,
    InferenceEnvironmentError,
    NoOpInferenceEnvironment,
)
from mechaharness.core.events import InMemoryEventLog
from mechaharness.core.types import ChatMessage, Role, ToolCall
from mechaharness.decision_log import (
    DecisionRecord,
    TopologySpan,
    compute_topology_metrics,
    export_offline_dataset,
    replay_verdict,
)
from mechaharness.decision_surfaces import (
    DecisionSurface,
    RulesDecisionBackend,
    reject_invalid_choice,
)
from mechaharness.delegation_policy import DefaultDelegationPolicy, DelegationRequest
from mechaharness.di import MechaHarnessConfig, _expose_ctor_type_hints, get_injector
from mechaharness.failure_attribution import attribute_error, detect_repeated_failure_classes
from mechaharness.graph import (
    DependencyEdge,
    ExecutionGraph,
    FanInItem,
    GraphNode,
    GraphStore,
    NodeStatus,
    VerificationOracle,
    bounded_repair,
    hierarchical_fan_in,
    merge_branch_artifacts,
    qualify_validator,
    validator_qualified,
)
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphEscalation,
    GraphExecutor,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
)
from mechaharness.graph_templates import (
    FanOutAggregateTemplate,
    GraphTemplateParams,
    IndependentReviewTemplate,
    SubgraphNodeRunner,
    default_graph_templates,
)
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.harness_experiment import HarnessExperiment, HarnessExperimentRunner
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.judge import (
    ChoiceOption,
    ChoiceQuestion,
    ChoiceSignal,
    FixtureJudgeProvider,
    JudgeRequest,
    NoulQuestion,
    NoulSignal,
    ScoreAnchor,
    ScoreQuestion,
    hash_state,
    judge,
)
from mechaharness.inference.openai_compat import OpenAICompatStrategy
from mechaharness.inference.systemone import SystemOneJudgeProvider
from mechaharness.instruction_component import InstructionCatalog
from mechaharness.judgement_policy import (
    JudgementFacts,
    JudgementPolicy,
    JudgementThreshold,
    decide,
)
from mechaharness.lifecycle_extension import (
    BeforeGraphNode,
    BeforeTool,
    Block,
    ExtensionEffect,
    LifecycleExtension,
    LifecycleExtensionContext,
    LifecycleExtensionRegistry,
    ObserveBefore,
    Replace,
    Rewrite,
)
from mechaharness.linkage_resolver import DefaultLinkageResolver
from mechaharness.operation_registry import (
    NodeContractBind,
    OperationContract,
    ResourceScope,
    default_operations,
)
from mechaharness.outcome_contract import OutcomeContract
from mechaharness.research import EvalProtocol, ResearchLab
from mechaharness.routing import (
    activate_scoped_policy,
    route_at_boundary,
    route_for_capability_needs,
    shadow_decision_backends,
)
from mechaharness.tools.base import ToolRegistry
from mechaharness.verification_policy import DefaultVerificationPolicy
from tests.fakes import ScriptedInference
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.support.di import make_harness


class _LaneEnvironment(InferenceEnvironment):
    """Story double: real lane checks (unlike NoOpInferenceEnvironment)."""

    def __init__(self, lane: str) -> None:
        self._lane = lane

    def active_profile(self) -> str | None:
        return f"story-{self._lane}"

    def active_capabilities(self):
        from mechaharness.core.access import CapabilityProfile

        return CapabilityProfile()

    def active_lane(self) -> str | None:
        return self._lane


def _assert_expect(actual: dict[str, Any], expect: dict[str, Any]) -> None:
    for key, wanted in expect.items():
        if key not in actual:
            raise AssertionError(f"missing actual key {key!r}; got {sorted(actual)}")
        got = actual[key]
        if key.endswith("_include") and isinstance(wanted, list):
            missing = [item for item in wanted if item not in got]
            assert not missing, f"{key}: missing {missing} in {got}"
        elif key.endswith("_in") and isinstance(wanted, list):
            assert got in wanted, f"{key}: {got!r} not in {wanted!r}"
        elif key.endswith("_contains") and isinstance(wanted, str):
            assert wanted in str(got), f"{key}: {wanted!r} not in {got!r}"
        elif key.startswith("min_") and isinstance(wanted, (int, float)):
            assert got >= wanted, f"{key}: {got} < {wanted}"
        elif key.endswith("_min") and isinstance(wanted, (int, float)):
            assert got >= wanted, f"{key}: {got} < {wanted}"
        elif key.endswith("_nonempty"):
            assert bool(got) is bool(wanted), f"{key}: {got!r} vs {wanted!r}"
            if wanted:
                assert str(got).strip(), f"{key}: empty value"
        else:
            assert got == wanted, f"{key}: {got!r} != {wanted!r}"


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
                        ChoiceOption(id=o["id"], description=o.get("description", ""))
                        for o in item["options"]
                    ],
                )
            )
        elif kind == "noul":
            out.append(
                NoulQuestion(id=item["id"], instructions=item.get("instructions", ""))
            )
        elif kind == "score":
            out.append(
                ScoreQuestion(
                    id=item["id"],
                    instructions=item.get("instructions", ""),
                    min=float(item.get("min", 0.0)),
                    max=float(item.get("max", 1.0)),
                    anchors=[
                        ScoreAnchor(value=float(a["value"]), description=a.get("description", ""))
                        for a in item.get("anchors", [])
                    ],
                )
            )
        else:
            raise ValueError(f"unsupported question kind {kind!r}")
    return out


def _policy_from_request(raw: dict[str, Any] | None) -> JudgementPolicy:
    raw = raw or {}
    thresholds = [JudgementThreshold(**t) for t in raw.get("thresholds", [])]
    return JudgementPolicy(
        version=raw.get("version", "story"),
        thresholds=thresholds,
        ignore_unknown_signals=bool(raw.get("ignore_unknown_signals", False)),
    )


async def run_story(case: StoryCase, backend: StoryBackend) -> None:
    meta = case.load_json("story.json")
    kind = meta["kind"]
    if backend.mode == "live" and case.adapter == "in_process":
        raise AssertionError(
            f"{case.label}: in_process stories must not be collected in live mode"
        )
    runners = {
        "pass_through": _run_pass_through,
        "route_refund": _run_route_refund,
        "systemone_cassette": _run_route_refund,
        "wrong_lane_deny": _run_wrong_lane_deny,
        "grant_gate_write": _run_grant_gate_write,
        "config_access_policy": _run_config_access_policy,
        "completer_flavors": _run_completer_flavors,
        "fixture_judge_batch": _run_fixture_judge_batch,
        "decision_surface_reject": _run_decision_surface_reject,
        "convergence_ceiling": _run_convergence_ceiling,
        "context_compiler_deficit": _run_context_compiler_deficit,
        "local_plan_resume": _run_local_plan_resume,
        "graph_executor_run": _run_graph_executor_run,
        "topology_efficiency": _run_topology_efficiency,
        "shadow_decision_backends": _run_shadow_decision_backends,
        "validator_qualification": _run_validator_qualification,
        "atk_research_reject": _run_atk_research_reject,
        "offline_decision_export": _run_offline_decision_export,
        "human_review_pending": _run_human_review_pending,
        "tool_gating": _run_tool_gating,
        "bounded_repair_loop": _run_bounded_repair_loop,
        "context_observation_chain": _run_context_observation_chain,
        "derived_memory": _run_derived_memory,
        "repo_topology": _run_repo_topology,
        "model_affinity": _run_model_affinity,
        "cache_layout_experiment": _run_cache_layout_experiment,
        "policy_replay": _run_policy_replay,
        "graph_linkage_preflight": _run_graph_linkage_preflight,
        "graph_template_soft_points": _run_graph_template_soft_points,
        "capability_envelope_narrow": _run_capability_envelope_narrow,
        "sparse_advisor_consult": _run_sparse_advisor_consult,
        "verification_outcome_gate": _run_verification_outcome_gate,
        "consequence_risk_scale": _run_consequence_risk_scale,
        "harness_experiment_retire": _run_harness_experiment_retire,
        "dynamic_subgraph_nest": _run_dynamic_subgraph_nest,
        "context_provider_discovery": _run_context_provider_discovery,
        "instruction_gotcha_metrics": _run_instruction_gotcha_metrics,
        "independent_review_template": _run_independent_review_template,
        "failure_attribution_trace": _run_failure_attribution_trace,
        "checkpoint_fingerprint_refuse": _run_checkpoint_fingerprint_refuse,
        "capability_need_routing": _run_capability_need_routing,
        "environment_linkage_fail": _run_environment_linkage_fail,
        "wake_reresolve_resume": _run_wake_reresolve_resume,
        "graph_budget_limits": _run_graph_budget_limits,
        "graph_budget_subgraph_rollup": _run_graph_budget_subgraph_rollup,
        "lifecycle_extension_observe": _run_lifecycle_extension_observe,
        "lifecycle_extension_rewrite": _run_lifecycle_extension_rewrite,
        "lifecycle_extension_block": _run_lifecycle_extension_block,
        "lifecycle_extension_replace": _run_lifecycle_extension_replace,
        "lifecycle_extension_graph_observe": _run_lifecycle_extension_graph_observe,
    }
    try:
        runner = runners[kind]
    except KeyError as exc:
        raise ValueError(f"unknown story kind {kind!r} in {case.label}") from exc
    await runner(case, backend)


async def _run_pass_through(case: StoryCase, backend: StoryBackend) -> None:
    request = case.load_json("request.json")
    response = case.load_json("response.json")
    expect = case.load_json("expect.json")
    prompt = request["prompt"]
    model = request.get("model") or case.model
    log = InMemoryEventLog()

    if case.adapter == "in_process":
        content = response.get("content", "ok")
        inference = ScriptedInference(
            [ChatMessage(role=Role.ASSISTANT, content=content)]
        )
        harness = make_harness(
            inference,
            config=HarnessConfig(model=model, max_turns=1),
            harness_cls=PassThroughHarness,
            event_log=log,
        )
        result = await harness.run(prompt)
    elif case.adapter == "openai_compat":
        settings = Settings(
            inference_backend="openai_compat",
            harness_family="pass_through",
            model=model,
            base_url=os.environ.get("MECHA_BASE_URL", "http://story.invalid/v1"),
            api_key=os.environ.get("MECHA_API_KEY", "story"),
            max_tokens=int(os.environ.get("MECHA_MAX_TOKENS", "256")),
        )
        client: httpx.AsyncClient | None
        if backend.mode == "static":
            payload = response

            def handler(http_request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json=payload)

            client = httpx.AsyncClient(
                base_url=settings.base_url or "http://story.invalid/v1",
                transport=httpx.MockTransport(handler),
                headers={"Authorization": f"Bearer {settings.api_key}"},
            )
        else:
            if not os.environ.get("MECHA_BASE_URL"):
                pytest.fail("MECHA_BASE_URL is required for live openai_compat stories")
            client = None
        strategy = OpenAICompatStrategy(settings, timeout=180.0, client=client)
        harness = make_harness(
            strategy,
            config=HarnessConfig(
                model=settings.model,
                max_turns=1,
                max_tokens=settings.max_tokens,
            ),
            harness_cls=PassThroughHarness,
            event_log=log,
        )
        try:
            result = await harness.run(prompt)
        finally:
            await strategy.aclose()
    else:
        raise ValueError(f"pass_through unsupported adapter {case.adapter!r}")

    actual = {
        "final_text_nonempty": bool((result.final_text or "").strip()),
        "turns": result.turns,
        "min_cost_units": result.cost.units,
        "event_types_include": [event.type for event in result.events],
    }
    _assert_expect(actual, expect)


async def _run_route_refund(case: StoryCase, backend: StoryBackend) -> None:
    request = case.load_json("request.json")
    response = case.load_json("response.json")
    expect = case.load_json("expect.json")
    state = request["state"]
    questions = _build_questions(request["questions"])
    policy = _policy_from_request(request.get("policy"))
    client: httpx.AsyncClient | None = None

    if case.adapter == "in_process":
        provider = FixtureJudgeProvider(response.get("answers", {}))
    elif case.adapter == "systemone":
        if backend.mode == "static":
            payload = response

            def handler(http_request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json=payload)

            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            connection = SimpleHttpConnectionConfig(
                base_url="http://story.invalid",
                path="/v1/systemone",
                model="laya",
            )
            provider = SystemOneJudgeProvider(connection=connection, client=client)
        else:
            provider = SystemOneJudgeProvider()
    else:
        raise ValueError(f"route_refund unsupported adapter {case.adapter!r}")

    try:
        judgement = await judge(
            JudgeRequest(
                state=state,
                state_hash=hash_state(state),
                questions=questions,
                question_set_version=request.get("question_set_version", "story"),
            ),
            provider=provider,
        )
    finally:
        if client is not None:
            await client.aclose()

    by_id = {a.id: a for a in judgement.answers}
    route = by_id.get("route")
    selected = route.selected if isinstance(route, ChoiceSignal) else None
    verdict = decide(JudgementFacts(action="route"), judgement, policy)
    actual = {
        "route_selected_in": selected,
        "verdict_in": verdict.kind,
        "min_answer_count": len(judgement.answers),
    }
    _assert_expect(actual, expect)


async def _run_wrong_lane_deny(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    env: InferenceEnvironment = _LaneEnvironment(request["active_lane"])
    raised: Exception | None = None
    try:
        env.assert_compatible(require_lane=request["require_lane"])
    except Exception as exc:  # noqa: BLE001 — type checked via expect
        raised = exc
    assert raised is not None, "expected InferenceEnvironmentError"
    assert isinstance(raised, InferenceEnvironmentError)
    actual = {
        "error_type": type(raised).__name__,
        "error_match": str(raised),
    }
    assert actual["error_type"] == expect["error_type"]
    assert expect["error_match"].lower() in actual["error_match"].lower()


async def _run_grant_gate_write(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    response = case.load_json("response.json")
    expect = case.load_json("expect.json")

    registry = ToolRegistry()

    @registry.tool(
        description="Write a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        grants=[FsWrite],
        ability=Ability.BASIC,
    )
    def write_file(path: str) -> str:
        return f"wrote {path}"

    tool_calls = [
        ToolCall(
            id=tc["id"],
            name=tc["name"],
            arguments=tc.get("arguments") or {},
        )
        for tc in response.get("tool_calls", [])
    ]

    def _script() -> ScriptedInference:
        return ScriptedInference(
            [
                ChatMessage(role=Role.ASSISTANT, content=None, tool_calls=tool_calls),
                ChatMessage(role=Role.ASSISTANT, content="done"),
            ]
        )

    read_only = AccessPolicy(grants=request.get("read_grants", []))
    with_write = CompoundPolicy.of(
        read_only,
        AccessPolicy(grants=request.get("write_grants", [FsWrite])),
    )

    denied_log = InMemoryEventLog()
    denied = await make_harness(
        _script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=denied_log,
        access_policy=read_only,
    ).run(request.get("prompt", "write"))
    denied_ok = any("Permission denied" in (m.content or "") for m in denied.messages)

    allow_log = InMemoryEventLog()
    allowed = await make_harness(
        _script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=allow_log,
        access_policy=with_write,
    ).run(request.get("prompt", "write"))
    allowed_ok = allowed.final_text == "done"

    actual = {
        "denied_without_write_grant": denied_ok,
        "allowed_with_compound": allowed_ok,
    }
    _assert_expect(actual, expect)


async def _run_config_access_policy(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    layers = [AccessPolicy(grants=layer) for layer in request["layers"]]
    compound = CompoundPolicy.of(*layers)

    class StoryConfig(MechaHarnessConfig):
        def __init__(self) -> None:
            self._inference = ScriptedInference([])
            super().__init__()  # type: ignore[no-untyped-call]

        def get_inference_class(self) -> type[InferenceStrategy]:
            return type(self._inference)

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_access_policy(self):
            return compound

        def configure(self) -> None:
            super().configure()
            self.register_instance(InferenceStrategy, self._inference)

    control = get_injector(StoryConfig()).inject(AccessControl)
    assert isinstance(control, InMemoryAccessControl)
    allows = all(control.allows([g]) for g in request["must_allow"])
    denies = all(not control.allows([g]) for g in request["must_deny"])
    actual = {"allows_compound": allows, "denies_missing": denies}
    _assert_expect(actual, expect)


async def _run_completer_flavors(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    flavor_tags = list(request["flavor_tags"])
    matched_required = list(request["matched_required"])
    assert flavor_tags == ["reason", "code", "deep"]
    assert matched_required == ["reason", "code"]

    class FlavorCompleter(ScriptedInference):
        def __init__(self) -> None:
            super().__init__([])
            self.flavor = "code"

    class CodeReviewHost:
        def __init__(
            self,
            inference: Annotated[Completer, Named(["reason", "code", "deep"])],
            via_matched: Annotated[
                Completer,
                Matched(required=["reason", "code"]),
            ],
        ) -> None:
            self.inference = inference
            self.via_matched = via_matched

    class StoryConfig(MechaHarnessConfig):
        def __init__(self) -> None:
            self._default = ScriptedInference([])
            super().__init__()  # type: ignore[no-untyped-call]

        def get_inference_class(self) -> type[InferenceStrategy]:
            return type(self._default)

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def completer_bindings(self):
            return [
                (Named(["reason"], default=True), self.get_inference_class()),
                (Named(["reason", "code", "deep"]), FlavorCompleter),
            ]

        def configure(self) -> None:
            super().configure()
            self.register_instance(InferenceStrategy, self._default)
            _expose_ctor_type_hints(CodeReviewHost)
            self.register(CodeReviewHost, CodeReviewHost)

    injector = get_injector(StoryConfig())
    default = injector.inject(Completer)
    strategy = injector.inject(InferenceStrategy)
    host = injector.inject(CodeReviewHost)
    actual = {
        "default_is_inference": default is strategy,
        "flavor_selected": getattr(host.inference, "flavor", None) == "code",
        "matched_selects_flavor": host.via_matched is host.inference,
    }
    _assert_expect(actual, expect)


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


async def _run_convergence_ceiling(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    contract = ConvergenceContract(**request["contract"])
    guard = ConvergenceGuard(contract)
    fingerprints = list(request.get("fingerprints", []))
    for fp in fingerprints:
        guard.tick(fingerprint=fp, elapsed_ms=float(request.get("elapsed_ms_per_tick", 1)))
    actual = {
        "terminal_in": guard.state.terminal,
        "reason_in": guard.state.reason,
        "success": guard.state.terminal == "success",
    }
    _assert_expect(actual, expect)


async def _run_context_compiler_deficit(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    compiler = ContextCompiler(token_budget=int(request.get("token_budget", 8)))
    compiled = compiler.compile(
        state_revision=request.get("state_revision", "r1"),
        operation=request.get("operation", "chat"),
        sources=request.get("sources", {}),
        mandatory=request.get("mandatory", []),
        blockers=request.get("blockers", []),
        verification_obligations=request.get("verification_obligations", []),
    )
    actual = {
        "deficit": compiled.deficit,
        "unresolved_gaps_include": compiled.manifest.unresolved_gaps,
        "blockers_include": compiled.manifest.blockers,
        "silent_truncate": (
            not compiled.deficit
            and any(m in compiled.manifest.omitted for m in request.get("mandatory", []))
        ),
    }
    _assert_expect(actual, expect)


async def _run_local_plan_resume(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    ops = default_operations()
    ops.register(
        "write_file",
        lambda **_: None,
        contract=OperationContract(
            name="write_file",
            version="1",
            write_scopes=[ResourceScope(name="app.py", mode="write")],
            preconditions=["approved"],
            external_effects="write",
        ),
    )
    bind = NodeContractBind(
        operation="write_file",
        contract_version="1",
        state_revision=request.get("state_revision", "r1"),
        planned_effects="write",
        evidence_refs=request.get("evidence_refs", []),
    )
    ops.bind_node(bind)
    stale = ops.recheck_preconditions("write_file", satisfied=request.get("satisfied", []))

    graph = ExecutionGraph(goal=request.get("goal", "ship patch"))
    graph.add_node(
        GraphNode(
            id="produce",
            status=NodeStatus.SUCCEEDED,
            write_scopes=["app.py"],
            payload={"path": "app.py", "content": "v1"},
        )
    )
    graph.add_node(
        GraphNode(
            id="consume",
            write_scopes=["app.py"],
            status=NodeStatus.PENDING,
        )
    )
    graph.add_dependency(
        DependencyEdge(
            from_node="produce",
            to_node="consume",
            types=["data", "resource"],
            reason="consume needs produce output; exclusive write",
            evidence_ref="edge:1",
        )
    )
    store = GraphStore()
    store.save(graph, run_id="story-graph", boundary="dispatch")
    restored = store.latest(run_id="story-graph")
    assert restored is not None
    ready = [n.id for n in restored.ready_nodes()]
    fan = hierarchical_fan_in(
        [
            FanInItem(id="ok", source_ref="b1", payload={"id": "x"}),
            FanInItem(id="dup", source_ref="b2", payload={"id": "x"}),
            FanInItem(id="bad", source_ref="b3", payload={"id": "y"}, failed=True),
        ],
        budget=int(request.get("fan_in_budget", 4)),
    )
    merged = merge_branch_artifacts(
        base_revision="r0",
        branches=request.get(
            "branches",
            [
                {"path": "app.py", "content": "a", "status": "ok"},
                {"path": "app.py", "content": "b", "status": "ok"},
            ],
        ),
    )
    actual = {
        "stale_preconditions_include": stale,
        "ready_include": ready,
        "dependency_justified": all(e.reason and e.types for e in restored.edges),
        "fan_in_failures_include": fan.failures,
        "merge_conflicts_include": merged["conflicts"],
        "recovery_boundary_in": store.latest_boundary(run_id="story-graph"),
    }
    _assert_expect(actual, expect)


async def _run_graph_executor_run(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    attempts: list[int] = []

    async def produce(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"value": request.get("produce_value", 1)},
            evidence={"node": node.id},
        )

    async def flaky(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        attempts.append(node.attempt)
        if len(attempts) < int(request.get("fail_until_attempt", 2)):
            return NodeOutcome(status=NodeStatus.FAILED, error="transient")
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"recovered": True})

    async def consume(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del node
        parent = context.graph.nodes["produce"]
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"sum": int(parent.payload.get("value", 0)) + 1},
        )

    class _Heal(GraphEscalation):
        async def handle(self, node: GraphNode, *, context: GraphRunContext) -> NodeOutcome:
            del context
            return NodeOutcome(
                status=NodeStatus.SUCCEEDED,
                payload={**node.payload, "escalated": True},
            )

    registry = GraphNodeRunnerRegistry(
        [
            CallableGraphNodeRunner(["produce"], produce),
            CallableGraphNodeRunner(["flaky"], flaky),
            CallableGraphNodeRunner(["consume"], consume),
        ]
    )

    class StoryGraphConfig(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            from mechaharness.inference.mock import MockInferenceStrategy

            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_harness_config(self) -> HarnessConfig:
            return HarnessConfig(model="story", max_turns=1)

        def get_tools(self) -> ToolRegistry:
            return ToolRegistry()

        def get_grants(self) -> list[object]:
            return list(request.get("grants", [GraphExecute, GraphEscalate]))

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

        def get_graph_escalation(self) -> GraphEscalation:
            return _Heal()

    executor = get_injector(StoryGraphConfig()).inject(GraphExecutor)
    graph = ExecutionGraph(goal=request.get("goal", "local pipe"))
    graph.add_node(GraphNode(id="produce", kind="produce"))
    graph.add_node(
        GraphNode(
            id="flaky",
            kind="flaky",
            depends_on=["produce"],
            max_attempts=int(request.get("max_attempts", 2)),
        )
    )
    graph.add_node(GraphNode(id="consume", kind="consume", depends_on=["flaky"]))
    graph.add_dependency(
        DependencyEdge(
            from_node="produce",
            to_node="flaky",
            types=["data"],
            reason="flaky needs produce",
        )
    )
    graph.add_dependency(
        DependencyEdge(
            from_node="flaky",
            to_node="consume",
            types=["control"],
            reason="consume after repair",
        )
    )

    denied = None
    if request.get("check_deny", True):
        class DenyConfig(StoryGraphConfig):
            def get_grants(self) -> list[object]:
                return []

        denied_exec = get_injector(DenyConfig()).inject(GraphExecutor)
        denied = await denied_exec.run(
            graph.model_copy(deep=True),
            budget_policy=BudgetPolicy.unlimited(),
            run_id="story-deny",
        )

    result = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="story-graph-exec"
    )
    types = [e.type for e in result.events]
    actual = {
        "status": result.status,
        "consume_sum": result.graph.nodes["consume"].payload.get("sum"),
        "emitted_graph_start": "core:graph_start" in types,
        "emitted_graph_end": "core:graph_end" in types,
        "denied_without_execute_grant": denied is not None and denied.status == "denied",
        "flaky_attempts": len(attempts),
    }
    _assert_expect(actual, expect)


async def _run_topology_efficiency(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    spans = [TopologySpan(**s) for s in request["spans"]]
    metrics = compute_topology_metrics(
        spans,
        graph_version=request.get("graph_version", "1"),
        worker_count=request.get("worker_count"),
    )
    actual = {
        "min_total_node_work_ms": metrics.total_node_work_ms,
        "min_elapsed_ms": metrics.elapsed_ms,
        "work_exceeds_elapsed": metrics.total_node_work_ms > metrics.elapsed_ms,
        "notes_include": metrics.notes,
    }
    _assert_expect(actual, expect)


async def _run_shadow_decision_backends(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    report = shadow_decision_backends(
        state_hash=request.get("state_hash", "h"),
        candidate_actions=request.get("candidate_actions", []),
        evidence_refs=request.get("evidence_refs", []),
        backends=request.get("backends", {}),
    )
    by_kind = {c.kind: c for c in report.candidates}
    unavailable = [
        k for k, c in by_kind.items() if not c.available and c.latency_ms is None
    ]
    actual = {
        "unavailable_include": unavailable,
        "available_include": [k for k, c in by_kind.items() if c.available],
        "matched_actions_include": report.matched_inputs.get("candidate_actions", []),
    }
    _assert_expect(actual, expect)


async def _run_validator_qualification(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    def honest(item: str) -> str:
        if item == "missing":
            return "unknown"
        return "pass" if item.startswith("ok") else "fail"

    def always_pass(_item: str) -> str:
        return "pass"

    good = qualify_validator(
        name="honest",
        verifier=honest,
        good_fixtures=request.get("good_fixtures", ["ok1"]),
        bad_fixtures=request.get("bad_fixtures", ["bad1"]),
        missing_fixtures=request.get("missing_fixtures", ["missing"]),
    )
    weak = qualify_validator(
        name="weak",
        verifier=always_pass,
        good_fixtures=["ok"],
        bad_fixtures=["bad"],
    )
    actual = {
        "honest_qualified": validator_qualified(good),
        "weak_qualified": validator_qualified(weak),
    }
    _assert_expect(actual, expect)


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
        lab.promote(accepted[0])
    report = lab.report()
    actual = {
        "rejected_cheap_nonempty": bool(report.rejected_cheap_failures),
        "promoted_nonempty": bool(report.promoted_id),
        "negative_results_nonempty": bool(report.negative_results),
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


async def _run_human_review_pending(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    policy = JudgementPolicy(
        version="story-review",
        require_approval_for=["mutate"],
        thresholds=[
            JudgementThreshold(signal_id="destructive", allow_above=0.9, ask_below=0.9),
        ],
    )
    ask = decide(
        JudgementFacts(action="mutate", action_digest="sha256:story"),
        [NoulSignal(id="destructive", p_true=0.95)],
        policy,
    )
    allow = decide(
        JudgementFacts(
            action="mutate",
            action_digest="sha256:story",
            approvals={"sha256:story": "approved-1"},
        ),
        [NoulSignal(id="destructive", p_true=0.95)],
        policy,
    )
    actual = {"verdict_kinds": [ask.kind, allow.kind]}
    _assert_expect(actual, expect)


async def _run_tool_gating(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    response = case.load_json("response.json")
    expect = case.load_json("expect.json")

    registry = ToolRegistry()

    @registry.tool(
        description="Write a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        grants=[FsWrite],
        ability=Ability.BASIC,
    )
    def write_file(path: str) -> str:
        return f"wrote {path}"

    tool_calls = [
        ToolCall(
            id=tc["id"],
            name=tc["name"],
            arguments=tc.get("arguments") or {},
        )
        for tc in response.get("tool_calls", [])
    ]

    def _script() -> ScriptedInference:
        return ScriptedInference(
            [
                ChatMessage(role=Role.ASSISTANT, content=None, tool_calls=tool_calls),
                ChatMessage(role=Role.ASSISTANT, content="done"),
            ]
        )

    deny_policy = AccessPolicy(grants=request.get("deny_grants", []))
    allow_policy = AccessPolicy(grants=request.get("allow_grants", [FsWrite]))

    denied_log = InMemoryEventLog()
    denied = await make_harness(
        _script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=denied_log,
        access_policy=deny_policy,
    ).run(request.get("prompt", "write"))
    denied_ok = any("Permission denied" in (m.content or "") for m in denied.messages)

    allow_log = InMemoryEventLog()
    allowed = await make_harness(
        _script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=allow_log,
        access_policy=allow_policy,
    ).run(request.get("prompt", "write"))
    allowed_ok = allowed.final_text == "done"

    actual = {
        "denied_without_grant": denied_ok,
        "allowed_with_grant": allowed_ok,
    }
    _assert_expect(actual, expect)


async def _run_bounded_repair_loop(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")

    def has_file(node: GraphNode) -> tuple[bool, dict[str, Any]]:
        ok = bool(node.payload.get("path"))
        return ok, {"file": node.payload.get("path")}

    node = GraphNode(id="repair-story", payload={}, max_attempts=3)
    repaired = bounded_repair(
        node,
        verifiers=[has_file],
        repair=lambda n: n.model_copy(update={"payload": {"path": "/tmp/story.png"}}),
    )
    actual = {"final_status_in": repaired.status.value}
    _assert_expect(actual, expect)


async def _run_context_observation_chain(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    store = ObservationStore()
    store.put(ObservationRef(tool_name="comfy", content="raw bytes"))
    flags = CtxFlags(
        evidence_reduction=True, economic_compaction=True, action_fusion=True
    )
    fake = reduce_evidence(store, "obs:missing", summary="lie", flags=flags)
    fused = fuse_actions(
        ["edit", "test"], allowed_sequences=[["edit", "test"]], flags=flags
    )
    compacted = compact_at_boundary(
        [{"role": "user", "content": str(i)} for i in range(10)],
        flags=flags,
        keep_last=2,
    )
    actual = {
        "fabricated_receipt": bool(fake.fabricated),
        "fused": fused == ["edit", "test"],
        "compacted": len(compacted) < 10,
    }
    _assert_expect(actual, expect)


async def _run_derived_memory(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    store = DerivedMemoryStore()
    events = [
        {"id": "e1", "content": "Redis"},
        {"id": "e2", "content": "Dragonfly"},
        {"id": "e3", "content": "Redis"},
    ]
    store.consolidate_from(events, up_to=2)
    first = len(store.current())
    store.consolidate_from(events, up_to=2)
    idempotent = len(store.current()) == first
    popular = DerivedMemoryRecord(content="rumor", retrieval_rank=99, authority=False)
    rule = DerivedMemoryRecord(content="approval-rule", retrieval_rank=0, authority=True)
    store.apply("add", popular)
    store.apply("add", rule)
    store._published[popular.id] = popular
    store._published[rule.id] = rule
    auth = store.current(authoritative_only=True)
    actual = {
        "authority_outranks_popularity": bool(auth) and all(r.authority for r in auth),
        "idempotent": idempotent,
    }
    _assert_expect(actual, expect)


async def _run_repo_topology(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    topo = RepositoryTopologyProvider()
    view = topo.index(
        revision="r1",
        files={"a.py": "def foo():\n  pass\n", "b.py": "x"},
        budget=1,
    )
    actual = {
        "has_omissions_or_entries": bool(view.entries) or bool(view.omissions),
    }
    _assert_expect(actual, expect)


async def _run_model_affinity(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    decision = route_at_boundary(boundary="task_entry", task_kind="judge")
    policy = JudgementPolicy(
        version="v1",
        thresholds=[JudgementThreshold(signal_id="e", allow_above=0.5)],
    )
    uncalibrated = activate_scoped_policy(
        facts=JudgementFacts(),
        signals=[NoulSignal(id="e", p_true=0.9)],
        policy=policy,
        calibrated=False,
    )
    actual = {
        "selected_lane": decision.selected.lane,
        "uncalibrated_is_null": uncalibrated is None,
    }
    _assert_expect(actual, expect)


async def _run_cache_layout_experiment(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    layout = compile_cache_aware_layout(
        policy_blocks=["policy"],
        relevant=["ctx"],
        dynamic=["q"],
        flags=CtxFlags(cache_aware_layout=True),
        policy_version="v2",
    )
    actual = {"enabled_has_stable_prefix": bool(layout.stable_prefix)}
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


async def _run_graph_linkage_preflight(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    registry = GraphNodeRunnerRegistry(
        [CallableGraphNodeRunner(["compute"], ok), CallableGraphNodeRunner(["loop"], ok)]
    )
    access = InMemoryAccessControl(
        event_log=InMemoryEventLog(),
        policy=AccessPolicy(grants=[GraphExecute]),
    )
    resolver = DefaultLinkageResolver(
        runners=registry,
        access=access,
        environment=NoOpInferenceEnvironment(),
    )

    actual: dict[str, Any] = {}
    if request.get("check_missing_runner", True):
        g = ExecutionGraph(goal="missing")
        g.add_node(GraphNode(id="x", kind="unregistered"))
        report = resolver.resolve(g)
        actual["missing_runner_ok"] = report.ok
        actual["missing_runner_codes_include"] = [e.code for e in report.edges]
    if request.get("check_missing_stop", True):
        g = ExecutionGraph(goal="loop")
        g.add_node(GraphNode(id="loop", kind="loop", repeating=True))
        report = resolver.resolve(g)
        actual["missing_stop_ok"] = report.ok
        actual["missing_stop_codes_include"] = [e.code for e in report.edges]
    if request.get("check_ok_linear", True):
        g = ExecutionGraph(goal="ok")
        g.add_node(GraphNode(id="a", kind="compute"))
        g.add_node(GraphNode(id="b", kind="compute", depends_on=["a"]))
        report = resolver.resolve(g)
        actual["ok_linear_ok"] = report.ok
        actual["ok_linear_fingerprint_nonempty"] = bool(report.fingerprint)
    _assert_expect(actual, expect)


async def _run_graph_template_soft_points(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    registry = default_graph_templates()
    template = registry.get(str(request["template"]))
    assert template is not None
    n = int(request.get("branch_count", 2))
    graph = template.instantiate(
        GraphTemplateParams(
            goal=str(request.get("goal") or ""),
            branch_payloads=[{"index": i} for i in range(n)],
            acceptance=list(request.get("acceptance") or []),
            source_workflow_ref=request.get("source_workflow_ref"),
        )
    )
    demoted = FanOutAggregateTemplate()
    demoted.status = "demoted"
    refused = False
    try:
        demoted.instantiate(GraphTemplateParams(goal="nope"))
    except RuntimeError:
        refused = True
    catalog = registry.catalog()
    soft_nonempty = all(bool(row.get("soft_points")) for row in catalog)
    actual = {
        "template_name": graph.template_name,
        "template_status": graph.template_status,
        "node_ids_include": list(graph.nodes),
        "source_workflow_ref": graph.source_workflow_ref,
        "catalog_soft_points_nonempty": soft_nonempty,
        "demoted_refused": refused,
    }
    _assert_expect(actual, expect)


async def _run_capability_envelope_narrow(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    parent = CapabilityEnvelope(grants=list(request["parent_grants"]))
    child = parent.narrow(grants=list(request["child_grants"]))
    widen_raises = False
    try:
        parent.narrow(grants=list(request["widen_grants"]))
    except ValueError:
        widen_raises = True
    decision = DefaultDelegationPolicy().decide(
        DelegationRequest(independence_required=True, parent_envelope=parent)
    )
    actual = {
        "narrow_ok": set(child.grants).issubset(set(parent.grants)),
        "child_grant_count": len(child.grants),
        "widen_raises": widen_raises,
        "delegation_choice": decision.choice,
    }
    _assert_expect(actual, expect)


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


async def _run_consequence_risk_scale(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    policy = ConsequencePolicy(
        actions=[
            ActionConsequence(
                action=str(request["action"]),
                consequence=request.get("consequence", "high"),
                requires_approval=True,
            )
        ]
    )
    policy.record_approval_prompt()
    policy.record_approval_decision()
    actual = {
        "requires_stronger_controls": policy.requires_stronger_controls(str(request["action"])),
        "approval_frequency": policy.approval_frequency(),
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


async def _run_dynamic_subgraph_nest(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            from mechaharness.inference.mock import MockInferenceStrategy

            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

    executor = get_injector(Cfg()).inject(GraphExecutor)
    child = ExecutionGraph(goal=str(request.get("child_goal") or "child"))
    child.add_node(GraphNode(id="c1", kind="compute"))
    parent = ExecutionGraph(goal=str(request.get("parent_goal") or "parent"))
    parent.add_node(SubgraphNodeRunner.embed(child, parent_node_id="wrap"))
    result = await executor.run(
        parent,
        budget_policy=BudgetPolicy.unlimited(),
        skip_linkage=True,
        run_id="story-subgraph",
    )
    wrap = result.graph.nodes["wrap"]
    actual = {
        "status": result.status,
        "child_status": wrap.payload.get("child_status"),
        "child_run_id_nonempty": bool(wrap.payload.get("child_run_id")),
    }
    _assert_expect(actual, expect)


async def _run_context_provider_discovery(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    provider = StaticContextProvider(
        str(request["provider_id"]),
        {str(request["ref"]): str(request["content"])},
    )
    entries = provider.index(budget=8)
    chunks = provider.load([str(request["ref"])])
    actual = {
        "index_count": len(entries),
        "loaded_provider_id": chunks[0].provider_id if chunks else None,
        "token_estimate_min": chunks[0].token_estimate if chunks else 0,
    }
    _assert_expect(actual, expect)


async def _run_instruction_gotcha_metrics(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    catalog = InstructionCatalog()
    gotcha = catalog.append_gotcha(
        str(request["title"]),
        str(request["body"]),
        provenance={"source": "client"},
    )
    if request.get("over_trigger"):
        gotcha.record_trigger(used=True, appropriate=False)
    else:
        gotcha.record_trigger(used=True, appropriate=True)
    catalog.promote(gotcha.id)
    actual = {
        "over_trigger_count": gotcha.over_trigger_count,
        "status_after_promote": gotcha.status,
        "active_gotcha_count": len(catalog.active(kind="gotcha")),
    }
    _assert_expect(actual, expect)


async def _run_independent_review_template(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    graph = IndependentReviewTemplate().instantiate(
        GraphTemplateParams(
            goal="review",
            inputs={"reviewer_count": int(request.get("reviewer_count", 1))},
            acceptance=list(request.get("acceptance") or []),
        )
    )
    reviews = [n for n in graph.nodes if n.startswith("review_")]
    actual = {
        "review_count": len(reviews),
        "omit_producer_reasoning": graph.nodes[reviews[0]].payload.get(
            "omit_producer_reasoning"
        ),
        "retain_disagreement": graph.nodes["aggregate_reviews"].payload.get(
            "retain_disagreement"
        ),
        "template_name": graph.template_name,
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


async def _run_checkpoint_fingerprint_refuse(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            from mechaharness.inference.mock import MockInferenceStrategy

            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

    executor = get_injector(Cfg()).inject(GraphExecutor)
    graph = ExecutionGraph(goal=str(request.get("goal") or "fp"), version="1")
    graph.add_node(GraphNode(id="a", kind="compute"))
    first = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="insp-fp"
    )
    executor.fingerprint_parts = {"harness_version": "changed"}
    resumed = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="insp-fp", resume=True
    )
    actual = {
        "first_status": first.status,
        "resume_status": resumed.status,
        "error_contains": resumed.error or "",
    }
    _assert_expect(actual, expect)


async def _run_capability_need_routing(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    route = route_for_capability_needs(
        capability_needs=list(request.get("capability_needs") or []),
        available_model_classes=list(request.get("available_model_classes") or []),
    )
    actual = {"selected_model_class": route["selected_model_class"]}
    _assert_expect(actual, expect)


async def _run_environment_linkage_fail(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    class StrictEnv(InferenceEnvironment):
        def active_profile(self) -> str | None:
            return "story-strict"

        def active_capabilities(self):
            from mechaharness.core.access import CapabilityProfile

            return CapabilityProfile()

        def active_grants(self) -> list[str]:
            return []

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])
    access = InMemoryAccessControl(
        event_log=InMemoryEventLog(),
        policy=AccessPolicy(grants=[GraphExecute]),
    )
    from mechaharness.capability_envelope import CapabilityEnvelope

    resolver = DefaultLinkageResolver(
        runners=registry,
        access=access,
        environment=StrictEnv(),
    )
    graph = ExecutionGraph(goal="env")
    graph.add_node(GraphNode(id="a", kind="compute"))
    report = resolver.resolve(
        graph,
        envelope=CapabilityEnvelope(grants=[str(request.get("required_grant"))]),
    )
    actual = {
        "ok": report.ok,
        "codes_include": [e.code for e in report.edges],
    }
    _assert_expect(actual, expect)


async def _run_wake_reresolve_resume(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            from mechaharness.inference.mock import MockInferenceStrategy

            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

    inj = get_injector(Cfg())
    executor = inj.inject(GraphExecutor)
    graph = ExecutionGraph(goal=str(request.get("goal") or "wake"))
    graph.add_node(GraphNode(id="a", kind="compute"))
    # Client wake: resolve then run; checkpoint; wake again with matching fingerprint
    first = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="insp-wake"
    )
    resolve = executor.linkage_resolver.resolve(first.graph)
    resumed = await executor.run(
        first.graph, budget_policy=BudgetPolicy.unlimited(), run_id="insp-wake", resume=True
    )
    actual = {
        "resolve_ok": resolve.ok,
        "resume_status": resumed.status,
        "fingerprint_nonempty": bool(first.graph.config_fingerprint or resolve.fingerprint),
    }
    _assert_expect(actual, expect)


def _story_graph_executor(registry: GraphNodeRunnerRegistry) -> GraphExecutor:
    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            from mechaharness.inference.mock import MockInferenceStrategy

            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

    return get_injector(Cfg()).inject(GraphExecutor)


async def _run_graph_budget_limits(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    cost = float(request.get("node_cost", 1))

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"id": node.id},
            cost_units=cost,
        )

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])
    executor = _story_graph_executor(registry)

    def _linear() -> ExecutionGraph:
        g = ExecutionGraph(goal="budget-limits")
        g.add_node(GraphNode(id="a", kind="compute", payload={"cost_units": cost}))
        g.add_node(
            GraphNode(
                id="b",
                kind="compute",
                depends_on=["a"],
                payload={"cost_units": cost},
            )
        )
        return g

    soft_pol = BudgetPolicy(
        soft_limit=request["soft_policy"].get("soft_limit"),
        hard_limit=request["soft_policy"].get("hard_limit"),
    )
    soft = await executor.run(_linear(), budget_policy=soft_pol, run_id="story-budget-soft")
    hard_pol = BudgetPolicy(
        soft_limit=request["hard_policy"].get("soft_limit"),
        hard_limit=request["hard_policy"].get("hard_limit"),
    )
    hard = await executor.run(_linear(), budget_policy=hard_pol, run_id="story-budget-hard")
    actual = {
        "soft_status": soft.status,
        "soft_error": soft.error,
        "soft_budget_level": soft.budget_level,
        "hard_status": hard.status,
        "hard_error": hard.error,
        "hard_budget_level": hard.budget_level,
    }
    _assert_expect(actual, expect)


async def _run_graph_budget_subgraph_rollup(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    cost = float(request.get("node_cost", 1))

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(
            status=NodeStatus.SUCCEEDED,
            payload={"id": node.id},
            cost_units=cost,
        )

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])
    executor = _story_graph_executor(registry)

    child = ExecutionGraph(goal="child-budget")
    child.add_node(GraphNode(id="c1", kind="compute", payload={"cost_units": cost}))
    child.add_node(
        GraphNode(
            id="c2",
            kind="compute",
            depends_on=["c1"],
            payload={"cost_units": cost},
        )
    )
    parent = ExecutionGraph(goal="parent-budget")
    parent.add_node(SubgraphNodeRunner.embed(child, parent_node_id="wrap"))
    parent.add_node(
        GraphNode(
            id="after",
            kind="compute",
            depends_on=["wrap"],
            payload={"cost_units": cost},
        )
    )
    policy = BudgetPolicy(
        soft_limit=request.get("soft_limit"),
        hard_limit=request.get("hard_limit"),
    )
    result = await executor.run(
        parent,
        budget_policy=policy,
        skip_linkage=True,
        run_id="story-budget-rollup",
    )
    actual = {
        "status": result.status,
        "budget_spent": result.budget_spent,
        "budget_level": result.budget_level,
        "error": result.error,
        "after_status": parent.nodes["after"].status.value,
    }
    _assert_expect(actual, expect)


class _WatchA(LifecycleExtension):
    extension_id = "acme:watch_a"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({ObserveBefore})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(mode=ObserveBefore.key(), notes={"tag": "a"})


class _WatchB(LifecycleExtension):
    extension_id = "acme:watch_b"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({ObserveBefore})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(mode=ObserveBefore.key(), notes={"tag": "b"})


class _SandboxRewrite(LifecycleExtension):
    extension_id = "acme:sandbox_rewrite"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({Rewrite})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        path = str(context.arguments.get("path", ""))
        return ExtensionEffect(
            mode=Rewrite.key(),
            rewrite_arguments={"path": f"/sandbox/{path}"},
        )


class _BlockWrite(LifecycleExtension):
    extension_id = "acme:block_write"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({Block})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(
            mode=Block.key(),
            block=True,
            block_message="blocked by host extension",
        )


class _ReplaceWrite(LifecycleExtension):
    extension_id = "acme:replace_write"
    version = "1"
    boundary = BeforeTool
    modes = frozenset({Replace})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(
            mode=Replace.key(),
            replace_content="hand-off: skipped write",
        )


class _GraphWatch(LifecycleExtension):
    extension_id = "acme:graph_watch"
    version = "1"
    boundary = BeforeGraphNode
    modes = frozenset({ObserveBefore})

    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        del context
        return ExtensionEffect(mode=ObserveBefore.key())


def _lifecycle_write_registry() -> ToolRegistry:
    registry = ToolRegistry()

    @registry.tool(
        description="Write a file",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        grants=[FsWrite],
        ability=Ability.BASIC,
    )
    def write_file(path: str) -> str:
        return f"wrote {path}"

    return registry


async def _run_lifecycle_tool_story(
    case: StoryCase,
    *,
    extensions: list[LifecycleExtension],
) -> dict[str, Any]:
    request = case.load_json("request.json")
    response = case.load_json("response.json")
    tool_calls = [
        ToolCall(
            id=tc["id"],
            name=tc["name"],
            arguments=tc.get("arguments") or {},
        )
        for tc in response.get("tool_calls", [])
    ]
    inference = ScriptedInference(
        [
            ChatMessage(role=Role.ASSISTANT, content=None, tool_calls=tool_calls),
            ChatMessage(role=Role.ASSISTANT, content="done"),
        ]
    )
    log = InMemoryEventLog()
    grants = list(request.get("grants", [FsWrite]))
    result = await make_harness(
        inference,
        tools=_lifecycle_write_registry(),
        config=HarnessConfig(model="story", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=log,
        access_policy=AccessPolicy(grants=grants),
        lifecycle_extensions=LifecycleExtensionRegistry(extensions),
        capability_envelope=CapabilityEnvelope.from_grants(grants),
    ).run(request.get("prompt", "write"))
    rid = result.events[0].run_id if result.events else None
    ext_events = [
        e for e in log.query(run_id=rid) if e.type == "core:extension_applied"
    ]
    tool_msgs = [m.content or "" for m in result.messages if m.role == Role.TOOL]
    tool_result = tool_msgs[0] if tool_msgs else ""
    # Mutative flags / default_ran are taken from before_tool events only.
    before_events = [
        e for e in ext_events if e.payload.get("boundary") == "core:before_tool"
    ]
    focus = before_events or ext_events
    return {
        "extension_ids": [e.payload.get("extension_id") for e in focus],
        "orders": [e.payload.get("order") for e in focus],
        "default_ran": all(bool(e.payload.get("default_ran")) for e in focus)
        if focus
        else False,
        "applied_rewrite": any(bool(e.payload.get("applied_rewrite")) for e in focus),
        "applied_block": any(bool(e.payload.get("applied_block")) for e in focus),
        "applied_replace": any(bool(e.payload.get("applied_replace")) for e in focus),
        "tool_result_contains": tool_result,
    }


async def _run_lifecycle_extension_observe(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    actual = await _run_lifecycle_tool_story(case, extensions=[_WatchA(), _WatchB()])
    # Also ensure AfterTool observers are optional; before-tool order is the claim.
    _assert_expect(
        {
            "extension_ids": actual["extension_ids"],
            "orders": actual["orders"],
            "default_ran": actual["default_ran"],
            "tool_result_contains": actual["tool_result_contains"],
        },
        expect,
    )


async def _run_lifecycle_extension_rewrite(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    actual = await _run_lifecycle_tool_story(case, extensions=[_SandboxRewrite()])
    _assert_expect(
        {
            "tool_result_contains": actual["tool_result_contains"],
            "applied_rewrite": actual["applied_rewrite"],
            "default_ran": actual["default_ran"],
        },
        expect,
    )


async def _run_lifecycle_extension_block(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    actual = await _run_lifecycle_tool_story(case, extensions=[_BlockWrite()])
    _assert_expect(
        {
            "tool_result_contains": actual["tool_result_contains"],
            "applied_block": actual["applied_block"],
            "default_ran": actual["default_ran"],
        },
        expect,
    )


async def _run_lifecycle_extension_replace(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    expect = case.load_json("expect.json")
    actual = await _run_lifecycle_tool_story(case, extensions=[_ReplaceWrite()])
    _assert_expect(
        {
            "tool_result_contains": actual["tool_result_contains"],
            "applied_replace": actual["applied_replace"],
            "default_ran": actual["default_ran"],
        },
        expect,
    )


async def _run_lifecycle_extension_graph_observe(
    case: StoryCase, backend: StoryBackend
) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    log = InMemoryEventLog()

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    registry = GraphNodeRunnerRegistry([CallableGraphNodeRunner(["compute"], ok)])

    class Cfg(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            from mechaharness.inference.mock import MockInferenceStrategy

            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return PassThroughHarness

        def get_grants(self) -> list[object]:
            return [GraphExecute]

        def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
            return registry

        def get_event_log(self) -> InMemoryEventLog:
            return log

        def get_lifecycle_extension_registry(self) -> LifecycleExtensionRegistry:
            return LifecycleExtensionRegistry([_GraphWatch()])

    executor = get_injector(Cfg()).inject(GraphExecutor)
    graph = ExecutionGraph(goal=str(request.get("goal") or "lifecycle"))
    graph.add_node(GraphNode(id="a", kind="compute"))
    result = await executor.run(
        graph, budget_policy=BudgetPolicy.unlimited(), run_id="lifecycle-graph"
    )
    ext_events = [
        e for e in log.query(run_id="lifecycle-graph") if e.type == "core:extension_applied"
    ]
    before = next(
        (e for e in ext_events if e.payload.get("boundary") == "core:before_graph_node"),
        None,
    )
    actual = {
        "graph_status": result.status,
        "boundary": before.payload.get("boundary") if before else None,
        "extension_id": before.payload.get("extension_id") if before else None,
        "default_ran": bool(before.payload.get("default_ran")) if before else False,
    }
    _assert_expect(actual, expect)
