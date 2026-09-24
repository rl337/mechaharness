"""Execute user-story kinds against static or live backends."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest
from pyiv import get_injector

from mechaharness.api_connection import SimpleHttpConnectionConfig
from mechaharness.config import Settings
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
from mechaharness.di import MechaHarnessConfig
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
