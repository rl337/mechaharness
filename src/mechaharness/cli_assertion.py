"""Open CLI story assertions (map multibind; no closed expect bag).

YAML ``expect`` is a list of ``{kind, ...}`` entries. ``kind`` is open
identity — hosts/tests register more via ``cli_assertion_classes()``.

``key`` may be a top-level observation name or a dotted / indexed path
(``plan.items[0].instruction``).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

# name | [index] tokens; dots separate names.
_PATH_TOKEN = re.compile(r"([^.\[]+)|\[(\d+)\]")


def resolve_observation_path(observation: Mapping[str, Any], path: str) -> Any:
    """Resolve ``path`` into ``observation`` (dot + ``[index]``).

    Bare keys (no ``.`` / ``[``) use exact top-level lookup. Nested paths
    walk mappings and sequences; missing segments raise ``KeyError``.
    """
    if not path:
        raise KeyError(path)
    if "." not in path and "[" not in path:
        if path not in observation:
            raise KeyError(path)
        return observation[path]

    current: Any = observation
    for match in _PATH_TOKEN.finditer(path):
        name, index_s = match.group(1), match.group(2)
        if name is not None:
            if not isinstance(current, Mapping) or name not in current:
                raise KeyError(path)
            current = current[name]
        else:
            idx = int(index_s)
            if not isinstance(current, Sequence) or isinstance(current, (str, bytes)):
                raise KeyError(path)
            if idx < 0 or idx >= len(current):
                raise KeyError(path)
            current = current[idx]
    return current


def _lookup(observation: Mapping[str, Any], key: str) -> Any:
    """Resolve ``key`` or raise ``AssertionError`` with top-level keys listed."""
    try:
        return resolve_observation_path(observation, key)
    except KeyError as exc:
        raise AssertionError(
            f"missing observation key {key!r}; got {sorted(observation)}"
        ) from exc


class CliAssertionSpec(BaseModel):
    """One structured assertion (open ``kind`` + params)."""

    model_config = ConfigDict(extra="allow")

    kind: str

    def params(self) -> dict[str, Any]:
        data = self.model_dump()
        data.pop("kind", None)
        return data


class CliAssertion(ABC):
    """One assertion kind. Register via ``cli_assertion_classes()`` map multibind."""

    kind: ClassVar[str]
    params_model: ClassVar[type[BaseModel]]

    @abstractmethod
    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        """Raise ``AssertionError`` when the observation fails the check."""


class _EqualsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any


class EqualsAssertion(CliAssertion):
    kind = "equals"
    params_model = _EqualsParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_EqualsParams, params)
        got = _lookup(observation, body.key)
        if got != body.value:
            raise AssertionError(
                f"{body.key}: {got!r} != {body.value!r}"
            )


class _KeyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any = None


class ExactlyAssertion(CliAssertion):
    kind = "exactly"
    params_model = _KeyParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_KeyParams, params)
        got = _lookup(observation, body.key)
        if got != body.value:
            raise AssertionError(
                f"{body.key}: {got!r} != {body.value!r}"
            )


class PositiveAssertion(CliAssertion):
    kind = "positive"
    params_model = _KeyParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_KeyParams, params)
        got = _lookup(observation, body.key)
        if not (isinstance(got, (int, float)) and got > 0):
            raise AssertionError(f"{body.key}: expected positive, got {got!r}")


class NonemptyAssertion(CliAssertion):
    kind = "nonempty"
    params_model = _KeyParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_KeyParams, params)
        got = _lookup(observation, body.key)
        if got is None or (isinstance(got, str) and not got.strip()):
            raise AssertionError(f"{body.key}: expected nonempty, got {got!r}")
        if isinstance(got, (list, dict)) and not got:
            raise AssertionError(f"{body.key}: expected nonempty, got {got!r}")


class TrueAssertion(CliAssertion):
    kind = "true"
    params_model = _KeyParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_KeyParams, params)
        got = _lookup(observation, body.key)
        if got is not True:
            raise AssertionError(f"{body.key}: expected True, got {got!r}")


class FalseAssertion(CliAssertion):
    kind = "false"
    params_model = _KeyParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_KeyParams, params)
        got = _lookup(observation, body.key)
        if got is not False:
            raise AssertionError(f"{body.key}: expected False, got {got!r}")


class _ErrorParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


class ErrorAssertion(CliAssertion):
    """Assert the step surfaced a structured error code (durable IoC, etc.)."""

    kind = "error"
    params_model = _ErrorParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_ErrorParams, params)
        got = observation.get("error")
        if got != body.value:
            raise AssertionError(f"error: {got!r} != {body.value!r}")


class _IncludesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: list[Any]


class IncludesAssertion(CliAssertion):
    """Every item in ``value`` must appear in the observation sequence at ``key``."""

    kind = "includes"
    params_model = _IncludesParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_IncludesParams, params)
        got = _lookup(observation, body.key)
        missing = [item for item in body.value if item not in got]
        if missing:
            raise AssertionError(f"{body.key}: missing {missing} in {got}")


class _IncludesIfParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: list[Any]
    if_key: str
    if_equals: Any = True


class IncludesIfAssertion(CliAssertion):
    """Like ``includes``, but only when ``observation[if_key] == if_equals``.

    Used when a write ledger is required only if the coding burst expected
    changes (not when host verify was already green / ``already_satisfied``).
    """

    kind = "includes_if"
    params_model = _IncludesIfParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_IncludesIfParams, params)
        gate = observation.get(body.if_key)
        if gate != body.if_equals:
            return
        got = _lookup(observation, body.key)
        missing = [item for item in body.value if item not in got]
        if missing:
            raise AssertionError(
                f"{body.key}: missing {missing} in {got} "
                f"(required because {body.if_key}={body.if_equals!r})"
            )


class _GteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: int | float


class GteAssertion(CliAssertion):
    """Observation at ``key`` must be >= ``value``."""

    kind = "gte"
    params_model = _GteParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_GteParams, params)
        got = _lookup(observation, body.key)
        if not isinstance(got, (int, float)) or got < body.value:
            raise AssertionError(f"{body.key}: {got!r} < {body.value!r}")


class LteAssertion(CliAssertion):
    """Observation at ``key`` must be <= ``value`` (token / cost ceilings)."""

    kind = "lte"
    params_model = _GteParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_GteParams, params)
        got = _lookup(observation, body.key)
        if not isinstance(got, (int, float)) or got > body.value:
            raise AssertionError(f"{body.key}: {got!r} > {body.value!r}")


class _ContainsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: str


class ContainsAssertion(CliAssertion):
    """``value`` must be a substring of ``str(observation[key])``."""

    kind = "contains"
    params_model = _ContainsParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_ContainsParams, params)
        got = _lookup(observation, body.key)
        if body.value not in str(got):
            raise AssertionError(f"{body.key}: {body.value!r} not in {got!r}")


class _HumanReviewParams(BaseModel):
    """Fail unless the step requested human review.

    ``inject`` is folded into verb params by the user_story step harness and
    ignored at assert time.
    """

    model_config = ConfigDict(extra="forbid")

    inject: dict[str, Any] | None = None


class HumanReviewAssertion(CliAssertion):
    """Observation must report ``human_review_requested: true``."""

    kind = "human_review"
    params_model = _HumanReviewParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        del params
        if observation.get("human_review_requested") is not True:
            raise AssertionError(
                "human review was not requested "
                f"(human_review_requested={observation.get('human_review_requested')!r})"
            )


def default_cli_assertion_classes() -> dict[str, type[CliAssertion]]:
    return {
        EqualsAssertion.kind: EqualsAssertion,
        ExactlyAssertion.kind: ExactlyAssertion,
        PositiveAssertion.kind: PositiveAssertion,
        NonemptyAssertion.kind: NonemptyAssertion,
        TrueAssertion.kind: TrueAssertion,
        FalseAssertion.kind: FalseAssertion,
        ErrorAssertion.kind: ErrorAssertion,
        IncludesAssertion.kind: IncludesAssertion,
        IncludesIfAssertion.kind: IncludesIfAssertion,
        GteAssertion.kind: GteAssertion,
        LteAssertion.kind: LteAssertion,
        ContainsAssertion.kind: ContainsAssertion,
        HumanReviewAssertion.kind: HumanReviewAssertion,
    }


class _CliAssertionMapHost:
    def __init__(self, assertions: dict[str, CliAssertion]) -> None:
        self.assertions = assertions


def resolve_cli_assertions(config: Any) -> dict[str, CliAssertion]:
    from mechaharness.di import _expose_ctor_type_hints, get_injector

    _expose_ctor_type_hints(_CliAssertionMapHost)
    return cast(
        dict[str, CliAssertion],
        get_injector(config).inject(_CliAssertionMapHost).assertions,
    )


def parse_expect_list(raw: Any) -> list[CliAssertionSpec]:
    """Parse YAML expect list; reject closed bags and empty lists."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("expect must be a non-empty list of {kind: ...} assertions")
    out: list[CliAssertionSpec] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ValueError(f"expect[{index}] must be a mapping")
        data = dict(item)
        if "kind" not in data:
            raise ValueError(f"expect[{index}] missing kind")
        out.append(CliAssertionSpec.model_validate(data))
    return out


# Cassette replay pins exact usage; live models vary. Soften only these keys.
_CASSETTE_EXACT_KEYS = frozenset(
    {"prompt_tokens", "completion_tokens", "total_tokens"}
)
_CASSETTE_EXACT_KINDS = frozenset({"equals", "exactly", "lte", "gte"})


def is_cassette_exact_assertion(spec: CliAssertionSpec) -> bool:
    """True when the spec pins replay-exact token counts from a cassette."""
    key = spec.params().get("key")
    return (
        isinstance(key, str)
        and key in _CASSETTE_EXACT_KEYS
        and spec.kind in _CASSETTE_EXACT_KINDS
    )


def check_assertions(
    observation: Mapping[str, Any],
    specs: list[CliAssertionSpec],
    assertions: Mapping[str, CliAssertion],
    *,
    label: str,
    relax_cassette_exact: bool = False,
) -> None:
    for index, spec in enumerate(specs):
        if relax_cassette_exact and is_cassette_exact_assertion(spec):
            continue
        checker = assertions.get(spec.kind)
        if checker is None:
            known = ", ".join(sorted(assertions))
            raise AssertionError(
                f"{label}: unknown assertion kind {spec.kind!r}; known: {known}"
            )
        params = checker.params_model.model_validate(spec.params())
        try:
            checker.check(observation, params)
        except AssertionError as exc:
            raise AssertionError(f"{label}: expect[{index}] {exc}") from exc


class ExpectBlock(BaseModel):
    """Validated expect list (load-time)."""

    model_config = ConfigDict(extra="forbid")

    items: list[CliAssertionSpec] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _coerce_list(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"items": parse_expect_list(data)}
        return data


__all__ = [
    "CliAssertion",
    "CliAssertionSpec",
    "ExpectBlock",
    "check_assertions",
    "default_cli_assertion_classes",
    "is_cassette_exact_assertion",
    "parse_expect_list",
    "resolve_cli_assertions",
    "resolve_observation_path",
]
