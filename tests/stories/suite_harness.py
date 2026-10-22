"""Run a user-story suite: shared hooks/vars, parallel or sequential stages."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.stories.backend import StoryBackend
from tests.stories.harness import run_story
from tests.stories.live_capability import live_eligible
from tests.stories.suite_catalog import resolve_stage_story_case
from tests.stories.suite_spec import SuiteSpec


@dataclass
class SuiteRunContext:
    """Mutable suite environment (workspace + merged vars)."""

    suite: SuiteSpec
    workspace: Path | None = None
    vars: dict[str, Any] = field(default_factory=dict)
    _temp_workspace: tempfile.TemporaryDirectory[str] | None = None

    def close(self) -> None:
        if self._temp_workspace is not None:
            self._temp_workspace.cleanup()
            self._temp_workspace = None


def _apply_hook(name: str, ctx: SuiteRunContext) -> None:
    if name == "ensure_workspace":
        if ctx.workspace is not None:
            ctx.workspace.mkdir(parents=True, exist_ok=True)
            return
        if ctx.suite.workspace == "temp" or ctx.suite.workspace is None:
            tmp = tempfile.TemporaryDirectory(prefix=f"mecha_suite_{ctx.suite.id}_")
            ctx._temp_workspace = tmp
            ctx.workspace = Path(tmp.name)
            return
        path = Path(ctx.suite.workspace)
        path.mkdir(parents=True, exist_ok=True)
        ctx.workspace = path
        return
    raise ValueError(f"unknown suite hook {name!r}")


def _run_hooks(names: list[str], ctx: SuiteRunContext) -> None:
    for name in names:
        _apply_hook(name, ctx)


async def run_user_story_suite(suite: SuiteSpec, backend: StoryBackend) -> None:
    """Execute suite stages under the resolved story backend."""
    ctx = SuiteRunContext(suite=suite, vars=dict(suite.vars))
    if suite.workspace is not None and suite.workspace != "temp":
        ctx.workspace = Path(suite.workspace)
    try:
        _run_hooks(suite.setup, ctx)
        if suite.execution.mode == "sequential":
            await _run_sequential(suite, backend, ctx)
        else:
            await _run_parallel(suite, backend, ctx)
    finally:
        try:
            _run_hooks(suite.cleanup, ctx)
        finally:
            ctx.close()


async def _run_parallel(
    suite: SuiteSpec, backend: StoryBackend, ctx: SuiteRunContext
) -> None:
    """Isolated stage runs; collect all failures (order not required)."""
    _ = ctx  # vars/workspace reserved for sequential arcs / future stage merge
    errors: list[str] = []
    for stage in suite.stages:
        try:
            case = resolve_stage_story_case(stage, model_filter=backend.model_filter)
        except LookupError as exc:
            errors.append(str(exc))
            continue
        if backend.mode == "live" and not live_eligible(case):
            continue
        try:
            await run_story(case, backend)
        except Exception as exc:  # noqa: BLE001 — collect then fail suite
            errors.append(f"{stage.story}/{stage.scenario}: {exc}")
    if errors:
        joined = "\n".join(f"  - {e}" for e in errors)
        raise AssertionError(
            f"suite {suite.id!r} failed {len(errors)} stage(s):\n{joined}"
        )


async def _run_sequential(
    suite: SuiteSpec, backend: StoryBackend, ctx: SuiteRunContext
) -> None:
    """Shared workspace; stop on first failure (remaining = prerequisite failed)."""
    _ = ctx
    for index, stage in enumerate(suite.stages):
        try:
            case = resolve_stage_story_case(stage, model_filter=backend.model_filter)
        except LookupError as exc:
            raise AssertionError(str(exc)) from exc
        if backend.mode == "live" and not live_eligible(case):
            continue
        try:
            await run_story(case, backend)
        except Exception as exc:
            remaining = suite.stages[index + 1 :]
            skip_note = ""
            if remaining:
                names = ", ".join(f"{s.story}/{s.scenario}" for s in remaining)
                skip_note = f" (skipped remaining stages: {names})"
            raise AssertionError(
                f"suite {suite.id!r} stage {stage.story}/{stage.scenario} "
                f"failed{skip_note}: {exc}"
            ) from exc


__all__ = [
    "SuiteRunContext",
    "run_user_story_suite",
]
