"""pyiv Config for MechaHarness.

``MechaHarnessConfig.configure()`` binds interfaces from overridable class
hooks. Hosts subclass and override ``get_inference_class`` /
``get_harness_class``. ``SettingsConfig`` resolves those classes from string
maps (the OpenAPI/CLI configuration path).

Hosts must wire via Config + ``get_injector`` (or the OpenAPI ``run()``
facade). Manual harness construction is not a supported host path.
"""

from __future__ import annotations

import inspect
import sys
from typing import Any, ForwardRef, get_type_hints

from eval_type_backport import eval_type_backport
from pyiv import Config, get_injector
from pyiv.injector import Injector

from mechaharness.api_connection import APIConnectionConfig, SimpleHttpConnectionConfig
from mechaharness.advisor import Advisor, AdvisorPolicy, DefaultAdvisorPolicy, RejectAdvisor
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.config import Settings
from mechaharness.context_provider import ContextProviderRegistry
from mechaharness.core.access import (
    AccessControl,
    AccessPolicy,
    CostAccountant,
    GrantPolicyLike,
    InMemoryAccessControl,
    InMemoryCostAccountant,
)
from mechaharness.core.completer import Completer
from mechaharness.core.environment import InferenceEnvironment, NoOpInferenceEnvironment
from mechaharness.core.events import EventLog, default_event_log
from mechaharness.delegation_policy import DefaultDelegationPolicy, DelegationPolicy
from mechaharness.graph_executor import (
    DefaultGraphFailurePolicy,
    GraphEscalation,
    GraphExecutor,
    GraphFailurePolicy,
    GraphNodeRunnerRegistry,
    RejectGraphEscalation,
)
from mechaharness.graph_template import GraphTemplateRegistry, default_graph_templates
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.families import AnthropicToolsHarness, OpenAIToolsHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.harness.react import ReactHarness
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.anthropic import AnthropicStrategy
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.judge import JudgeProvider
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.inference.openai_compat import OpenAICompatStrategy
from mechaharness.inference.systemone import SystemOneJudgeProvider
from mechaharness.linkage_resolver import DefaultLinkageResolver, LinkageResolver
from mechaharness.operation_registry import OperationRegistry, default_operations
from mechaharness.tools.base import ToolRegistry
from mechaharness.verification_policy import DefaultVerificationPolicy, VerificationPolicy

