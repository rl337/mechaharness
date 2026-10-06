"""pyiv Config for MechaHarness.

``MechaHarnessConfig.configure()`` binds interfaces from overridable class
hooks. Hosts subclass and override ``get_inference_class`` /
``get_harness_class``. ``SettingsConfig`` resolves those classes from string
maps (the OpenAPI/CLI configuration path).

Same-lane Completer / JudgeProvider **flavors** are additional ``Named``
bindings from ``completer_bindings()`` / ``judge_bindings()``. Host harnesses
select them with ``Annotated[T, Named(...)]`` / ``Matched(...)`` on
constructors (not field injection).

Hosts must wire via Config + ``get_injector`` (or the OpenAPI ``run()``
facade). Manual harness construction is not a supported host path.
Prefer ``mechaharness.di.get_injector`` so Named default Completer aliases
share identity with ``InferenceStrategy``.
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable, Sequence
from typing import (
    Annotated,
    Any,
    ForwardRef,
    Optional,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from eval_type_backport import eval_type_backport
from pyiv import Config, Stage
from pyiv.injector import Injector
from pyiv.injector import get_injector as _pyiv_get_injector
from pyiv.key import Key, Named
from pyiv.provider import InstanceProvider
from pyiv.scope import SingletonScope

from mechaharness.advisor import Advisor, AdvisorPolicy, DefaultAdvisorPolicy, RejectAdvisor
from mechaharness.api_connection import APIConnectionConfig, SimpleHttpConnectionConfig
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.checkpoint_store import CheckpointStore, EventLogCheckpointStore
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
from mechaharness.core.environment import (
    LANE_JUDGE,
    LANE_REASON,
    InferenceEnvironment,
    NoOpInferenceEnvironment,
)
from mechaharness.core.events import EventLog, default_event_log
from mechaharness.delegation_policy import DefaultDelegationPolicy, DelegationPolicy
from mechaharness.external_effect import CrashProbe, NoopCrashProbe
from mechaharness.graph import GraphStore
from mechaharness.graph_executor import (
    DefaultGraphFailurePolicy,
    GraphEscalation,
    GraphExecutor,
    GraphFailurePolicy,
    GraphNodeRunnerRegistry,
    RejectGraphEscalation,
)
from mechaharness.graph_templates import GraphTemplateRegistry, default_graph_templates
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
from mechaharness.lifecycle_extension import (
    LifecycleExtensionRegistry,
    empty_lifecycle_extension_registry,
)
from mechaharness.linkage_resolver import DefaultLinkageResolver, LinkageResolver
from mechaharness.operation_registry import OperationRegistry, default_operations
from mechaharness.tools.base import ToolRegistry
from mechaharness.verification_policy import DefaultVerificationPolicy, VerificationPolicy

CompleterBinding = tuple[
    Named, Union[type, Completer, Callable[..., Completer]]
]
JudgeBinding = tuple[
    Named, Union[type, JudgeProvider, Callable[..., JudgeProvider]]
]


class _BoundInjectorProvider:
    """Provider that resolves a type once the injector is bound."""

    def __init__(self, target: type) -> None:
        self._target = target
        self._injector: Injector | None = None

    def bind(self, injector: Injector) -> None:
        self._injector = injector

    def get(self) -> Any:
        if self._injector is None:
            raise RuntimeError(
                "Named binding resolved before injector bind; use "
                "mechaharness.di.get_injector or inject Completer / "
                "InferenceStrategy first"
            )
        return self._injector.inject(self._target)


class _BoundFactoryProvider:
    """Provider wrapping a zero-arg or ``injector=`` factory after bind."""

    def __init__(self, factory: Callable[..., Any]) -> None:
        self._factory = factory
        self._injector: Injector | None = None

    def bind(self, injector: Injector) -> None:
        self._injector = injector

    def get(self) -> Any:
        if self._injector is None:
            raise RuntimeError(
                "Named factory binding resolved before injector bind; use "
                "mechaharness.di.get_injector"
            )
        sig = inspect.signature(self._factory)
        if "injector" in sig.parameters:
            return self._factory(injector=self._injector)
        return self._factory()


def _normalize_named_bindings(
    bindings: Sequence[tuple[Named, Any]],
    *,
    hook: str,
) -> list[tuple[Named, Any]]:
    items = list(bindings)
    if not items:
        raise ValueError(f"{hook}() must return at least one binding")
    defaults = [named for named, _ in items if named.default]
    if len(items) == 1 and not defaults:
        named, impl = items[0]
        items = [(Named(sorted(named.tags), default=True), impl)]
        defaults = [items[0][0]]
    if len(defaults) != 1:
        raise ValueError(
            f"{hook}() requires exactly one Named(..., default=True) "
            f"or a single binding; got {len(defaults)} defaults among "
            f"{len(items)} bindings"
        )
    return items

_INFERENCE_DEFAULTS: dict[str, dict[str, Any]] = {
    "openai": {"base_url": "https://api.openai.com/v1"},
    "openai_compat": {"base_url": "https://api.openai.com/v1"},
    "lmstudio": {"base_url": "http://localhost:1234/v1", "api_key": "lm-studio"},
    "vllm": {"base_url": "http://localhost:8000/v1"},
    "openai_local": {
        # Hosts set MECHA_BASE_URL / Settings.base_url; no localhost default.
        "api_key": "local",
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


def _is_union_origin(origin: Any) -> bool:
    """True for ``typing.Union`` and PEP 604 ``types.UnionType`` (3.10+)."""
    if origin is Union:
        return True
    return getattr(origin, "__name__", None) == "UnionType"


def _normalize_injection_annotation(annotation: Any) -> Any:
    """Rewrite PEP 604 optionals so pyiv 0.4 can peel Named/Matched.

    pyiv's ``is_optional_type`` only recognizes ``typing.Union`` / ``Optional``.
    On Python 3.10+, ``get_type_hints`` may leave ``T | None`` as
    ``types.UnionType``, so ``Annotated[T | None, Named(...)]`` fails with
    "requires a concrete type". Prefer ``Optional[Annotated[T, Q]]``.
    """
    origin = get_origin(annotation)
    if _is_union_origin(origin):
        args = get_args(annotation)
        if len(args) == 2 and type(None) in args:
            non_none = args[0] if args[1] is type(None) else args[1]
            return Optional[_normalize_injection_annotation(non_none)]
        return annotation
    if origin is Annotated or getattr(origin, "__name__", None) == "Annotated":
        args = get_args(annotation)
        if not args:
            return annotation
        base, metas = args[0], args[1:]
        base_origin = get_origin(base)
        if _is_union_origin(base_origin):
            b_args = get_args(base)
            if len(b_args) == 2 and type(None) in b_args:
                inner = b_args[0] if b_args[1] is type(None) else b_args[1]
                return Optional[Annotated[(inner, *metas)]]
        normalized_base = _normalize_injection_annotation(base)
        if normalized_base is base:
            return annotation
        return Annotated[(normalized_base, *metas)]
    return annotation


def _expose_ctor_type_hints(cls: type) -> None:
    """Resolve PEP 563 string annotations so pyiv can constructor-inject.

    pyiv ≥ 0.4 reads ``inspect.signature`` annotations as-is; with
    ``from __future__ import annotations`` those are strings. On Python 3.9,
    ``X | Y`` also needs ``eval_type_backport``. Rewriting
    ``__init__.__annotations__`` exposes real types for the injector.

    Uses ``include_extras=True`` so ``Annotated[T, Named|Matched]`` metadata
    survives for qualified constructor injection. Normalizes ``T | None``
    optionals for pyiv compatibility on 3.10+.
    """
    init = getattr(cls, "__init__", None)
    if init is None or init is object.__init__:
        return
    init_module = getattr(init, "__module__", cls.__module__)
    globalns = getattr(sys.modules.get(init_module), "__dict__", {})
    try:
        hints = get_type_hints(init, globalns=globalns, include_extras=True)
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
        init.__annotations__.update(
            {name: _normalize_injection_annotation(ann) for name, ann in hints.items()}
        )


class MechaHarnessConfig(Config):
    """Template-method pyiv Config. Override the ``get_*_class`` hooks."""

    def __init__(self) -> None:
        self._mh_bound_providers: list[Any] = []
        super().__init__()  # type: ignore[no-untyped-call]

    def _bind_mh_providers(self, injector: Injector) -> None:
        for provider in self._mh_bound_providers:
            provider.bind(injector)

    def _implementation_for_key(
        self,
        impl: Any,
        *,
        alias_to: type | None = None,
    ) -> Any:
        """Map a binding value to a ``register_key`` implementation."""
        if alias_to is not None:
            alias_provider = _BoundInjectorProvider(alias_to)
            self._mh_bound_providers.append(alias_provider)
            return alias_provider
        if isinstance(impl, type):
            return impl
        if hasattr(impl, "get") and callable(impl.get) and not isinstance(impl, type):
            return impl
        if callable(impl):
            factory_provider = _BoundFactoryProvider(impl)
            self._mh_bound_providers.append(factory_provider)
            return factory_provider
        return InstanceProvider(impl)

    def _register_named_bindings(
        self,
        abstract: type,
        bindings: Sequence[tuple[Named, Any]],
        *,
        hook: str,
        alias_default_to: type | None = None,
        default_impl: Any | None = None,
    ) -> None:
        normalized = _normalize_named_bindings(bindings, hook=hook)
        scope = SingletonScope()  # type: ignore[no-untyped-call]
        for named, impl in normalized:
            if isinstance(impl, type):
                _expose_ctor_type_hints(impl)
            alias_to = None
            if (
                named.default
                and alias_default_to is not None
                and default_impl is not None
                and impl is default_impl
            ):
                alias_to = alias_default_to
            key_impl = self._implementation_for_key(impl, alias_to=alias_to)
            self.register_key(Key(abstract, named), key_impl, scope=scope)

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
        self.register_instance(
            LifecycleExtensionRegistry, self.get_lifecycle_extension_registry()
        )
        self.register_instance(CheckpointStore, self.get_checkpoint_store())
        self.register_instance(CrashProbe, self.get_crash_probe())

        inference_cls = self.get_inference_class()
        harness_cls = self.get_harness_class()
        graph_executor_cls = self.get_graph_executor_class()
        _expose_ctor_type_hints(inference_cls)
        _expose_ctor_type_hints(harness_cls)
        _expose_ctor_type_hints(AbstractHarness)
        _expose_ctor_type_hints(graph_executor_cls)
        _expose_ctor_type_hints(GraphExecutor)

        def make_inference(injector: Injector) -> InferenceStrategy:
            self._bind_mh_providers(injector)
            return cast(
                InferenceStrategy,
                injector._instantiate(inference_cls),  # noqa: SLF001
            )

        self.register(InferenceStrategy, make_inference, singleton=True)

        def make_completer(injector: Injector) -> Completer:
            self._bind_mh_providers(injector)
            strategy = injector.inject(InferenceStrategy)
            assert isinstance(strategy, Completer)
            return strategy

        # Thin alias so bare inject(Completer) shares identity with InferenceStrategy
        # (including host register_instance overrides). Named default also aliases.
        self.register(Completer, make_completer, singleton=True)
        self._register_named_bindings(
            Completer,
            self.completer_bindings(),
            hook="completer_bindings",
            alias_default_to=InferenceStrategy,
            default_impl=inference_cls,
        )

        judge_bindings = self.judge_bindings()
        self._register_named_bindings(
            JudgeProvider,
            judge_bindings,
            hook="judge_bindings",
        )
        default_judge_named = next(
            named
            for named, _ in _normalize_named_bindings(
                judge_bindings, hook="judge_bindings"
            )
            if named.default
        )

        def make_judge(injector: Injector) -> JudgeProvider:
            self._bind_mh_providers(injector)
            return cast(
                JudgeProvider,
                injector.inject(Key(JudgeProvider, default_judge_named)),
            )

        self.register(JudgeProvider, make_judge, singleton=True)

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

    def completer_bindings(self) -> Sequence[CompleterBinding]:
        """Named Completer flavors (lane + host tags).

        Default: ``Named([reason], default=True)`` → ``get_inference_class()``,
        aliased to the ``InferenceStrategy`` singleton so bare
        ``inject(Completer)`` and the Named default share identity.

        Hosts append flavors (e.g. ``Named(["reason", "code", "deep"])``).
        Exactly one ``default=True`` (or a single binding) is required.
        """
        return [(Named([LANE_REASON], default=True), self.get_inference_class())]

    def judge_bindings(self) -> Sequence[JudgeBinding]:
        """Named JudgeProvider flavors.

        Default: ``Named([judge], default=True)`` → ``get_judge_provider()``.
        Hosts append flavors (e.g. ``Named(["judge", "heavy"])``).
        Exactly one ``default=True`` (or a single binding) is required.
        """
        return [(Named([LANE_JUDGE], default=True), self.get_judge_provider())]

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

    def get_checkpoint_store(self) -> CheckpointStore:
        """Authoritative graph/effect persistence (default: ephemeral EventLog).

        Override to bind the SQLite reference backend (or a host store)::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from mechaharness.checkpoint_store import CheckpointStore
            >>> from mechaharness.di import MechaHarnessConfig, get_injector
            >>> from mechaharness.harness.pass_through import PassThroughHarness
            >>> from mechaharness.inference.mock import MockInferenceStrategy
            >>> from mechaharness.sqlite_checkpoint_store import SqliteCheckpointStore
            >>> path = Path(tempfile.mkdtemp()) / "runs.sqlite"
            >>> class DurableConfig(MechaHarnessConfig):
            ...     def get_inference_class(self):
            ...         return MockInferenceStrategy
            ...     def get_harness_class(self):
            ...         return PassThroughHarness
            ...     def get_checkpoint_store(self):
            ...         return SqliteCheckpointStore(path)
            >>> store = get_injector(DurableConfig()).inject(CheckpointStore)
            >>> store.durability
            'durable'
        """
        existing = getattr(self, "_checkpoint_store", None)
        if existing is None:
            event_log = self.get_event_log()
            existing = EventLogCheckpointStore(
                GraphStore(event_log, agent_id="graph"),
                event_log=event_log,
                agent_id="graph",
            )
            self._checkpoint_store = existing
        return existing

    def get_crash_probe(self) -> CrashProbe:
        """Optional crash-injection probe (default: never crash)."""
        return NoopCrashProbe()

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
        """Host context providers (document/KG adapters bind here)."""
        return ContextProviderRegistry()

    def get_capability_envelope(self) -> CapabilityEnvelope:
        """Default run envelope from configured grants."""
        return CapabilityEnvelope.from_grants(self.get_grants())

    def get_lifecycle_extension_registry(self) -> LifecycleExtensionRegistry:
        """Ordered lifecycle extensions (default: empty)."""
        return empty_lifecycle_extension_registry()

    def inference_classes(self) -> dict[str, type[InferenceStrategy]]:
        """Named backend map. Hosts merge via ``super().inference_classes()``."""
        return {
            "openai": OpenAICompatStrategy,
            "openai_compat": OpenAICompatStrategy,
            "lmstudio": OpenAICompatStrategy,
            "vllm": OpenAICompatStrategy,
            "openai_local": OpenAICompatStrategy,
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
        super().__init__()

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


def get_injector(
    config: type[Config] | Config,
    *,
    stage: Stage = Stage.DEVELOPMENT,
) -> Injector:
    """Create an injector and bind MechaHarness Named alias providers.

    Prefer this over ``pyiv.get_injector`` so default Completer Named bindings
    that alias ``InferenceStrategy`` resolve safely. Injecting ``Completer`` or
    ``InferenceStrategy`` first also binds aliases when using pyiv directly.
    """
    injector = _pyiv_get_injector(config, stage=stage)
    bind = getattr(injector._config, "_bind_mh_providers", None)  # noqa: SLF001
    if callable(bind):
        bind(injector)
    return injector


def build_injector(
    settings: Settings | None = None,
    tools: ToolRegistry | None = None,
) -> Injector:
    """Build a pyiv injector from ``SettingsConfig`` (CLI/API/non-DI path)."""
    return get_injector(SettingsConfig(settings=settings, tools=tools))
