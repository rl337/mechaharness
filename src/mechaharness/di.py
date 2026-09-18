"""pyiv Config for MechaHarness.

``MechaHarnessConfig.configure()`` binds interfaces from overridable class
hooks. Hosts subclass and override ``get_inference_class`` /
``get_harness_class``. ``SettingsConfig`` resolves those classes from string
maps (the OpenAPI/CLI configuration path).
"""

from __future__ import annotations

from typing import Any

from pyiv import Config, get_injector
from pyiv.injector import Injector

from mechaharness.config import Settings
from mechaharness.core.access import (
    AccessControl,
    CostAccountant,
    InMemoryAccessControl,
    InMemoryCostAccountant,
)
from mechaharness.core.events import EventLog, default_event_log
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.families import AnthropicToolsHarness, OpenAIToolsHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.harness.react import ReactHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.anthropic import AnthropicStrategy
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.inference.openai_compat import OpenAICompatStrategy
from mechaharness.tools.base import ToolRegistry

_INFERENCE_DEFAULTS: dict[str, dict[str, Any]] = {
    "openai": {"base_url": "https://api.openai.com/v1"},
    "openai_compat": {"base_url": "https://api.openai.com/v1"},
    "lmstudio": {"base_url": "http://localhost:1234/v1", "api_key": "lm-studio"},
    "vllm": {"base_url": "http://localhost:8000/v1"},
    "ollama": {"base_url": "http://localhost:11434/v1", "api_key": "ollama"},
    "anthropic": {"base_url": "https://api.anthropic.com"},
}


def apply_backend_defaults(settings: Settings) -> Settings:
    """Fill ``base_url`` / ``api_key`` from the named backend when unset."""
    defaults = _INFERENCE_DEFAULTS.get(settings.inference_backend.lower(), {})
    updates: dict[str, Any] = {}
    if settings.base_url is None and "base_url" in defaults:
        updates["base_url"] = defaults["base_url"]
    if settings.api_key is None and "api_key" in defaults:
        updates["api_key"] = defaults["api_key"]
    return settings.model_copy(update=updates) if updates else settings


class MechaHarnessConfig(Config):
    """Template-method pyiv Config. Override the ``get_*_class`` hooks."""

    def configure(self) -> None:
        self.register_instance(Settings, self.get_settings())
        self.register_instance(HarnessConfig, self.get_harness_config())
        self.register_instance(ToolRegistry, self.get_tools())
        self.register_instance(EventLog, self.get_event_log())
        self.register_instance(AccessControl, self.get_access_control())
        self.register_instance(CostAccountant, self.get_cost_accountant())
        self._bind_inference()
        self._bind_harness()

    def get_settings(self) -> Settings:
        return Settings()

    def get_event_log(self) -> EventLog:
        existing = getattr(self, "_event_log", None)
        if existing is None:
            existing = default_event_log()
            self._event_log = existing
        return existing

    def get_access_control(self) -> AccessControl:
        existing = getattr(self, "_access_control", None)
        if existing is None:
            existing = InMemoryAccessControl(
                event_log=self.get_event_log(),
                grants=self.get_grants(),
            )
            self._access_control = existing
        return existing

    def get_grants(self) -> list[object]:
        """Deny-by-default grant list. Hosts override; unknown namespaced keys ok."""
        return []

    def get_cost_accountant(self) -> CostAccountant:
        existing = getattr(self, "_cost_accountant", None)
        if existing is None:
            existing = InMemoryCostAccountant(event_log=self.get_event_log())
            self._cost_accountant = existing
        return existing

    def get_inference_class(self) -> type[InferenceStrategy]:
        """Required override: class bound to ``InferenceStrategy``."""
        raise NotImplementedError

    def get_harness_class(self) -> type[AbstractHarness]:
        """Required override: class bound to ``AbstractHarness``."""
        raise NotImplementedError

    def get_harness_config(self) -> HarnessConfig:
        settings = self.get_settings()
        return HarnessConfig(
            model=settings.model,
            system_prompt=settings.system_prompt,
            max_turns=settings.max_turns,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )

    def get_tools(self) -> ToolRegistry:
        return ToolRegistry()

    def inference_classes(self) -> dict[str, type[InferenceStrategy]]:
        return {
            "openai": OpenAICompatStrategy,
            "openai_compat": OpenAICompatStrategy,
            "lmstudio": OpenAICompatStrategy,
            "vllm": OpenAICompatStrategy,
            "ollama": OpenAICompatStrategy,
            "anthropic": AnthropicStrategy,
            "mock": MockInferenceStrategy,
        }

    def harness_classes(self) -> dict[str, type[AbstractHarness]]:
        return {
            "pass_through": PassThroughHarness,
            "tool_loop": ToolLoopHarness,
            "react": ReactHarness,
            "openai_tools": OpenAIToolsHarness,
            "anthropic_tools": AnthropicToolsHarness,
        }

    def _bind_inference(self) -> None:
        inference_cls = self.get_inference_class()

        def make_inference() -> InferenceStrategy:
            return inference_cls(self.get_settings())  # type: ignore[call-arg]

        self.register(InferenceStrategy, make_inference)

    def _bind_harness(self) -> None:
        harness_cls = self.get_harness_class()

        def make_harness(injector: Injector) -> AbstractHarness:
            return harness_cls(
                inference=injector.inject(InferenceStrategy),
                tools=self.get_tools(),
                config=self.get_harness_config(),
                event_log=injector.inject(EventLog),
                access=injector.inject(AccessControl),
                cost=injector.inject(CostAccountant),
            )

        self.register(AbstractHarness, make_harness)


class SettingsConfig(MechaHarnessConfig):
    """Resolves inference/harness classes from ``Settings`` name maps."""

    def __init__(
        self,
        settings: Settings | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        self._provided_settings = settings
        self._provided_tools = tools
        self._resolved_settings: Settings | None = None
        super().__init__()  # type: ignore[no-untyped-call]

    def get_settings(self) -> Settings:
        if self._resolved_settings is None:
            self._resolved_settings = apply_backend_defaults(
                self._provided_settings or Settings()
            )
        return self._resolved_settings

    def get_tools(self) -> ToolRegistry:
        if self._provided_tools is not None:
            return self._provided_tools
        return _demo_tools()

    def get_inference_class(self) -> type[InferenceStrategy]:
        name = self.get_settings().inference_backend.lower()
        classes = self.inference_classes()
        try:
            return classes[name]
        except KeyError as exc:
            known = ", ".join(sorted(classes)) or "(none)"
            raise KeyError(f"Unknown inference backend {name!r}. Known: {known}") from exc

    def get_harness_class(self) -> type[AbstractHarness]:
        name = self.get_settings().harness_family.lower()
        classes = self.harness_classes()
        try:
            return classes[name]
        except KeyError as exc:
            known = ", ".join(sorted(classes)) or "(none)"
            raise KeyError(f"Unknown harness family {name!r}. Known: {known}") from exc


def _demo_tools() -> ToolRegistry:
    tools = ToolRegistry()

    @tools.tool(
        description="Echo text back. Useful as a smoke-test tool.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )
    def echo(text: str) -> str:
        return text

    @tools.tool(
        description="Add two numbers.",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
    )
    def add(a: float, b: float) -> str:
        return str(a + b)

    return tools


def list_inference_backends() -> list[str]:
    return sorted(SettingsConfig().inference_classes())


def list_harness_families() -> list[str]:
    return sorted(SettingsConfig().harness_classes())


def build_injector(
    settings: Settings | None = None,
    tools: ToolRegistry | None = None,
) -> Injector:
    return get_injector(SettingsConfig(settings=settings, tools=tools))
