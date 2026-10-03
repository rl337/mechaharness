"""Ordered lifecycle interception at declared execution boundaries (req 20).

EventLog remains append-only telemetry. This module is the control-plane
registry hosts bind via ``MechaHarnessConfig.get_lifecycle_extension_registry``.
Extensions declare modes and required grants; AccessControl / envelopes still
gate the real tool or node action after any rewrite.

In *Customize Claude Code with mods*, the Claude developer blog suggests
typed lifecycle hooks that observe, rewrite, block, or replace default
behavior, stack in deterministic load order, and cannot silently widen
authority
(https://claude.com/blog/claude-code-mods).
A tiny production-safeguard extension::

    >>> from mechaharness.capability_envelope import CapabilityEnvelope
    >>> from mechaharness.core.access import ExtensionRewrite
    >>> from mechaharness.lifecycle_extension import (
    ...     BeforeTool, ExtensionEffect, LifecycleExtension,
    ...     LifecycleExtensionContext, LifecycleExtensionRegistry, Rewrite,
    ... )
    >>> class NeedsRewriteGrant(LifecycleExtension):
    ...     extension_id = "acme:rewrite"
    ...     boundary = BeforeTool
    ...     modes = frozenset({Rewrite})
    ...     required_grants = (ExtensionRewrite,)
    ...     def handle(self, context):
    ...         return ExtensionEffect(
    ...             mode=Rewrite.key(),
    ...             rewrite_arguments={"path": "/safe"},
    ...         )
    >>> reg = LifecycleExtensionRegistry([NeedsRewriteGrant()])
    >>> ctx = LifecycleExtensionContext(
    ...     boundary=BeforeTool.key(), run_id="r", agent_id="a",
    ...     tool_name="Write", arguments={"path": "/etc/passwd"},
    ... )
    >>> # Without the extension.rewrite grant, the mod is skipped (default runs).
    >>> denied = reg.dispatch(
    ...     BeforeTool, ctx, envelope=CapabilityEnvelope(grants=["core:fs.write"]),
    ... )
    >>> denied.rewrite_arguments is None
    True
    >>> allowed = reg.dispatch(
    ...     BeforeTool, ctx,
    ...     envelope=CapabilityEnvelope(
    ...         grants=["core:fs.write", "core:extension.rewrite"],
    ...     ),
    ... )
    >>> allowed.rewrite_arguments
    {'path': '/safe'}
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.access import grant_key
from mechaharness.core.events import CoreEvent, Event, EventLog, event_type_key


class ExtensionApplied(CoreEvent):
    """Provenance for one extension invocation (``core:extension_applied``)."""

    name = "extension_applied"


class LifecycleBoundary:
    """Namespaced boundary identity (open hierarchy, like ``EventType`` / ``Grant``)."""

    namespace: ClassVar[str] = ""
    name: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            return
        if not cls.namespace:
            raise TypeError(f"{cls.__name__} must set namespace (via a base class)")
        if ":" in cls.namespace or ":" in cls.name:
            raise ValueError("namespace and name must not contain ':'")
        key = cls.key()
        existing = _BOUNDARIES.get(key)
        if existing is not None and existing is not cls:
            raise ValueError(f"duplicate lifecycle boundary {key!r} ({existing.__name__})")
        _BOUNDARIES[key] = cls

    @classmethod
    def key(cls) -> str:
        if not cls.namespace or not cls.name:
            raise TypeError(f"{cls.__name__} is not a concrete lifecycle boundary")
        return f"{cls.namespace}:{cls.name}"


_BOUNDARIES: dict[str, type[LifecycleBoundary]] = {}


class CoreLifecycleBoundary(LifecycleBoundary):
    namespace = "core"


class BeforeTool(CoreLifecycleBoundary):
    name = "before_tool"


class AfterTool(CoreLifecycleBoundary):
    name = "after_tool"


class BeforeInference(CoreLifecycleBoundary):
    name = "before_inference"


class AfterInference(CoreLifecycleBoundary):
    name = "after_inference"


class BeforeTurn(CoreLifecycleBoundary):
    name = "before_turn"


class AfterTurn(CoreLifecycleBoundary):
    name = "after_turn"


class BeforeGraphNode(CoreLifecycleBoundary):
    name = "before_graph_node"


class AfterGraphNode(CoreLifecycleBoundary):
    name = "after_graph_node"


class InterceptionMode:
    """Namespaced interception mode (open hierarchy)."""

    namespace: ClassVar[str] = ""
    name: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            return
        if not cls.namespace:
            raise TypeError(f"{cls.__name__} must set namespace (via a base class)")
        if ":" in cls.namespace or ":" in cls.name:
            raise ValueError("namespace and name must not contain ':'")
        key = cls.key()
        existing = _MODES.get(key)
        if existing is not None and existing is not cls:
            raise ValueError(f"duplicate interception mode {key!r} ({existing.__name__})")
        _MODES[key] = cls

    @classmethod
    def key(cls) -> str:
        if not cls.namespace or not cls.name:
            raise TypeError(f"{cls.__name__} is not a concrete interception mode")
        return f"{cls.namespace}:{cls.name}"


_MODES: dict[str, type[InterceptionMode]] = {}


class CoreInterceptionMode(InterceptionMode):
    namespace = "core"


class ObserveBefore(CoreInterceptionMode):
    name = "observe_before"


class ObserveAfter(CoreInterceptionMode):
    name = "observe_after"


class Rewrite(CoreInterceptionMode):
    name = "rewrite"


class Block(CoreInterceptionMode):
    name = "block"


class Retry(CoreInterceptionMode):
    name = "retry"


class Replace(CoreInterceptionMode):
    name = "replace"


class Wrap(CoreInterceptionMode):
    name = "wrap"


class LifecycleExtensionContext(BaseModel):
    """Snapshot passed to an extension at a boundary."""

    model_config = ConfigDict(extra="allow")

    boundary: str
    run_id: str
    agent_id: str
    parent_agent_id: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    turn: int | None = None
    node_id: str | None = None
    node_kind: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    envelope_grants: list[str] = Field(default_factory=list)


class ExtensionEffect(BaseModel):
    """Local effect of one extension on the pending default action."""

    model_config = ConfigDict(extra="allow")

    mode: str = ObserveBefore.key()
    rewrite_arguments: dict[str, Any] | None = None
    rewrite_tool_name: str | None = None
    block: bool = False
    block_message: str | None = None
    replace_content: str | None = None
    replace_is_error: bool = False
    notes: dict[str, Any] = Field(default_factory=dict)


class LifecycleExtension(ABC):
    """Host-provided interception at one boundary with declared modes/grants."""

    extension_id: str = "core:anonymous"
    version: str = "1"
    boundary: type[LifecycleBoundary] = BeforeTool
    modes: frozenset[type[InterceptionMode]] = frozenset({ObserveBefore, ObserveAfter})
    required_grants: Sequence[object] = ()

    @abstractmethod
    def handle(self, context: LifecycleExtensionContext) -> ExtensionEffect:
        """Return a local effect; mutative fields ignored unless mode is declared."""


class LifecycleExtensionRegistry:
    """Explicit ordered sequence of extensions (registration order = run order)."""

    def __init__(self, extensions: Sequence[LifecycleExtension] | None = None) -> None:
        self._extensions: list[LifecycleExtension] = list(extensions or ())

    def __iter__(self) -> Iterator[LifecycleExtension]:
        return iter(self._extensions)

    def __len__(self) -> int:
        return len(self._extensions)

    @property
    def extensions(self) -> tuple[LifecycleExtension, ...]:
        return tuple(self._extensions)

    def for_boundary(self, boundary: type[LifecycleBoundary]) -> list[LifecycleExtension]:
        key = boundary.key()
        return [ext for ext in self._extensions if ext.boundary.key() == key]

    def authority_ok(
        self,
        extension: LifecycleExtension,
        *,
        envelope: CapabilityEnvelope | None,
    ) -> bool:
        required = [grant_key(g) for g in extension.required_grants]
        if not required:
            return True
        if envelope is None:
            return True
        return all(envelope.allows_grant(g) for g in required)

    def dispatch(
        self,
        boundary: type[LifecycleBoundary],
        context: LifecycleExtensionContext,
        *,
        event_log: EventLog | None = None,
        envelope: CapabilityEnvelope | None = None,
        allow_modes: frozenset[type[InterceptionMode]] | None = None,
    ) -> ExtensionEffect:
        """Run matching extensions in order; return merged effect for the caller.

        ``allow_modes`` limits which mutative modes are honored (observe is always
        recorded). Hard AccessControl still runs after this returns.
        """
        permitted = allow_modes or frozenset(
            {ObserveBefore, ObserveAfter, Rewrite, Block, Replace}
        )
        merged = ExtensionEffect()
        arguments = dict(context.arguments)
        tool_name = context.tool_name
        order = 0
        for extension in self.for_boundary(boundary):
            order += 1
            if not self.authority_ok(extension, envelope=envelope):
                self._emit(
                    event_log,
                    context,
                    extension=extension,
                    order=order,
                    mode="authority_denied",
                    default_ran=True,
                    arguments=arguments,
                    tool_name=tool_name,
                    effect=ExtensionEffect(mode="authority_denied"),
                )
                continue
            ctx = context.model_copy(
                update={
                    "arguments": dict(arguments),
                    "tool_name": tool_name,
                    "envelope_grants": list(envelope.grants) if envelope else [],
                }
            )
            effect = extension.handle(ctx)
            mode_key = effect.mode
            declared = {m.key() for m in extension.modes}
            if mode_key not in declared:
                mode_key = next(iter(declared), ObserveBefore.key())
                effect = effect.model_copy(update={"mode": mode_key})

            applied_rewrite = False
            applied_block = False
            applied_replace = False
            if (
                Rewrite in permitted
                and Rewrite.key() in declared
                and (effect.rewrite_arguments is not None or effect.rewrite_tool_name)
            ):
                if effect.rewrite_arguments is not None:
                    arguments = dict(effect.rewrite_arguments)
                    merged.rewrite_arguments = dict(arguments)
                    applied_rewrite = True
                if effect.rewrite_tool_name is not None:
                    tool_name = effect.rewrite_tool_name
                    merged.rewrite_tool_name = tool_name
                    applied_rewrite = True
                mode_key = Rewrite.key()
            if Block in permitted and Block.key() in declared and effect.block:
                merged.block = True
                merged.block_message = effect.block_message or merged.block_message
                applied_block = True
                mode_key = Block.key()
            if (
                Replace in permitted
                and Replace.key() in declared
                and effect.replace_content is not None
            ):
                merged.replace_content = effect.replace_content
                merged.replace_is_error = effect.replace_is_error
                applied_replace = True
                mode_key = Replace.key()

            default_will_run = not (merged.block or merged.replace_content is not None)
            self._emit(
                event_log,
                context,
                extension=extension,
                order=order,
                mode=mode_key,
                default_ran=default_will_run,
                arguments=arguments,
                tool_name=tool_name,
                effect=effect,
                applied_rewrite=applied_rewrite,
                applied_block=applied_block,
                applied_replace=applied_replace,
            )
            if applied_block or applied_replace:
                break

        merged.rewrite_arguments = (
            dict(arguments) if merged.rewrite_arguments is not None else None
        )
        if tool_name != context.tool_name:
            merged.rewrite_tool_name = tool_name
        return merged

    def _emit(
        self,
        event_log: EventLog | None,
        context: LifecycleExtensionContext,
        *,
        extension: LifecycleExtension,
        order: int,
        mode: str,
        default_ran: bool,
        arguments: Mapping[str, Any],
        tool_name: str | None,
        effect: ExtensionEffect,
        applied_rewrite: bool = False,
        applied_block: bool = False,
        applied_replace: bool = False,
    ) -> None:
        if event_log is None:
            return
        payload: dict[str, Any] = {
            "extension_id": extension.extension_id,
            "extension_version": extension.version,
            "boundary": context.boundary,
            "order": order,
            "mode": mode,
            "default_ran": default_ran,
            "tool_name": tool_name,
            "tool_call_id": context.tool_call_id,
            "arguments": dict(arguments),
            "applied_rewrite": applied_rewrite,
            "applied_block": applied_block,
            "applied_replace": applied_replace,
            "notes": dict(effect.notes),
        }
        if context.turn is not None:
            payload["turn"] = context.turn
        if context.node_id is not None:
            payload["node_id"] = context.node_id
        if context.node_kind is not None:
            payload["node_kind"] = context.node_kind
        event_log.emit(
            Event(
                type=event_type_key(ExtensionApplied),
                agent_id=context.agent_id,
                parent_agent_id=context.parent_agent_id,
                run_id=context.run_id,
                payload=payload,
            )
        )


def boundary_key(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, type) and issubclass(value, LifecycleBoundary):
        return value.key()
    raise TypeError(f"boundary must be LifecycleBoundary subclass or str, got {value!r}")


def empty_lifecycle_extension_registry() -> LifecycleExtensionRegistry:
    return LifecycleExtensionRegistry()


__all__ = [
    "AfterGraphNode",
    "AfterInference",
    "AfterTool",
    "AfterTurn",
    "BeforeGraphNode",
    "BeforeInference",
    "BeforeTool",
    "BeforeTurn",
    "Block",
    "ExtensionApplied",
    "ExtensionEffect",
    "InterceptionMode",
    "LifecycleBoundary",
    "LifecycleExtension",
    "LifecycleExtensionContext",
    "LifecycleExtensionRegistry",
    "ObserveAfter",
    "ObserveBefore",
    "Replace",
    "Retry",
    "Rewrite",
    "Wrap",
    "boundary_key",
    "empty_lifecycle_extension_registry",
]
