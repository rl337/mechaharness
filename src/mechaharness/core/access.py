"""Cost units and deny-by-default tool grants.

Ability is a five-step scale; higher ability costs more. Grants are open
identity: a class hierarchy with wire form ``namespace:name`` (for example
``core:fs.read``, ``acme:widget``). Unknown namespaced keys round-trip; bare
names are rejected.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import Enum
from typing import Any, ClassVar, Union

from pydantic import BaseModel, Field, field_validator

from mechaharness.core.events import AccessCheck, Cost, Event, EventLog, EventType, event_type_key
from mechaharness.core.types import Usage


class Ability(str, Enum):
    """How capable a completer or tool is at a given kind of work."""

    SIMPLE = "simple"
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    PROFICIENT = "proficient"
    ADVANCED = "advanced"

    @property
    def rank(self) -> int:
        order = (
            Ability.SIMPLE,
            Ability.BASIC,
            Ability.INTERMEDIATE,
            Ability.PROFICIENT,
            Ability.ADVANCED,
        )
        return order.index(self) + 1

    @property
    def units(self) -> int:
        """Cost units: 1, 2, 4, 8, 16."""
        return 1 << (self.rank - 1)


class CapabilityKind(str, Enum):
    """Kinds of work a completer can perform (aligned with model skills)."""

    CODE = "code"
    REASONING = "reasoning"
    TOOL_USE = "tool_use"


class Capability(BaseModel):
    kind: CapabilityKind
    level: Ability


class CapabilityProfile(BaseModel):
    """Declared skills of a completer. Cost is the sum of each capability's units."""

    capabilities: list[Capability] = Field(default_factory=list)

    def units(self) -> int:
        if not self.capabilities:
            return Ability.SIMPLE.units
        return sum(item.level.units for item in self.capabilities)


class Grant:
    """Namespaced grant identity.

    Subclass to add grants. The wire form is ``namespace:name`` (for example
    ``core:fs.read``). Intermediate classes set ``namespace``; leaves set
    ``name``.
    """

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
        existing = _GRANTS.get(key)
        if existing is not None and existing is not cls:
            raise ValueError(f"duplicate grant {key!r} ({existing.__name__})")
        _GRANTS[key] = cls

    @classmethod
    def key(cls) -> str:
        if not cls.namespace or not cls.name:
            raise TypeError(f"{cls.__name__} is not a concrete grant")
        return f"{cls.namespace}:{cls.name}"

    @classmethod
    def parse(cls, value: str) -> type[Grant]:
        """Return the class registered for ``namespace:name``."""
        _require_namespaced_grant(value)
        try:
            return _GRANTS[value]
        except KeyError as exc:
            raise KeyError(f"unknown grant {value!r}") from exc


_GRANTS: dict[str, type[Grant]] = {}
GrantRef = Union[str, type[Grant]]


class CoreGrant(Grant):
    """Built-in MechaHarness grants (``core:*``). Conveniences, not a closed set."""

    namespace = "core"


class FsRead(CoreGrant):
    name = "fs.read"


class FsWrite(CoreGrant):
    name = "fs.write"


class NetHttp(CoreGrant):
    name = "net.http"


class MediaImage(CoreGrant):
    name = "media.image"


class MediaVideo(CoreGrant):
    name = "media.video"


class MediaAudio(CoreGrant):
    name = "media.audio"


def grant_key(value: object) -> str:
    """Normalize a class or ``namespace:name`` string to the wire key."""
    if isinstance(value, str):
        _require_namespaced_grant(value)
        return value
    if isinstance(value, type) and issubclass(value, Grant):
        return value.key()
    raise TypeError(f"grant must be Grant subclass or str, got {value!r}")


def _require_namespaced_grant(value: str) -> None:
    namespace, sep, name = value.partition(":")
    if not sep or not namespace or not name:
        raise ValueError(f"grant must be namespace:name, got {value!r}")
    if ":" in name:
        raise ValueError(f"grant must be namespace:name, got {value!r}")


class AccessPolicy(BaseModel):
    """Deny-by-default grant list for a harness."""

    grants: list[str] = Field(default_factory=list)

    @field_validator("grants", mode="before")
    @classmethod
    def _coerce_grants(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple)):
            raise TypeError("grants must be a sequence")
        return [grant_key(item) for item in value]

    def allows(self, required: Sequence[object]) -> bool:
        granted = set(self.grants)
        needed = {grant_key(item) for item in required}
        return needed <= granted


class CostEntry(BaseModel):
    kind: str
    name: str
    units: int
    capabilities: list[Capability] = Field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class CostReport(BaseModel):
    units: int = 0
    entries: list[CostEntry] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, entry: CostEntry) -> None:
        self.entries.append(entry)
        self.units += entry.units
        if entry.prompt_tokens is not None:
            self.prompt_tokens += entry.prompt_tokens
        if entry.completion_tokens is not None:
            self.completion_tokens += entry.completion_tokens
        if entry.total_tokens is not None:
            self.total_tokens += entry.total_tokens


def inference_cost_entry(
    name: str,
    profile: CapabilityProfile,
    *,
    usage: Usage | None = None,
) -> CostEntry:
    return CostEntry(
        kind="inference",
        name=name,
        units=profile.units(),
        capabilities=list(profile.capabilities),
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        total_tokens=usage.total_tokens if usage else None,
    )


