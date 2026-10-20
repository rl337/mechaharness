"""CLI verb / probe catalog: open identity via pyiv map multibind.

Hosts and story Configs contribute ``cli_verb_classes()`` entries. Dispatch is
``verbs[name].run(params, runtime)`` — no closed optional-field union and no
per-verb ``if`` ladder in the instrumentor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field


class CliParsedCommand(BaseModel):
    """One YAML command: verb name + raw params (+ optional per-step expect)."""

    model_config = ConfigDict(extra="forbid")

    verb: str
    params: dict[str, Any] = Field(default_factory=dict)
    expect: list[dict[str, Any]] | None = None
    expect_error: str | None = None


class CliScript(BaseModel):
    """Product CLI script (no test expects)."""

    model_config = ConfigDict(extra="forbid")

    commands: list[CliParsedCommand] = Field(min_length=1)


class CliVerb(ABC):
    """One instrumentor verb. Register via ``cli_verb_classes()`` map multibind."""

    name: ClassVar[str]
    params_model: ClassVar[type[BaseModel]]

    @abstractmethod
    async def run(self, params: BaseModel, runtime: Any) -> Any:
        """Execute; return ``CliStepResult`` or a probe ``dict`` merged into observation."""


class CliProbe(ABC):
    """Story/test probe under the ``probe`` verb (test Config map multibind)."""

    name: ClassVar[str]
    params_model: ClassVar[type[BaseModel]]

    @abstractmethod
    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        """Return observation fields for hard expects."""


class _CliVerbMapHost:
    """Injection host so ``Dict[str, CliVerb]`` resolves from the map multibind."""

    def __init__(self, verbs: dict[str, CliVerb]) -> None:
        self.verbs = verbs


class _CliProbeMapHost:
    def __init__(self, probes: dict[str, CliProbe]) -> None:
        self.probes = probes


def resolve_cli_verbs(config: Any) -> dict[str, CliVerb]:
    """Construct the verb map from Config's ``cli_verb_classes`` multibind."""
    from mechaharness.di import _expose_ctor_type_hints, get_injector

    _expose_ctor_type_hints(_CliVerbMapHost)
    return cast(dict[str, CliVerb], get_injector(config).inject(_CliVerbMapHost).verbs)


def resolve_cli_probes(config: Any) -> dict[str, CliProbe]:
    from mechaharness.di import _expose_ctor_type_hints, get_injector

    _expose_ctor_type_hints(_CliProbeMapHost)
    return cast(
        dict[str, CliProbe], get_injector(config).inject(_CliProbeMapHost).probes
    )


def parse_cli_commands(raw_commands: list[Any]) -> list[CliParsedCommand]:
    """Parse YAML command list: each item is ``{verb_name: params}`` (+ expect)."""
    out: list[CliParsedCommand] = []
    for index, item in enumerate(raw_commands):
        if not isinstance(item, Mapping):
            raise ValueError(f"commands[{index}] must be a mapping")
        data = dict(item)
        expect = data.pop("expect", None)
        expect_error = data.pop("expect_error", None)
        if len(data) != 1:
            raise ValueError(
                f"commands[{index}] needs exactly one verb key; got {sorted(data)}"
            )
        verb, params = next(iter(data.items()))
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            raise ValueError(f"commands[{index}].{verb} params must be a mapping")
        out.append(
            CliParsedCommand(
                verb=str(verb),
                params=dict(params),
                expect=list(expect) if expect is not None else None,
                expect_error=str(expect_error) if expect_error is not None else None,
            )
        )
    return out


def script_from_mapping(data: Mapping[str, Any]) -> CliScript:
    """Build a :class:`CliScript` from a YAML-like mapping (commands only)."""
    commands = data.get("commands")
    if not isinstance(commands, list) or not commands:
        raise ValueError("script requires non-empty commands list")
    return CliScript(commands=parse_cli_commands(commands))


__all__ = [
    "CliParsedCommand",
    "CliProbe",
    "CliScript",
    "CliVerb",
    "parse_cli_commands",
    "resolve_cli_probes",
    "resolve_cli_verbs",
    "script_from_mapping",
]
