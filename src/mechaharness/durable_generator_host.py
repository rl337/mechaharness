"""Host-facing durable generator helpers (soft-point UI seam).

Thin orchestration over :class:`DurableGraphGenerator` for shipping hosts.
Prefer :mod:`mechaharness.durable_generator_script` for verb-led multi-step
sessions (CLI/TUI/story scripts). This module keeps guidance bindings and the
simple :func:`run_soft_point_session` loop.

See ``docs/reference/durable-graph-generators.md``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.durable_graph_generator import (
    DurableGraphGenerator,
    GraphYield,
    GuidanceResponse,
    RunInspection,
    ScriptedDriver,
    YieldKind,
)
from mechaharness.host_kit import host_durable_graph_generator


class GuidanceBinding(BaseModel):
    """One scripted (or future interactive) answer for an advice yield."""

    model_config = ConfigDict(extra="forbid")

    soft_point: str | None = None
    choose: str | None = None
    choice_id: str | None = None
    text: str | None = None
    request_id: str | None = None
    structured: dict[str, Any] = Field(default_factory=dict)

    def to_response(self, *, request_id: str = "") -> GuidanceResponse:
        cid = self.choice_id or self.choose
        return GuidanceResponse(
            request_id=self.request_id or request_id,
            choice_id=cid,
            text=self.text,
            structured=dict(self.structured or {}),
        )


class DurableSessionResult(BaseModel):
    """Stable session view for hosts and hard story checks."""

    model_config = ConfigDict(extra="forbid")

    yields: list[GraphYield] = Field(default_factory=list)
    recipe_ids: list[str] = Field(default_factory=list)
    inspect: RunInspection | None = None
    unexpected_advice_failed: bool = False
    stale_rejected: bool = False
    intruder_rejected: bool = False
    final_approval_rejected: bool = False

    @property
    def yield_kinds(self) -> list[YieldKind]:
        return [y.kind for y in self.yields]

    @property
    def final_kind(self) -> YieldKind | None:
        return self.yields[-1].kind if self.yields else None


def bindings_to_responses(
    bindings: list[GuidanceBinding] | list[dict[str, Any]],
) -> list[GuidanceResponse]:
    """Convert soft-point UI bindings to :class:`GuidanceResponse` list (order)."""
    out: list[GuidanceResponse] = []
    for item in bindings:
        binding = (
            item
            if isinstance(item, GuidanceBinding)
            else GuidanceBinding.model_validate(item)
        )
        out.append(binding.to_response())
    return out


def run_soft_point_session(
    generator: DurableGraphGenerator,
    recipe_id: str,
    inputs: dict[str, Any] | None = None,
    *,
    when_guidance: list[GuidanceBinding] | list[dict[str, Any]] | None = None,
    controller_id: str = "host",
    run_id: str | None = None,
    strict_unexpected_advice: bool = True,
    expected_kinds: list[YieldKind] | None = None,
) -> DurableSessionResult:
    """Run a recipe until terminal, answering ``advice_requested`` from bindings.

    Soft points are the UI seam: ``when_guidance`` is today's scripted binder;
    a curses/CLI host would supply the same answers interactively.
    """
    driver = ScriptedDriver(generator)
    unexpected_failed = False
    yields: list[GraphYield] = []
    try:
        yields = driver.run(
            recipe_id,
            inputs,
            controller_id=controller_id,
            responses=bindings_to_responses(when_guidance or []),
            expected_kinds=expected_kinds,
            strict_unexpected_advice=strict_unexpected_advice,
            run_id=run_id,
        )
    except AssertionError:
        if strict_unexpected_advice and not (when_guidance or []):
            unexpected_failed = True
        else:
            raise
    insp = None
    if yields:
        insp = generator.inspect(yields[0].run_id)
    recipes = [r.recipe_id for r in generator.list_recipes()]
    return DurableSessionResult(
        yields=yields,
        recipe_ids=recipes,
        inspect=insp,
        unexpected_advice_failed=unexpected_failed,
    )


def build_host_generator(
    *,
    run_store: Any | None = None,
    local_work: Any | None = None,
    event_log: Any | None = None,
) -> DurableGraphGenerator:
    """Blessed Config/DI path for a durable generator with the default recipe catalog."""
    return host_durable_graph_generator(
        run_store=run_store,
        local_work=local_work,
        event_log=event_log,
    )
