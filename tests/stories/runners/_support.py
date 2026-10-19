"""Shared helpers for story runners."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from mechaharness.core.access import (
    GraphExecute,
)
from mechaharness.core.environment import (
    InferenceEnvironment,
)
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.graph_executor import (
    GraphExecutor,
    GraphNodeRunnerRegistry,
)
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.judge import (
    ChoiceOption,
    ChoiceQuestion,
    NoulQuestion,
    ScoreAnchor,
    ScoreQuestion,
)
from mechaharness.judgement_policy import (
    JudgementPolicy,
    JudgementThreshold,
)
from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase

StoryRunner = Callable[[StoryCase, StoryBackend], Awaitable[None]]


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
