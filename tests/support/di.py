"""Test helpers: build harnesses through pyiv Config (DI-only path)."""

from __future__ import annotations

from mechaharness.core.access import AccessPolicy, GrantPolicyLike
from mechaharness.core.completer import Completer
from mechaharness.core.events import EventLog
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.harness.base import AbstractHarness, HarnessConfig
from mechaharness.harness.tool_loop import ToolLoopHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.tools.base import ToolRegistry


class ScriptedHarnessConfig(MechaHarnessConfig):
    """Config that binds a pre-built inference Completer/strategy for tests."""

    def __init__(
        self,
        inference: Completer,
        *,
        tools: ToolRegistry | None = None,
        harness_config: HarnessConfig | None = None,
        harness_cls: type[AbstractHarness] = ToolLoopHarness,
        event_log: EventLog | None = None,
        access_policy: GrantPolicyLike | None = None,
        grants: list[object] | None = None,
        include_subagent_tools: bool = False,
        agent_id: str | None = None,
        parent_agent_id: str | None = None,
    ) -> None:
        self._inference = inference
        self._tools = tools if tools is not None else ToolRegistry()
        self._harness_config = harness_config or HarnessConfig(model="test")
        self._harness_cls = harness_cls
        self._provided_event_log = event_log
        self._access_policy = access_policy
        self._grants = grants
        self._include_subagent_tools = include_subagent_tools
        self._agent_id = agent_id
        self._parent_agent_id = parent_agent_id
        super().__init__()  # type: ignore[no-untyped-call]

    def get_inference_class(self) -> type[InferenceStrategy]:
        if isinstance(self._inference, InferenceStrategy):
            return type(self._inference)
        # Nested Completer (e.g. child harness): class bind is overridden in configure.
        from mechaharness.inference.mock import MockInferenceStrategy

        return MockInferenceStrategy

    def get_harness_class(self) -> type[AbstractHarness]:
        return self._harness_cls

    def get_tools(self) -> ToolRegistry:
        return self._tools

    def get_harness_config(self) -> HarnessConfig:
        cfg = self._harness_config
        if self._include_subagent_tools and not cfg.subagent_tools:
            return cfg.model_copy(update={"subagent_tools": True})
        return cfg

    def include_subagent_tools(self) -> bool:
        return self._include_subagent_tools or self._harness_config.subagent_tools

    def get_event_log(self) -> EventLog:
        if self._provided_event_log is not None:
            return self._provided_event_log
        return super().get_event_log()

    def get_access_policy(self) -> GrantPolicyLike:
        if self._access_policy is not None:
            return self._access_policy
        if self._grants is not None:
            return AccessPolicy(grants=self._grants)
        return super().get_access_policy()

    def configure(self) -> None:
        super().configure()
        if isinstance(self._inference, InferenceStrategy):
            self.register_instance(InferenceStrategy, self._inference)
        self.register_instance(Completer, self._inference)


def inject_harness(config: MechaHarnessConfig) -> AbstractHarness:
    """Inject ``AbstractHarness`` from a Config (optionally set agent ids)."""
    kwargs: dict[str, object] = {}
    if isinstance(config, ScriptedHarnessConfig):
        if config._agent_id is not None:
            kwargs["agent_id"] = config._agent_id
        if config._parent_agent_id is not None:
            kwargs["parent_agent_id"] = config._parent_agent_id
    return get_injector(config).inject(AbstractHarness, **kwargs)


def make_harness(
    inference: Completer,
    *,
    tools: ToolRegistry | None = None,
    config: HarnessConfig | None = None,
    harness_cls: type[AbstractHarness] = ToolLoopHarness,
    event_log: EventLog | None = None,
    access_policy: GrantPolicyLike | None = None,
    grants: list[object] | None = None,
    include_subagent_tools: bool = False,
    agent_id: str | None = None,
    parent_agent_id: str | None = None,
) -> AbstractHarness:
    """Build a harness via DI for unit/story tests."""
    return inject_harness(
        ScriptedHarnessConfig(
            inference,
            tools=tools,
            harness_config=config,
            harness_cls=harness_cls,
            event_log=event_log,
            access_policy=access_policy,
            grants=grants,
            include_subagent_tools=include_subagent_tools,
            agent_id=agent_id,
            parent_agent_id=parent_agent_id,
        )
    )