def tool_cost_entry(name: str, ability: Ability) -> CostEntry:
    return CostEntry(kind="tool", name=name, units=ability.units)


class AccessControl(ABC):
    """Whether a tool may run. Deny-by-default unless a grant covers it."""

    @abstractmethod
    def allows(
        self,
        required: Sequence[object],
        *,
        tool_name: str = "",
        agent_id: str = "",
        run_id: str = "",
        parent_agent_id: str | None = None,
    ) -> bool:
        """Return True if every required grant is held."""


class CostAccountant(ABC):
    """Price one inference call or tool invocation and keep a ledger."""

    @abstractmethod
    def price_inference(
        self,
        name: str,
        profile: CapabilityProfile,
        *,
        agent_id: str = "",
        run_id: str = "",
        parent_agent_id: str | None = None,
        usage: Usage | None = None,
    ) -> CostEntry:
        """Units for one completer call."""

    @abstractmethod
    def price_tool(
        self,
        name: str,
        ability: Ability,
        *,
        agent_id: str = "",
        run_id: str = "",
        parent_agent_id: str | None = None,
    ) -> CostEntry:
        """Units for one successful tool run."""

    @abstractmethod
    def report(self) -> CostReport:
        """Accumulated ledger for this accountant instance."""


def _emit_policy_event(
    event_log: EventLog | None,
    event_type: type[EventType],
    payload: dict[str, Any],
    *,
    agent_id: str,
    run_id: str,
    parent_agent_id: str | None,
) -> None:
    if event_log is None or not agent_id or not run_id:
        return
    event_log.emit(
        Event(
            type=event_type_key(event_type),
            agent_id=agent_id,
            run_id=run_id,
            parent_agent_id=parent_agent_id,
            payload=payload,
        )
    )


class InMemoryAccessControl(AccessControl):
    """Deny-by-default grant list; records and emits every check."""

    def __init__(
        self,
        event_log: EventLog | None = None,
        grants: Sequence[object] | None = None,
        policy: AccessPolicy | None = None,
    ) -> None:
        if policy is not None:
            keys = list(policy.grants)
        else:
            keys = [grant_key(item) for item in (grants or [])]
        self.policy = AccessPolicy(grants=keys)
        self._event_log = event_log
        self.checks: list[dict[str, Any]] = []

    @property
    def grants(self) -> list[str]:
        return list(self.policy.grants)

    def allows(
        self,
        required: Sequence[object],
        *,
        tool_name: str = "",
        agent_id: str = "",
        run_id: str = "",
        parent_agent_id: str | None = None,
    ) -> bool:
        needed = [grant_key(item) for item in required]
        allowed = self.policy.allows(needed)
        record = {
            "tool": tool_name,
            "required": needed,
            "granted": list(self.policy.grants),
            "allowed": allowed,
        }
        self.checks.append(record)
        _emit_policy_event(
            self._event_log,
            AccessCheck,
            record,
            agent_id=agent_id,
            run_id=run_id,
            parent_agent_id=parent_agent_id,
        )
        return allowed


class InMemoryCostAccountant(CostAccountant):
    """Prices from the capability profile and tool ability; emits ``core:cost``."""

    def __init__(self, event_log: EventLog | None = None) -> None:
        self._event_log = event_log
        self._report = CostReport()

    def price_inference(
        self,
        name: str,
        profile: CapabilityProfile,
        *,
        agent_id: str = "",
        run_id: str = "",
        parent_agent_id: str | None = None,
        usage: Usage | None = None,
    ) -> CostEntry:
        return self._record(
            inference_cost_entry(name, profile, usage=usage),
            agent_id,
            run_id,
            parent_agent_id,
        )

    def price_tool(
        self,
        name: str,
        ability: Ability,
        *,
        agent_id: str = "",
        run_id: str = "",
        parent_agent_id: str | None = None,
    ) -> CostEntry:
        return self._record(tool_cost_entry(name, ability), agent_id, run_id, parent_agent_id)

    def report(self) -> CostReport:
        return self._report

    def _record(
        self,
        entry: CostEntry,
        agent_id: str,
        run_id: str,
        parent_agent_id: str | None,
    ) -> CostEntry:
        self._report.add(entry)
        payload: dict[str, Any] = {
            "kind": entry.kind,
            "name": entry.name,
            "units": entry.units,
        }
        if entry.prompt_tokens is not None:
            payload["prompt_tokens"] = entry.prompt_tokens
        if entry.completion_tokens is not None:
            payload["completion_tokens"] = entry.completion_tokens
        if entry.total_tokens is not None:
            payload["total_tokens"] = entry.total_tokens
        _emit_policy_event(
            self._event_log,
            Cost,
            payload,
            agent_id=agent_id,
            run_id=run_id,
            parent_agent_id=parent_agent_id,
        )
        return entry


def default_capability_profile() -> CapabilityProfile:
    """Pass-through / unknown completer: simple reasoning only."""
    return CapabilityProfile(
        capabilities=[Capability(kind=CapabilityKind.REASONING, level=Ability.SIMPLE)]
    )
