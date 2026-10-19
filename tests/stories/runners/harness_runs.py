"""Harness-run, routing, and host-kit story runners."""

from __future__ import annotations

import os
from typing import Annotated, Any

import pytest
from pyiv.http import AsyncUrllibHttpClient, MemoryAsyncHttpClient
from pyiv.key import Matched, Named
from pyiv.process import OsEnvironment

from mechaharness.api_connection import SimpleHttpConnectionConfig
from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.config import Settings
from mechaharness.conversational_tool_loop_runner import ConversationalToolLoopRunner
from mechaharness.core.access import (
    AccessPolicy,
    GraphExecute,
    InMemoryAccessControl,
)
from mechaharness.core.completer import Completer
from mechaharness.core.contract import RunRequest
from mechaharness.core.environment import (
    NoOpInferenceEnvironment,
)
from mechaharness.core.events import InMemoryEventLog
from mechaharness.core.types import ChatMessage, Role, ToolCall
from mechaharness.di import MechaHarnessConfig, _expose_ctor_type_hints, get_injector
from mechaharness.graph import (
    ExecutionGraph,
    GraphNode,
    NodeStatus,
)
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphNodeRunnerRegistry,
    GraphRunContext,
    NodeOutcome,
)
from mechaharness.graph_templates import (
    ConversationalToolLoopTemplate,
    GraphTemplateParams,
)
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.host_kit import host_graph_executor, tapping_event_log
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.judge import (
    ChoiceSignal,
    FixtureJudgeProvider,
    JudgeRequest,
    NoulSignal,
    hash_state,
    judge,
)
from mechaharness.inference.openai_compat import OpenAICompatStrategy
from mechaharness.inference.systemone import SystemOneJudgeProvider
from mechaharness.inference_capture import EvaluationOnlyCapture
from mechaharness.judgement_policy import (
    JudgementFacts,
    JudgementPolicy,
    JudgementThreshold,
    decide,
)
from mechaharness.linkage_resolver import DefaultLinkageResolver
from mechaharness.model_input_manifest import (
    ModelInputManifest,
    attach_manifest_ref,
    reconstruct_messages,
)
from mechaharness.node_component import (
    traversal_from_events,
)
from mechaharness.recipe_runner import (
    instantiate_recipe,
    list_recipes,
    run_backend_describe_recipe,
    run_harness_recipe,
)
from mechaharness.routing import (
    activate_scoped_policy,
    route_at_boundary,
    route_for_capability_needs,
    shadow_decision_backends,
)
from mechaharness.run_parity import compare_parity, parity_from_harness_config
from tests.fakes import ScriptedInference
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.runners._support import (
    StoryRunner,
    _assert_expect,
    _build_questions,
    _policy_from_request,
)
from tests.support.di import make_harness


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
        base = (settings.base_url or "http://story.invalid/v1").rstrip("/")
        if backend.mode == "static":
            client = MemoryAsyncHttpClient()
            client.add("POST", f"{base}/chat/completions", json=response)
        else:
            if not os.environ.get("MECHA_BASE_URL"):
                pytest.fail("MECHA_BASE_URL is required for live openai_compat stories")
            client = AsyncUrllibHttpClient(timeout=180.0)
        strategy = OpenAICompatStrategy(settings, client=client, timeout=180.0)
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
    provider_aclose = None

    if case.adapter == "in_process":
        provider = FixtureJudgeProvider(response.get("answers", {}))
    elif case.adapter == "systemone":
        if backend.mode == "static":
            connection = SimpleHttpConnectionConfig(
                base_url="http://story.invalid",
                path="/v1/systemone",
                model="laya",
            )
            client = MemoryAsyncHttpClient()
            client.add("POST", connection.endpoint_url(), json=response)
            provider = SystemOneJudgeProvider(connection=connection, client=client)
        else:
            provider = SystemOneJudgeProvider(
                connection=SimpleHttpConnectionConfig.for_judge(env=OsEnvironment()),
                client=AsyncUrllibHttpClient(),
            )
            provider_aclose = provider
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
        if provider_aclose is not None:
            await provider_aclose.aclose()

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


async def _run_host_kit_submit_once(case: StoryCase, backend: StoryBackend) -> None:
    """Fangore host kit: readable GraphExecutor + submit-once acceptance."""
    del backend
    import tempfile
    from pathlib import Path

    from tests.support.host_kit_cases import assert_expect, iter_cases, run_case

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    scenario_expect = dict(expect.get("scenarios") or {})
    wanted = list(request.get("scenarios") or [])
    assert wanted, "request.json must list scenarios"
    by_id = {c.id: c for c in iter_cases()}

    with tempfile.TemporaryDirectory(prefix="mh-host-kit-story-") as tmp:
        for scenario_id in wanted:
            fixture = by_id.get(scenario_id)
            assert fixture is not None, f"missing host_kit fixture {scenario_id!r}"
            soft = dict(scenario_expect.get(scenario_id) or {})
            db = Path(tmp) / f"{scenario_id}.sqlite"
            durable = bool(fixture.data.get("durable", True))
            payload = await run_case(fixture, db_path=db if durable else None)
            assert_expect(payload["actual"], soft, case_id=scenario_id)