_INFERENCE_DEFAULTS: dict[str, dict[str, Any]] = {
    "openai": {"base_url": "https://api.openai.com/v1"},
    "openai_compat": {"base_url": "https://api.openai.com/v1"},
    "lmstudio": {"base_url": "http://localhost:1234/v1", "api_key": "lm-studio"},
    "vllm": {"base_url": "http://localhost:8000/v1"},
    "junespark": {
        # Hosts set MECHA_BASE_URL / Settings.base_url; no LAN default in the library.
        "api_key": "junespark",
    },
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


def _expose_ctor_type_hints(cls: type) -> None:
    """Resolve PEP 563 string annotations so pyiv can constructor-inject.

    pyiv ≥ 0.4 reads ``inspect.signature`` annotations as-is; with
    ``from __future__ import annotations`` those are strings. On Python 3.9,
    ``X | Y`` also needs ``eval_type_backport``. Rewriting
    ``__init__.__annotations__`` exposes real types for the injector.
    """
    init = getattr(cls, "__init__", None)
    if init is None or init is object.__init__:
        return
    init_module = getattr(init, "__module__", cls.__module__)
    globalns = getattr(sys.modules.get(init_module), "__dict__", {})
    try:
        hints = get_type_hints(init, globalns=globalns)
    except (TypeError, NameError):
        hints = {}
        for name, param in inspect.signature(init).parameters.items():
            if name == "self" or param.annotation is inspect.Parameter.empty:
                continue
            ann: Any = param.annotation
            if isinstance(ann, str):
                ann = ForwardRef(ann)
            try:
                hints[name] = eval_type_backport(ann, globalns, globalns)
            except Exception:  # noqa: BLE001
                continue
    if hints:
        init.__annotations__.update(hints)


class MechaHarnessConfig(Config):
    """Template-method pyiv Config. Override the ``get_*_class`` hooks."""

    def configure(self) -> None:
        event_log = self.get_event_log()
        self.register_instance(Settings, self.get_settings())
        self.register_instance(HarnessConfig, self.get_harness_config())
        self.register_instance(ToolRegistry, self.get_tools())
        self.register_instance(EventLog, event_log)
        self.register_instance(AccessControl, self.get_access_control())
        self.register_instance(CostAccountant, self.get_cost_accountant())
        self.register_instance(InferenceEnvironment, self.get_inference_environment())
        self.register_instance(APIConnectionConfig, self.get_judge_connection())
        self.register_instance(JudgeProvider, self.get_judge_provider())
        self.register_instance(GraphNodeRunnerRegistry, self.get_node_runner_registry())
        self.register_instance(GraphFailurePolicy, self.get_graph_failure_policy())
        self.register_instance(GraphEscalation, self.get_graph_escalation())
        self.register_instance(OperationRegistry, self.get_operation_registry())
        self.register_instance(LinkageResolver, self.get_linkage_resolver())
        self.register_instance(VerificationPolicy, self.get_verification_policy())
        self.register_instance(DelegationPolicy, self.get_delegation_policy())
        self.register_instance(AdvisorPolicy, self.get_advisor_policy())
        self.register_instance(Advisor, self.get_advisor())
        self.register_instance(GraphTemplateRegistry, self.get_graph_template_registry())
        self.register_instance(ContextProviderRegistry, self.get_context_provider_registry())
        self.register_instance(CapabilityEnvelope, self.get_capability_envelope())

        inference_cls = self.get_inference_class()
        harness_cls = self.get_harness_class()
        graph_executor_cls = self.get_graph_executor_class()
        _expose_ctor_type_hints(inference_cls)
        _expose_ctor_type_hints(harness_cls)
        _expose_ctor_type_hints(AbstractHarness)
        _expose_ctor_type_hints(graph_executor_cls)
        _expose_ctor_type_hints(GraphExecutor)

        self.register(InferenceStrategy, inference_cls, singleton=True)

        def make_completer(injector: Injector) -> Completer:
            strategy = injector.inject(InferenceStrategy)
            assert isinstance(strategy, Completer)
            return strategy

        self.register(Completer, make_completer, singleton=True)
        self.register(AbstractHarness, harness_cls, singleton=True)
        self.register(GraphExecutor, graph_executor_cls, singleton=True)

    def get_settings(self) -> Settings:
        """Settings instance registered for this config (override to customize)."""
        return Settings()

    def get_event_log(self) -> EventLog:
        """Shared ``EventLog`` for harnesses and access/cost policies."""
        existing = getattr(self, "_event_log", None)
        if existing is None:
            existing = default_event_log()
            self._event_log = existing
        return existing

    def get_access_control(self) -> AccessControl:
        """Deny-by-default access control bound into harnesses."""
        existing = getattr(self, "_access_control", None)
        if existing is None:
            existing = InMemoryAccessControl(
                event_log=self.get_event_log(),
                policy=self.get_access_policy(),
            )
            self._access_control = existing
        return existing

    def get_access_policy(self) -> GrantPolicyLike:
        """Grant policy for harness tool gates.

        Default wraps :meth:`get_grants` in an :class:`AccessPolicy`. Hosts
        override to return a :class:`CompoundPolicy` of reusable grant sets.
        Not :class:`~mechaharness.judgement_policy.JudgementPolicy`.
        """
        return AccessPolicy(grants=self.get_grants())

    def get_grants(self) -> list[object]:
        """Deny-by-default grant list. Hosts override; unknown namespaced keys ok."""
        return []

    def get_inference_environment(self) -> InferenceEnvironment:
        """Host probe for the active inference profile (default: no-op)."""
        return NoOpInferenceEnvironment()

    def get_judge_connection(self) -> APIConnectionConfig:
        """HTTP connection for the judge lane (override for OAuth, etc.)."""
        existing = getattr(self, "_judge_connection", None)
        if existing is None:
            existing = SimpleHttpConnectionConfig.for_judge()
            self._judge_connection = existing
        return existing

    def get_judge_provider(self) -> JudgeProvider:
        """Judge backend (default: System One over ``get_judge_connection()``)."""
        return SystemOneJudgeProvider(connection=self.get_judge_connection())

    def include_subagent_tools(self) -> bool:
        """When True, parent harnesses get list_subagents / get_subagent_events."""
        return False

    def get_cost_accountant(self) -> CostAccountant:
        """Ledger used to price inference and tool invocations."""
        return InMemoryCostAccountant(event_log=self.get_event_log())

    def get_inference_class(self) -> type[InferenceStrategy]:
        """Required override: class bound to ``InferenceStrategy``."""
        raise NotImplementedError

    def get_harness_class(self) -> type[AbstractHarness]:
        """Required override: class bound to ``AbstractHarness``."""
        raise NotImplementedError

    def get_harness_config(self) -> HarnessConfig:
        """Build ``HarnessConfig`` from ``get_settings()``."""
        settings = self.get_settings()
        return HarnessConfig(
            model=settings.model,
            system_prompt=settings.system_prompt,
            max_turns=settings.max_turns,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            subagent_tools=self.include_subagent_tools(),
        )

    def get_tools(self) -> ToolRegistry:
        """Tools available to the harness (default: empty registry)."""
        return ToolRegistry()

    def get_graph_executor_class(self) -> type[GraphExecutor]:
        """Class bound to ``GraphExecutor`` (override to specialize)."""
        return GraphExecutor

    def get_node_runner_registry(self) -> GraphNodeRunnerRegistry:
        """Node-kind runners for the graph executor (default: empty)."""
        existing = getattr(self, "_node_runner_registry", None)
        if existing is None:
            existing = GraphNodeRunnerRegistry()
            self._node_runner_registry = existing
        return existing

    def get_graph_failure_policy(self) -> GraphFailurePolicy:
        """Retry / escalate / fail policy for graph node attempts."""
        return DefaultGraphFailurePolicy()

    def get_graph_escalation(self) -> GraphEscalation:
        """Escalation hook after retries are exhausted (default: reject)."""
        return RejectGraphEscalation()

    def get_operation_registry(self) -> OperationRegistry:
        """Shared operation contracts for linkage / compilers."""
        existing = getattr(self, "_operation_registry", None)
        if existing is None:
            existing = default_operations()
            self._operation_registry = existing
        return existing

    def get_linkage_resolver(self) -> LinkageResolver:
        """Pre-execution graph wiring validator."""
        return DefaultLinkageResolver(
            runners=self.get_node_runner_registry(),
            access=self.get_access_control(),
            environment=self.get_inference_environment(),
            operations=self.get_operation_registry(),
        )

    def get_verification_policy(self) -> VerificationPolicy:
        """Selects and runs verification for graph/outcome gates."""
        return DefaultVerificationPolicy()

    def get_delegation_policy(self) -> DelegationPolicy:
        """Chooses inline versus child/subgraph execution."""
        return DefaultDelegationPolicy()

    def get_advisor_policy(self) -> AdvisorPolicy:
        """Sparse advisor consultation policy."""
        return DefaultAdvisorPolicy()

    def get_advisor(self) -> Advisor:
        """Non-binding advisor (default: unavailable / reject)."""
        return RejectAdvisor()

    def get_graph_template_registry(self) -> GraphTemplateRegistry:
        """Library-owned parameterized graph templates."""
        return default_graph_templates()

    def get_context_provider_registry(self) -> ContextProviderRegistry:
        """Host context providers (June KG/docs bind here)."""
        return ContextProviderRegistry()

    def get_capability_envelope(self) -> CapabilityEnvelope:
        """Default run envelope from configured grants."""
        return CapabilityEnvelope.from_grants(self.get_grants())

    def inference_classes(self) -> dict[str, type[InferenceStrategy]]:
        """Named backend map. Hosts merge via ``super().inference_classes()``."""
        return {
            "openai": OpenAICompatStrategy,
            "openai_compat": OpenAICompatStrategy,
            "lmstudio": OpenAICompatStrategy,
            "vllm": OpenAICompatStrategy,
            "junespark": OpenAICompatStrategy,
            "ollama": OpenAICompatStrategy,
            "anthropic": AnthropicStrategy,
            "mock": MockInferenceStrategy,
        }

    def harness_classes(self) -> dict[str, type[AbstractHarness]]:
        """Named harness family map. Hosts merge via ``super().harness_classes()``."""
        return {
            "pass_through": PassThroughHarness,
            "tool_loop": ToolLoopHarness,
            "react": ReactHarness,
            "openai_tools": OpenAIToolsHarness,
            "anthropic_tools": AnthropicToolsHarness,
        }


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
    """Sorted names from the default ``SettingsConfig.inference_classes()`` map."""
    return sorted(SettingsConfig().inference_classes())


def list_harness_families() -> list[str]:
    """Sorted names from the default ``SettingsConfig.harness_classes()`` map."""
    return sorted(SettingsConfig().harness_classes())


def build_injector(
    settings: Settings | None = None,
    tools: ToolRegistry | None = None,
) -> Injector:
    """Build a pyiv injector from ``SettingsConfig`` (CLI/API/non-DI path)."""
    return get_injector(SettingsConfig(settings=settings, tools=tools))
