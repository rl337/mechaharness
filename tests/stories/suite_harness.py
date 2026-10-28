"""Run a user-story suite: shared hooks/vars, parallel or sequential stages."""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mechaharness.coding_workspace_checkpoint import save_coding_workspace_checkpoint
from mechaharness.run_timing import announce_timing, append_timing, inference_budget_fields
from tests.stories.backend import StoryBackend
from tests.stories.harness import run_story
from tests.stories.live_capability import live_eligible
from tests.stories.suite_catalog import resolve_stage_story_case
from tests.stories.suite_run import SuiteRunState, resolve_suite_run, stages_to_run
from tests.stories.suite_spec import SuiteSpec


@dataclass
class SuiteRunContext:
    """Mutable suite environment (workspace + merged vars)."""

    suite: SuiteSpec
    workspace: Path | None = None
    vars: dict[str, Any] = field(default_factory=dict)
    run: SuiteRunState | None = None
    _temp_workspace: tempfile.TemporaryDirectory[str] | None = None
    _persist_workspace: bool = False

    def close(self) -> None:
        # Persisted suite runs keep workspace on disk for MECHA_SUITE_RUN_ID resume.
        if self._persist_workspace:
            return
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
    from tests.stories.harness.user_story import (
        live_http_post_count,
        reset_live_http_post_count,
    )
    from tests.stories.live_capability import live_eligible, scenario_local_work

    ctx = SuiteRunContext(suite=suite, vars=dict(suite.vars))
    if suite.workspace is not None and suite.workspace != "temp":
        ctx.workspace = Path(suite.workspace)
    live_coding_stages = 0
    if backend.mode == "live":
        reset_live_http_post_count()
        for stage in suite.stages:
            try:
                case = resolve_stage_story_case(stage, model_filter=backend.model_filter)
            except LookupError:
                continue
            if live_eligible(case) and scenario_local_work(case) == "project_coding":
                live_coding_stages += 1
    try:
        if suite.execution.mode == "sequential":
            # Sequential arcs always get a durable run id + workspace under
            # .mechaharness/suite_runs (even when suite.workspace is "temp").
            ctx.run = resolve_suite_run(suite)
            ctx.workspace = ctx.run.workspace
            ctx._persist_workspace = True
            # ensure_workspace is satisfied by the persisted run workspace.
            _run_hooks(
                [h for h in suite.setup if h != "ensure_workspace"],
                ctx,
            )
            await _run_sequential(suite, backend, ctx)
        else:
            _run_hooks(suite.setup, ctx)
            await _run_parallel(suite, backend, ctx)
        if backend.mode == "live" and live_coding_stages > 0:
            posts = live_http_post_count()
            if posts < 1:
                raise AssertionError(
                    f"suite {suite.id!r}: expected live HTTP POSTs for "
                    f"{live_coding_stages} project_coding stage(s); got {posts}"
                )
    finally:
        try:
            _run_hooks(suite.cleanup, ctx)
        finally:
            ctx.close()


async def _run_parallel(
    suite: SuiteSpec, backend: StoryBackend, ctx: SuiteRunContext
) -> None:
    """Isolated stage runs; collect all failures (order not required)."""
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
            # Parallel stages do not share workspace; ignore suite ctx path.
            await run_story(case, backend, suite_workspace=None)
        except Exception as exc:  # noqa: BLE001 — collect then fail suite
            errors.append(f"{stage.story}/{stage.scenario}: {exc}")
    if errors:
        joined = "\n".join(f"  - {e}" for e in errors)
        raise AssertionError(
            f"suite {suite.id!r} failed {len(errors)} stage(s):\n{joined}"
        )
    _ = ctx


async def _run_sequential(
    suite: SuiteSpec, backend: StoryBackend, ctx: SuiteRunContext
) -> None:
    """Shared workspace; stop on first failure (remaining = prerequisite failed)."""
    if ctx.workspace is None:
        raise AssertionError(
            f"suite {suite.id!r}: sequential mode requires a suite run workspace "
            "(ensure_workspace / MECHA_SUITE_RUN_ID)"
        )
    run = ctx.run
    pending = stages_to_run(suite, run) if run is not None else list(
        enumerate(suite.stages)
    )
    if run is not None and not pending:
        # All stages already completed for this run id.
        return
    if run is not None:
        append_timing(
            run.workspace,
            kind="suite_start",
            suite_id=suite.id,
            run_id=run.run_id,
            backend=backend.mode,
            **inference_budget_fields(),
        )
    for index, stage in pending:
        stage_key = f"{stage.story}/{stage.scenario}"
        try:
            case = resolve_stage_story_case(stage, model_filter=backend.model_filter)
        except LookupError as exc:
            raise AssertionError(str(exc)) from exc
        if backend.mode == "live" and not live_eligible(case):
            if run is not None:
                run.mark_completed(stage)
                append_timing(
                    run.workspace,
                    kind="suite_stage",
                    stage=stage_key,
                    status="skipped_live_ineligible",
                    elapsed_s=0.0,
                )
            continue
        if run is not None:
            run.snapshot_workspace(stage)
        announce_timing(f" STAGE START  {stage_key}")
        t0 = time.perf_counter()
        try:
            await run_story(case, backend, suite_workspace=ctx.workspace)
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            if run is not None:
                run.mark_failed(stage)
                append_timing(
                    run.workspace,
                    kind="suite_stage",
                    stage=stage_key,
                    status="failed",
                    elapsed_s=elapsed,
                    error=str(exc)[:500],
                )
            announce_timing(f" STAGE FAIL   {stage_key}  {elapsed:.1f}s")
            remaining = suite.stages[index + 1 :]
            skip_note = ""
            if remaining:
                names = ", ".join(f"{s.story}/{s.scenario}" for s in remaining)
                skip_note = f" (skipped remaining stages: {names})"
            run_note = ""
            if run is not None:
                run_note = (
                    f"\n suite_run_id={run.run_id}"
                    f"\n resume: MECHA_SUITE_RUN_ID={run.run_id} "
                    f"MECHA_SUITE_FROM={stage.story}/{stage.scenario}"
                    f"\n timing: {run.root / 'TIMING.jsonl'}"
                )
            raise AssertionError(
                f"suite {suite.id!r} stage {stage.story}/{stage.scenario} "
                f"failed{skip_note}: {exc}{run_note}"
            ) from exc
        elapsed = time.perf_counter() - t0
        announce_timing(f" STAGE OK     {stage_key}  {elapsed:.1f}s")
        if run is not None:
            run.mark_completed(stage)
            append_timing(
                run.workspace,
                kind="suite_stage",
                stage=stage_key,
                status="ok",
                elapsed_s=elapsed,
            )
            # Advance coding escalate baseline to this green workspace so the
            # next stage (or mid-stage restore) does not rewind to empty 010.
            save_coding_workspace_checkpoint(run.workspace)


__all__ = [
    "SuiteRunContext",
    "run_user_story_suite",
]
