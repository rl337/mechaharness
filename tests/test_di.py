"""Dependency injection: Config hooks and host-style subclassing."""

from __future__ import annotations

from typing import Annotated

import pytest
from pyiv import CreationError
from pyiv.key import Key, Matched, Named

from mechaharness.config import Settings
from mechaharness.core.completer import Completer
from mechaharness.core.types import ChatMessage, Role, ToolCall
from mechaharness.di import (
    MechaHarnessConfig,
    SettingsConfig,
    _expose_ctor_type_hints,
    get_injector,
)
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.tools.base import ToolRegistry
from tests.fakes import ScriptedInference


@pytest.fixture
def tools() -> ToolRegistry:
    registry = ToolRegistry()

    @registry.tool(
        description="Add two numbers",
        parameters={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
    )
    def add(a: float, b: float) -> str:
        return str(a + b)

    return registry


class ScriptedConfig(MechaHarnessConfig):
    def __init__(
        self,
        inference: InferenceStrategy,
        tools: ToolRegistry,
        harness_config: HarnessConfig,
        harness_cls: type[AbstractHarness] = ToolLoopHarness,
    ) -> None:
        self._inference = inference
        self._tools = tools
        self._harness_config = harness_config
        self._harness_cls = harness_cls
        super().__init__()

    def get_inference_class(self) -> type[InferenceStrategy]:
        return type(self._inference)

    def get_harness_class(self) -> type[AbstractHarness]:
        return self._harness_cls

    def get_tools(self) -> ToolRegistry:
        return self._tools

    def get_harness_config(self) -> HarnessConfig:
        return self._harness_config

    def configure(self) -> None:
        super().configure()
        self.register_instance(InferenceStrategy, self._inference)


@pytest.mark.asyncio
async def test_inject_harness_runs_scripted_loop(tools: ToolRegistry) -> None:
    inference = ScriptedInference(
        [
            ChatMessage(
                role=Role.ASSISTANT,
                content=None,
                tool_calls=[ToolCall(id="1", name="add", arguments={"a": 2, "b": 3})],
            ),
            ChatMessage(role=Role.ASSISTANT, content="The sum is 5."),
        ]
    )
    config = ScriptedConfig(
        inference,
        tools,
        HarnessConfig(model="test-model", max_turns=4),
    )
    injector = get_injector(config)
    harness = injector.inject(AbstractHarness)
    result = await harness.run("What is 2+3?")
    assert result.final_text == "The sum is 5."
    assert result.turns == 2


@pytest.mark.asyncio
async def test_host_overrides_get_inference_class(tools: ToolRegistry) -> None:
    inference = ScriptedInference([ChatMessage(role=Role.ASSISTANT, content="injected")])
    config = ScriptedConfig(inference, tools, HarnessConfig(model="m"))
    injector = get_injector(config)
    assert injector.inject(InferenceStrategy) is inference
    harness = injector.inject(AbstractHarness)
    result = await harness.run("hi")
    assert result.final_text == "injected"


def test_base_config_requires_class_hooks() -> None:
    with pytest.raises(NotImplementedError):
        MechaHarnessConfig()


def test_settings_config_unknown_family() -> None:
    with pytest.raises(KeyError, match="Unknown harness family"):
        SettingsConfig(Settings(harness_family="not-a-family"))


class _CodeFlavorCompleter(MockInferenceStrategy):
    name = "code-flavor"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        self.flavor = "code"


class _DeepFlavorCompleter(MockInferenceStrategy):
    name = "deep-flavor"

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        self.flavor = "deep"


class _FlavorHostHarness:
    """Minimal host type that selects Completer flavors via Annotated."""

    def __init__(
        self,
        code: Annotated[Completer, Named(["reason", "code"])],
        deep: Annotated[
            Completer,
            Matched(required=["reason"], prefer=["deep"]),
        ],
        optional_missing: Annotated[
            Completer | None,
            Matched(required=["reason", "summarize"]),
        ] = None,
    ) -> None:
        self.code = code
        self.deep = deep
        self.optional_missing = optional_missing


class FlavorConfig(MechaHarnessConfig):
    def get_inference_class(self) -> type[InferenceStrategy]:
        return MockInferenceStrategy

    def get_harness_class(self) -> type[AbstractHarness]:
        return ToolLoopHarness

    def completer_bindings(self):
        return [
            (Named(["reason"], default=True), self.get_inference_class()),
            (Named(["reason", "code"]), _CodeFlavorCompleter),
            (Named(["reason", "deep"]), _DeepFlavorCompleter),
        ]

    def configure(self) -> None:
        super().configure()
        _expose_ctor_type_hints(_FlavorHostHarness)
        self.register(_FlavorHostHarness, _FlavorHostHarness)


def test_default_completer_aliases_inference_strategy() -> None:
    injector = get_injector(FlavorConfig)
    completer = injector.inject(Completer)
    strategy = injector.inject(InferenceStrategy)
    assert completer is strategy
    assert isinstance(completer, MockInferenceStrategy)
    named = injector.inject(Key(Completer, Named(["reason"], default=True)))
    assert named is completer


def test_annotated_named_and_matched_completer_flavors() -> None:
    host = get_injector(FlavorConfig).inject(_FlavorHostHarness)
    assert isinstance(host.code, _CodeFlavorCompleter)
    assert host.code.flavor == "code"
    assert isinstance(host.deep, _DeepFlavorCompleter)
    assert host.deep.flavor == "deep"
    assert host.optional_missing is None


def test_matched_missing_tags_raises_creation_error() -> None:
    injector = get_injector(FlavorConfig)
    with pytest.raises(CreationError, match="satisfies|No Named"):
        injector.inject(Key(Completer, Matched(required=["reason", "summarize"])))


def test_matched_ambiguous_tags_raises_creation_error() -> None:
    class AmbiguousConfig(MechaHarnessConfig):
        def get_inference_class(self) -> type[InferenceStrategy]:
            return MockInferenceStrategy

        def get_harness_class(self) -> type[AbstractHarness]:
            return ToolLoopHarness

        def completer_bindings(self):
            return [
                (Named(["reason"], default=True), self.get_inference_class()),
                (Named(["reason", "deep", "a"]), _CodeFlavorCompleter),
                (Named(["reason", "deep", "b"]), _DeepFlavorCompleter),
            ]

    injector = get_injector(AmbiguousConfig)
    with pytest.raises(CreationError, match="Ambiguous"):
        injector.inject(Key(Completer, Matched(required=["reason", "deep"])))


def test_expose_ctor_type_hints_preserves_named_annotation() -> None:
    class Sample:
        def __init__(
            self,
            inference: Annotated[Completer, Named(["reason", "code"])],
        ) -> None:
            self.inference = inference

    _expose_ctor_type_hints(Sample)
    ann = Sample.__init__.__annotations__["inference"]
    assert getattr(ann, "__metadata__", None)
    assert isinstance(ann.__metadata__[0], Named)


def test_expose_normalizes_pep604_optional_named() -> None:
    """``Annotated[T | None, Q]`` must become Optional[Annotated[T, Q]] for pyiv."""
    from typing import Optional, Union, get_args, get_origin

    from mechaharness.di import _normalize_injection_annotation

    # typing.Union stands in for PEP 604 ``T | None`` (UnionType on 3.10+).
    raw = Annotated[Union[Completer, None], Matched(required=["reason", "summarize"])]
    normalized = _normalize_injection_annotation(raw)
    assert get_origin(normalized) in (Optional, Union)
    args = [a for a in get_args(normalized) if a is not type(None)]
    assert len(args) == 1
    inner = args[0]
    assert get_origin(inner) is Annotated or getattr(
        get_origin(inner), "__name__", None
    ) == "Annotated"
    assert get_args(inner)[0] is Completer
    assert isinstance(get_args(inner)[1], Matched)

    _expose_ctor_type_hints(_FlavorHostHarness)
    exposed = _FlavorHostHarness.__init__.__annotations__["optional_missing"]
    assert get_origin(exposed) in (Optional, Union)
