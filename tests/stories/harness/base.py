"""Story harness protocol and shared expect asserts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, Union

from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase

StoryOpRunner = Callable[[StoryCase, StoryBackend], Awaitable[None]]
PureApiOp = Callable[
    [dict[str, Any]], Union[dict[str, Any], Awaitable[dict[str, Any]]]
]


class StoryHarness(Protocol):
    """Reusable interpreter for one execution shape (kind = harness family)."""

    name: str

    def known_ops(self) -> frozenset[str]:
        """Registered operation ids for catalog validation."""

    async def run(self, case: StoryCase, backend: StoryBackend) -> None:
        """Execute one story fixture under this harness."""


def assert_expect(actual: dict[str, Any], expect: dict[str, Any]) -> None:
    """Soft/hard key asserts shared by all story harnesses."""
    for key, wanted in expect.items():
        if key not in actual:
            raise AssertionError(f"missing actual key {key!r}; got {sorted(actual)}")
        got = actual[key]
        if key.endswith("_include") and isinstance(wanted, list):
            missing = [item for item in wanted if item not in got]
            assert not missing, f"{key}: missing {missing} in {got}"
        elif key.endswith("_in") and isinstance(wanted, list):
            assert got in wanted, f"{key}: {got!r} not in {wanted!r}"
        elif key.endswith("_contains") and isinstance(wanted, str):
            assert wanted in str(got), f"{key}: {wanted!r} not in {got!r}"
        elif key.startswith("min_") and isinstance(wanted, (int, float)):
            assert got >= wanted, f"{key}: {got} < {wanted}"
        elif key.endswith("_min") and isinstance(wanted, (int, float)):
            assert got >= wanted, f"{key}: {got} < {wanted}"
        elif key.endswith("_nonempty"):
            assert bool(got) is bool(wanted), f"{key}: {got!r} vs {wanted!r}"
            if wanted:
                assert str(got).strip(), f"{key}: empty value"
        else:
            assert got == wanted, f"{key}: {got!r} != {wanted!r}"


def split_request(request: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Require ``op``; return ``(op, inputs)`` with ``op`` removed from inputs."""
    if "op" not in request:
        raise ValueError("request.json must include string field 'op'")
    op = request["op"]
    if not isinstance(op, str) or not op.strip():
        raise ValueError("request.json 'op' must be a non-empty string")
    inputs = {k: v for k, v in request.items() if k != "op"}
    return op, inputs


@dataclass
class StrippedRequestCase:
    """StoryCase proxy whose ``request.json`` omits ``op`` for legacy op runners."""

    inner: StoryCase
    request_without_op: dict[str, Any]

    @property
    def family(self) -> str:
        return self.inner.family

    @property
    def model(self) -> str:
        return self.inner.model

    @property
    def version(self) -> str:
        return self.inner.version

    @property
    def story_id(self) -> str:
        return self.inner.story_id

    @property
    def adapter(self) -> str:
        return self.inner.adapter

    @property
    def root(self) -> Any:
        return self.inner.root

    @property
    def label(self) -> str:
        return self.inner.label

    def path(self, name: str) -> Any:
        return self.inner.path(name)

    def load_json(self, name: str) -> dict[str, Any]:
        if name == "request.json":
            return self.request_without_op
        return self.inner.load_json(name)


@dataclass
class OpDispatchHarness:
    """Harness family that dispatches ``request.op`` to registered op runners.

    Used for interim domain migration: ops are the former story ``kind`` strings.
    ``request.json`` must include ``op``; remaining keys are forwarded as the
    request body (``op`` stripped) so ``model_validate(request)`` still works.
    """

    name: str
    ops: dict[str, StoryOpRunner]

    def known_ops(self) -> frozenset[str]:
        return frozenset(self.ops)

    async def run(self, case: StoryCase, backend: StoryBackend) -> None:
        request = case.load_json("request.json")
        op, inputs = split_request(request)
        try:
            runner = self.ops[op]
        except KeyError as exc:
            known = ", ".join(sorted(self.ops))
            raise ValueError(
                f"{case.label}: unknown op {op!r} for harness {self.name!r}; "
                f"known: {known}"
            ) from exc
        await runner(StrippedRequestCase(case, inputs), backend)  # type: ignore[arg-type]
