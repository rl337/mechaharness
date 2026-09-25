"""Execute user-story kinds against static or live backends."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest
from pyiv import get_injector

from mechaharness.api_connection import SimpleHttpConnectionConfig
from mechaharness.config import Settings
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
from mechaharness.convergence import ConvergenceContract, ConvergenceGuard
from mechaharness.core.access import (
    Ability,
    AccessControl,
    AccessPolicy,
    CompoundPolicy,
    FsWrite,
    InMemoryAccessControl,
)
from mechaharness.core.environment import (
    InferenceEnvironment,
    InferenceEnvironmentError,
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
from mechaharness.di import MechaHarnessConfig
from mechaharness.graph import (
    DependencyEdge,
    ExecutionGraph,
    FanInItem,
    GraphNode,
    GraphStore,
    NodeStatus,
    bounded_repair,
    hierarchical_fan_in,
    merge_branch_artifacts,
    qualify_validator,
    validator_qualified,
)
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
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
from mechaharness.judgement_policy import (
    JudgementFacts,
    JudgementPolicy,
    JudgementThreshold,
    decide,
)
from mechaharness.operation_registry import (
    NodeContractBind,
    OperationContract,
    ResourceScope,
    default_operations,
)
from mechaharness.research import EvalProtocol, ResearchLab
from mechaharness.routing import (
    activate_scoped_policy,
    route_at_boundary,
    shadow_decision_backends,
)
from mechaharness.tools.base import ToolRegistry
from tests.fakes import ScriptedInference
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase


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
        elif key.startswith("min_") and isinstance(wanted, (int, float)):
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
        "fixture_judge_batch": _run_fixture_judge_batch,
        "decision_surface_reject": _run_decision_surface_reject,
        "convergence_ceiling": _run_convergence_ceiling,
        "context_compiler_deficit": _run_context_compiler_deficit,
        "local_plan_resume": _run_local_plan_resume,
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
        harness = PassThroughHarness(
            inference=inference,
            config=HarnessConfig(model=model, max_turns=1),
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
        harness = PassThroughHarness(
            inference=strategy,
            config=HarnessConfig(
                model=settings.model,
                max_turns=1,
                max_tokens=settings.max_tokens,
            ),
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
    denied = await ToolLoopHarness(
        inference=_script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        event_log=denied_log,
        access=InMemoryAccessControl(event_log=denied_log, policy=read_only),
    ).run(request.get("prompt", "write"))
    denied_ok = any("Permission denied" in (m.content or "") for m in denied.messages)

    allow_log = InMemoryEventLog()
    allowed = await ToolLoopHarness(
        inference=_script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        event_log=allow_log,
        access=InMemoryAccessControl(event_log=allow_log, policy=with_write),
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
    denied = await ToolLoopHarness(
        inference=_script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        event_log=denied_log,
        access=InMemoryAccessControl(event_log=denied_log, policy=deny_policy),
    ).run(request.get("prompt", "write"))
    denied_ok = any("Permission denied" in (m.content or "") for m in denied.messages)

    allow_log = InMemoryEventLog()
    allowed = await ToolLoopHarness(
        inference=_script(),
        tools=registry,
        config=HarnessConfig(model="story", max_turns=4),
        event_log=allow_log,
        access=InMemoryAccessControl(event_log=allow_log, policy=allow_policy),
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
