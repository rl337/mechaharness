"""CLI verb catalog: open identity via pyiv map multibind.

Hosts and story Configs contribute ``cli_verb_classes()`` entries. Dispatch is
``verbs[name].run(params, runtime)`` — no closed optional-field union and no
per-verb ``if`` ladder in the instrumentor.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, ClassVar, TypeVar, Union, cast

from pydantic import BaseModel, ConfigDict, Field

ParamsT = TypeVar("ParamsT", bound=BaseModel)
ProbeFn = Callable[[Any], Union[dict[str, Any], Awaitable[dict[str, Any]]]]
RuntimeFn = Callable[[Any, Any], Union[dict[str, Any], Awaitable[dict[str, Any]]]]


class CliParsedCommand(BaseModel):
    """One YAML command: verb name + raw params (validated by the verb)."""

    model_config = ConfigDict(extra="forbid")

    verb: str
    params: dict[str, Any] = Field(default_factory=dict)


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
        """Execute; return ``CliStepResult`` or a probe ``dict`` merged into expect."""


def make_probe_verb(
    name: str,
    params_model: type[ParamsT],
    fn: ProbeFn,
) -> type[CliVerb]:
    """Build a stateless verb that ignores runtime (library / story probes)."""

    class _ProbeVerb(CliVerb):
        async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
            del runtime
            out = fn(cast(ParamsT, params))
            if inspect.isawaitable(out):
                out = await out
            return out

    _ProbeVerb.name = name
    _ProbeVerb.params_model = params_model
    _ProbeVerb.__name__ = f"{name}_verb"
    _ProbeVerb.__qualname__ = _ProbeVerb.__name__
    return _ProbeVerb


def make_runtime_verb(
    name: str,
    params_model: type[ParamsT],
    fn: RuntimeFn,
) -> type[CliVerb]:
    """Build a verb that delegates to ``fn(params, runtime)``."""

    class _RuntimeVerb(CliVerb):
        async def run(self, params: BaseModel, runtime: Any) -> Any:
            out = fn(cast(ParamsT, params), runtime)
            if inspect.isawaitable(out):
                out = await out
            return out

    _RuntimeVerb.name = name
    _RuntimeVerb.params_model = params_model
    _RuntimeVerb.__name__ = f"{name}_verb"
    _RuntimeVerb.__qualname__ = _RuntimeVerb.__name__
    return _RuntimeVerb


class _CliVerbMapHost:
    """Injection host so ``Dict[str, CliVerb]`` resolves from the map multibind."""

    def __init__(self, verbs: dict[str, CliVerb]) -> None:
        self.verbs = verbs


def resolve_cli_verbs(config: Any) -> dict[str, CliVerb]:
    """Construct the verb map from Config's ``cli_verb_classes`` multibind."""
    from mechaharness.di import _expose_ctor_type_hints, get_injector

    _expose_ctor_type_hints(_CliVerbMapHost)
    return cast(dict[str, CliVerb], get_injector(config).inject(_CliVerbMapHost).verbs)


def parse_cli_commands(raw_commands: list[Any]) -> list[CliParsedCommand]:
    """Parse YAML command list: each item is ``{verb_name: params}``."""
    out: list[CliParsedCommand] = []
    for index, item in enumerate(raw_commands):
        if not isinstance(item, Mapping):
            raise ValueError(f"commands[{index}] must be a mapping")
        data = dict(item)
        data.pop("expect", None)  # per-command expect reserved / unused
        if len(data) != 1:
            raise ValueError(
                f"commands[{index}] needs exactly one verb key; got {sorted(data)}"
            )
        verb, params = next(iter(data.items()))
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            raise ValueError(f"commands[{index}].{verb} params must be a mapping")
        out.append(CliParsedCommand(verb=str(verb), params=dict(params)))
    return out


def script_from_mapping(data: Mapping[str, Any]) -> CliScript:
    """Build a :class:`CliScript` from a YAML-like mapping (commands only)."""
    commands = data.get("commands")
    if not isinstance(commands, list) or not commands:
        raise ValueError("script requires non-empty commands list")
    return CliScript(commands=parse_cli_commands(commands))


__all__ = [
    "CliParsedCommand",
    "CliScript",
    "CliVerb",
    "make_probe_verb",
    "make_runtime_verb",
    "parse_cli_commands",
    "resolve_cli_verbs",
    "script_from_mapping",
]
