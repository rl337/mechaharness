"""Open CLI story assertions (map multibind; no closed expect bag).

YAML ``expect`` is a list of ``{kind, ...}`` entries. ``kind`` is open
identity — hosts/tests register more via ``cli_assertion_classes()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
        if body.key not in observation:
            raise AssertionError(
                f"missing observation key {body.key!r}; got {sorted(observation)}"
            )
        got = observation[body.key]
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
        if body.key not in observation:
            raise AssertionError(
                f"missing observation key {body.key!r}; got {sorted(observation)}"
            )
        got = observation[body.key]
        if got != body.value:
            raise AssertionError(
                f"{body.key}: {got!r} != {body.value!r}"
            )


class PositiveAssertion(CliAssertion):
    kind = "positive"
    params_model = _KeyParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_KeyParams, params)
        if body.key not in observation:
            raise AssertionError(
                f"missing observation key {body.key!r}; got {sorted(observation)}"
            )
        got = observation[body.key]
        if not (isinstance(got, (int, float)) and got > 0):
            raise AssertionError(f"{body.key}: expected positive, got {got!r}")


class NonemptyAssertion(CliAssertion):
    kind = "nonempty"
    params_model = _KeyParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_KeyParams, params)
        if body.key not in observation:
            raise AssertionError(
                f"missing observation key {body.key!r}; got {sorted(observation)}"
            )
        got = observation[body.key]
        if got is None or (isinstance(got, str) and not got.strip()):
            raise AssertionError(f"{body.key}: expected nonempty, got {got!r}")
        if isinstance(got, (list, dict)) and not got:
            raise AssertionError(f"{body.key}: expected nonempty, got {got!r}")


class TrueAssertion(CliAssertion):
    kind = "true"
    params_model = _KeyParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_KeyParams, params)
        if body.key not in observation:
            raise AssertionError(
                f"missing observation key {body.key!r}; got {sorted(observation)}"
            )
        got = observation[body.key]
        if got is not True:
            raise AssertionError(f"{body.key}: expected True, got {got!r}")


class FalseAssertion(CliAssertion):
    kind = "false"
    params_model = _KeyParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_KeyParams, params)
        if body.key not in observation:
            raise AssertionError(
                f"missing observation key {body.key!r}; got {sorted(observation)}"
            )
        got = observation[body.key]
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
        if body.key not in observation:
            raise AssertionError(
                f"missing observation key {body.key!r}; got {sorted(observation)}"
            )
        got = observation[body.key]
        missing = [item for item in body.value if item not in got]
        if missing:
            raise AssertionError(f"{body.key}: missing {missing} in {got}")


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
        if body.key not in observation:
            raise AssertionError(
                f"missing observation key {body.key!r}; got {sorted(observation)}"
            )
        got = observation[body.key]
        if not isinstance(got, (int, float)) or got < body.value:
            raise AssertionError(f"{body.key}: {got!r} < {body.value!r}")


class LteAssertion(CliAssertion):
    """Observation at ``key`` must be <= ``value`` (token / cost ceilings)."""

    kind = "lte"
    params_model = _GteParams

    def check(self, observation: Mapping[str, Any], params: BaseModel) -> None:
        body = cast(_GteParams, params)
        if body.key not in observation:
            raise AssertionError(
                f"missing observation key {body.key!r}; got {sorted(observation)}"
            )
        got = observation[body.key]
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
        if body.key not in observation:
            raise AssertionError(
                f"missing observation key {body.key!r}; got {sorted(observation)}"
            )
        got = observation[body.key]
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


def check_assertions(
    observation: Mapping[str, Any],
    specs: list[CliAssertionSpec],
    assertions: Mapping[str, CliAssertion],
    *,
    label: str,
) -> None:
    for index, spec in enumerate(specs):
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
    "parse_expect_list",
    "resolve_cli_assertions",
]