async def _run_host_kit_event_tap(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    seen: list[str] = []

    async def ok(node: GraphNode, context: GraphRunContext) -> NodeOutcome:
        del context
        return NodeOutcome(status=NodeStatus.SUCCEEDED, payload={"id": node.id})

    log = tapping_event_log(on_event=lambda e: seen.append(str(getattr(e, "type", ""))))
    executor = host_graph_executor(
        runners=[CallableGraphNodeRunner([str(request.get("node_kind") or "compute")], ok)],
        event_log=log,
    )
    graph = ExecutionGraph(goal="tap")
    graph.add_node(GraphNode(id="n0", kind=str(request.get("node_kind") or "compute")))
    result = await executor.run(
        graph,
        budget_policy=BudgetPolicy.unlimited(),
        run_id=str(request.get("run_id") or "tap-1"),
        skip_linkage=True,
    )
    actual = {
        "status": result.status,
        "has_graph_node_start": any("graph_node_start" in t for t in seen),
        "has_graph_node_end": any("graph_node_end" in t for t in seen),
    }
    _assert_expect(actual, expect)


async def _run_harness_tool_loop_graph(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    from mechaharness.tools.base import Tool, ToolRegistry
    from tests.fakes import ScriptedInference
    from tests.support.di import make_harness

    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    tool_name = str(request.get("tool_name") or "lookup")
    registry = ToolRegistry()
    registry.register(Tool(tool_name, lambda: "ok", description="story tool"))
    log = InMemoryEventLog()
    script = ScriptedInference(
        [
            ChatMessage(
                role=Role.ASSISTANT,
                content=None,
                tool_calls=[ToolCall(id="c1", name=tool_name, arguments={})],
            ),
            ChatMessage(role=Role.ASSISTANT, content="done"),
        ]
    )
    result = await make_harness(
        script,
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        harness_cls=ToolLoopHarness,
        event_log=log,
    ).run(str(request.get("user_input") or "go"))
    events = result.events or log.query()
    records = traversal_from_events(
        [
            {"type": e.type, "payload": e.payload}
            for e in events
        ]
    )
    kinds = {r.kind for r in records}
    actual = {
        "ok": result.final_text == "done",
        "has_inference": "inference" in kinds,
        "has_tool_call": "tool_call" in kinds,
        "parent_is_harness": all(
            r.parent_node_id == "harness"
            for r in records
            if r.kind in {"inference", "tool_call", "tool_result", "turn_start"}
        ),
    }
    _assert_expect(actual, expect)


async def _run_harness_run_recipe(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    catalog = {row["name"] for row in list_recipes()}
    response = await run_harness_recipe(
        RunRequest(
            prompt=str(request["prompt"]),
            backend=str(request.get("backend") or "mock"),
            family=str(request.get("family") or "pass_through"),
            max_turns=int(request.get("max_turns") or 4),
        )
    )
    graph = instantiate_recipe(
        "harness_run",
        GraphTemplateParams(
            goal="harness_run",
            inputs={"prompt": request["prompt"]},
            soft_bindings={
                "prompt": request["prompt"],
                "backend": request.get("backend") or "mock",
                "family": request.get("family") or "pass_through",
            },
        ),
    )
    actual = {
        "in_catalog": "harness_run" in catalog,
        "status": "ok",
        "final_text_nonempty": bool((response.final_text or "").strip()),
        "turns_min": int(response.turns or 0),
        "has_prepare": "prepare" in graph.nodes,
        "has_harness_loop": "harness_loop" in graph.nodes,
        "has_render": "render" in graph.nodes,
    }
    _assert_expect(actual, expect)


async def _run_backend_describe_recipe(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    catalog = {row["name"] for row in list_recipes()}
    settings_kwargs: dict[str, Any] = {
        "inference_backend": str(request.get("backend") or "mock"),
    }
    for key in ("model", "base_url", "api_key"):
        if request.get(key) is not None:
            settings_kwargs[key] = request[key]
    settings = Settings(**settings_kwargs)
    description = await run_backend_describe_recipe(settings)
    graph = instantiate_recipe(
        "backend_describe",
        GraphTemplateParams(
            goal="backend_describe",
            soft_bindings={"backend": settings.inference_backend},
        ),
    )
    actual = {
        "in_catalog": "backend_describe" in catalog,
        "status": "ok",
        "description_name": description.get("name"),
        "has_describe_node": "describe" in graph.nodes,
    }
    _assert_expect(actual, expect)


async def _run_conversational_tool_loop(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    tool_name = str(request.get("tool_name") or "lookup")
    calls = {"n": 0}

    def complete(messages: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
        del messages, meta
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "function": {"name": tool_name, "arguments": "{}"}}
                ],
            }
        return {"role": "assistant", "content": "done", "tool_calls": []}

    runner = ConversationalToolLoopRunner(
        complete=complete,
        dispatch_tool=lambda name, args: f"ok:{name}",
    )
    graph = ConversationalToolLoopTemplate().instantiate(
        GraphTemplateParams(
            goal="loop",
            inputs={"max_iterations": int(request.get("max_iterations") or 4)},
        )
    )
    executor = host_graph_executor(runners=[runner])
    result = await executor.run(
        graph,
        budget_policy=BudgetPolicy.unlimited(),
        run_id="story-ctl",
        skip_linkage=True,
    )
    tools = result.graph.nodes["tools"]
    child = ExecutionGraph.resume(tools.subgraph or {})
    ids = list(child.nodes)
    actual = {
        "status": result.status,
        "has_inference_node": any(i.endswith("/inference") for i in ids),
        "has_tool_call_node": any(f"tool_call:{tool_name}" in i for i in ids),
        "rounds_min": int(tools.payload.get("rounds") or 0),
    }
    _assert_expect(actual, expect)


async def _run_model_input_manifest_replay(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    manifest = ModelInputManifest.from_parts(
        messages=list(request.get("messages") or []),
        tool_definitions=list(request.get("tool_definitions") or []),
        instructions=list(request.get("instructions") or []),
    )
    reconstructed = reconstruct_messages(manifest)
    fields = attach_manifest_ref({}, manifest)
    actual = {
        "hashes_ok": manifest.verify_hashes(),
        "reconstructed_equals": reconstructed == list(request.get("messages") or []),
        "manifest_ref_nonempty": bool(fields.get("context_manifest_ref")),
    }
    _assert_expect(actual, expect)


async def _run_run_parity_compare(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")

    def _surface(raw: dict[str, Any]):
        cfg = HarnessConfig(
            model=raw["model"],
            max_tokens=raw.get("max_tokens"),
            temperature=raw.get("temperature"),
            max_turns=int(raw.get("max_turns") or 8),
        )
        env = CapabilityEnvelope(tool_names=list(raw.get("tools") or []))
        return parity_from_harness_config(cfg, envelope=env)

    report = compare_parity(_surface(request["a"]), _surface(request["b"]))
    actual = {
        "comparable": report.comparable,
        "material_mismatches_include": report.material_mismatches,
    }
    _assert_expect(actual, expect)


async def _run_inference_capture_preflight(case: StoryCase, backend: StoryBackend) -> None:
    del backend
    request = case.load_json("request.json")
    expect = case.load_json("expect.json")
    reg = GraphNodeRunnerRegistry()

    async def ok(node, context):  # noqa: ANN001
        from mechaharness.graph import NodeStatus
        from mechaharness.graph_executor import NodeOutcome

        return NodeOutcome(status=NodeStatus.SUCCEEDED)

    reg.register(CallableGraphNodeRunner(["compute"], ok))
    access = InMemoryAccessControl(
        InMemoryEventLog(), AccessPolicy(grants=[GraphExecute])
    )
    resolver = DefaultLinkageResolver(
        reg,
        access,
        NoOpInferenceEnvironment(),
        inference_capture=EvaluationOnlyCapture(),
    )
    graph = ExecutionGraph(goal="capture")
    graph.add_node(GraphNode(id="a", kind="compute"))
    report = resolver.resolve(
        graph,
        fingerprint_parts={
            "required_inference_capture": request.get("required_inference_capture")
        },
    )
    actual = {
        "ok": report.ok,
        "codes_include": [e.code for e in report.edges],
    }
    _assert_expect(actual, expect)



RUNNERS: dict[str, StoryRunner] = {
    "pass_through": _run_pass_through,
    "route_refund": _run_route_refund,
    "systemone_cassette": _run_route_refund,
    "completer_flavors": _run_completer_flavors,
    "shadow_decision_backends": _run_shadow_decision_backends,
    "model_affinity": _run_model_affinity,
    "capability_need_routing": _run_capability_need_routing,
    "host_kit_submit_once": _run_host_kit_submit_once,
    "host_kit_event_tap": _run_host_kit_event_tap,
    "harness_tool_loop_graph": _run_harness_tool_loop_graph,
    "conversational_tool_loop": _run_conversational_tool_loop,
    "harness_run_recipe": _run_harness_run_recipe,
    "backend_describe_recipe": _run_backend_describe_recipe,
    "model_input_manifest_replay": _run_model_input_manifest_replay,
    "run_parity_compare": _run_run_parity_compare,
    "inference_capture_preflight": _run_inference_capture_preflight,
}
