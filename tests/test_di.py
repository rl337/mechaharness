"""Dependency injection: Config hooks and host-style subclassing."""

from __future__ import annotations

import pytest
from pyiv import get_injector

from mechaharness.config import Settings
from mechaharness.core.types import ChatMessage, Role, ToolCall
from mechaharness.di import MechaHarnessConfig, SettingsConfig
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.base import InferenceStrategy
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
