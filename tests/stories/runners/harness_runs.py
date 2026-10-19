"""Harness-run, routing, and host-kit story runners."""

from __future__ import annotations

from typing import Annotated

from pyiv.http import AsyncUrllibHttpClient, MemoryAsyncHttpClient
from pyiv.key import Matched, Named
from pyiv.process import OsEnvironment

from mechaharness.api_connection import SimpleHttpConnectionConfig
from mechaharness.core.access import (
    AccessPolicy,
    GraphExecute,
    InMemoryAccessControl,
)
from mechaharness.core.completer import Completer
from mechaharness.core.environment import (
    NoOpInferenceEnvironment,
)
from mechaharness.core.events import InMemoryEventLog
from mechaharness.di import MechaHarnessConfig, _expose_ctor_type_hints, get_injector
from mechaharness.graph import (
    ExecutionGraph,
    GraphNode,
)
from mechaharness.graph_executor import (
    CallableGraphNodeRunner,
    GraphNodeRunnerRegistry,
)
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.judge import (
    ChoiceSignal,
    FixtureJudgeProvider,
    JudgeRequest,
    hash_state,
    judge,
)
from mechaharness.inference.systemone import SystemOneJudgeProvider
from mechaharness.inference_capture import EvaluationOnlyCapture
from mechaharness.judgement_policy import (
    JudgementFacts,
    decide,
)
from mechaharness.linkage_resolver import DefaultLinkageResolver
from tests.fakes import ScriptedInference
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.runners._support import (
    StoryRunner,
    _assert_expect,
    _build_questions,
    _policy_from_request,
)


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
    "route_refund": _run_route_refund,
    "systemone_cassette": _run_route_refund,
    "completer_flavors": _run_completer_flavors,
    "host_kit_submit_once": _run_host_kit_submit_once,
    "inference_capture_preflight": _run_inference_capture_preflight,
}
