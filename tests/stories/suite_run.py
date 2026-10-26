"""Suite run ids: persist sequential workspace + resume from a stage.

Env:

- ``MECHA_SUITE_RUN_ID`` — resume an existing run (required with ``MECHA_SUITE_FROM``
  when you need the prior workspace).
- ``MECHA_SUITE_FROM`` — stage to (re)start: ``story/scenario``, ``scenario``, or
  0-based index. Earlier stages are skipped; workspace is kept as-is.
- ``MECHA_SUITE_RUNS_DIR`` — root for run dirs (default ``.mechaharness/suite_runs``).

Each run writes ``<runs_dir>/<run_id>/`` with ``manifest.json``, ``RUN_ID.txt``,
and ``workspace/``. Pointers ``LATEST`` and ``<suite_id>.latest`` name the run id.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from tests.stories.suite_spec import SuiteSpec, SuiteStage

_STAGE_SEP = "/"


@dataclass
class SuiteRunState:
    """On-disk suite run: id, workspace, and completed stage keys."""

    run_id: str
    suite_id: str
    root: Path
    workspace: Path
    completed_stages: list[str] = field(default_factory=list)
    failed_stage: str | None = None
    created_at: str = ""
    updated_at: str = ""
    resumed: bool = False
    from_stage: str | None = None

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    def stage_key(self, stage: SuiteStage) -> str:
        return f"{stage.story}{_STAGE_SEP}{stage.scenario}"

    def save(self) -> None:
        self.updated_at = _utc_now()
        payload = {
            "run_id": self.run_id,
            "suite_id": self.suite_id,
            "workspace": str(self.workspace),
            "completed_stages": list(self.completed_stages),
            "failed_stage": self.failed_stage,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "from_stage": self.from_stage,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.root / "RUN_ID.txt").write_text(self.run_id + "\n", encoding="utf-8")
        _write_latest_pointers(self.root.parent, self.suite_id, self.run_id)

    def mark_completed(self, stage: SuiteStage) -> None:
        key = self.stage_key(stage)
        if key not in self.completed_stages:
            self.completed_stages.append(key)
        self.failed_stage = None
        self.save()

    def mark_failed(self, stage: SuiteStage) -> None:
        self.failed_stage = self.stage_key(stage)
        self.save()

    def snapshot_dir(self, stage: SuiteStage) -> Path:
        safe = self.stage_key(stage).replace("/", "__")
        return self.root / "stage_snapshots" / safe

    def snapshot_workspace(self, stage: SuiteStage) -> Path:
        """Copy workspace → stage snapshot (stage-start handoff for resume)."""
        dest = self.snapshot_dir(stage)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        if self.workspace.is_dir():
            for path in self.workspace.iterdir():
                target = dest / path.name
                if path.is_dir():
                    shutil.copytree(path, target)
                else:
                    shutil.copy2(path, target)
        return dest

    def restore_workspace(self, stage: SuiteStage) -> bool:
        """Restore workspace from stage-start snapshot if present."""
        src = self.snapshot_dir(stage)
        if not src.is_dir():
            return False
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        for path in src.iterdir():
            target = self.workspace / path.name
            if path.is_dir():
                shutil.copytree(path, target)
            else:
                shutil.copy2(path, target)
        return True


def suite_runs_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    raw = (os.environ.get("MECHA_SUITE_RUNS_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.cwd() / ".mechaharness" / "suite_runs").resolve()


def resolve_suite_run(
    suite: SuiteSpec,
    *,
    runs_dir: Path | None = None,
) -> SuiteRunState:
    """Create or resume a suite run; print a conspicuous banner."""
    root_dir = suite_runs_dir(runs_dir)
    root_dir.mkdir(parents=True, exist_ok=True)
    requested = (os.environ.get("MECHA_SUITE_RUN_ID") or "").strip()
    from_raw = (os.environ.get("MECHA_SUITE_FROM") or "").strip() or None

    if requested:
        state = _load_run(root_dir, requested, suite_id=suite.id)
        state.resumed = True
        state.from_stage = from_raw
        if from_raw:
            start = resolve_stage_index(suite, from_raw)
            # Drop completion marks from the resume point onward so those stages re-run.
            keep = {
                f"{s.story}{_STAGE_SEP}{s.scenario}"
                for s in suite.stages[:start]
            }
            state.completed_stages = [
                k for k in state.completed_stages if k in keep
            ]
            state.failed_stage = None
            # Prefer stage-start snapshot so a failed attempt's trash is not reused.
            restored = state.restore_workspace(suite.stages[start])
            if restored:
                sys.stdout.write(
                    f" Restored workspace from stage snapshot "
                    f"{state.stage_key(suite.stages[start])}\n"
                )
                sys.stdout.flush()
        state.save()
        _announce(state, suite)
        return state

    if from_raw:
        raise AssertionError(
            "MECHA_SUITE_FROM requires MECHA_SUITE_RUN_ID so the shared "
            "workspace from the prior run is reused. Look for the banner "
            f"or {root_dir}/<suite>.latest / LATEST."
        )

    run_id = _new_run_id(suite.id)
    root = root_dir / run_id
    workspace = root / "workspace"
    now = _utc_now()
    state = SuiteRunState(
        run_id=run_id,
        suite_id=suite.id,
        root=root,
        workspace=workspace,
        completed_stages=[],
        failed_stage=None,
        created_at=now,
        updated_at=now,
        resumed=False,
        from_stage=None,
    )
    state.save()
    _announce(state, suite)
    return state


def resolve_stage_index(suite: SuiteSpec, raw: str) -> int:
    """Map ``MECHA_SUITE_FROM`` to a stage index."""
    text = raw.strip()
    if not text:
        raise AssertionError("MECHA_SUITE_FROM is empty")
    if text.isdigit():
        index = int(text)
        if index < 0 or index >= len(suite.stages):
            raise AssertionError(
                f"MECHA_SUITE_FROM index {index} out of range "
                f"0..{len(suite.stages) - 1} for suite {suite.id!r}"
            )
        return index
    # story/scenario or bare scenario stem
    if _STAGE_SEP in text:
        story, scenario = text.split(_STAGE_SEP, 1)
        for index, stage in enumerate(suite.stages):
            if stage.story == story and stage.scenario == scenario:
                return index
        raise AssertionError(
            f"MECHA_SUITE_FROM={text!r} not found in suite {suite.id!r}"
        )
    matches = [
        index
        for index, stage in enumerate(suite.stages)
        if stage.scenario == text or stage.story == text
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise AssertionError(
            f"MECHA_SUITE_FROM={text!r} not found in suite {suite.id!r}"
        )
    raise AssertionError(
        f"MECHA_SUITE_FROM={text!r} is ambiguous in suite {suite.id!r}; "
        "use story/scenario or a numeric index"
    )


def stages_to_run(suite: SuiteSpec, state: SuiteRunState) -> list[tuple[int, SuiteStage]]:
    """Stages still due: after FROM (if any) and not already completed."""
    start = 0
    if state.from_stage:
        start = resolve_stage_index(suite, state.from_stage)
    out: list[tuple[int, SuiteStage]] = []
    for index, stage in enumerate(suite.stages):
        if index < start:
            continue
        key = state.stage_key(stage)
        if key in state.completed_stages:
            continue
        out.append((index, stage))
    return out


def _load_run(root_dir: Path, run_id: str, *, suite_id: str) -> SuiteRunState:
    root = root_dir / run_id
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise AssertionError(
            f"unknown suite run id {run_id!r}; expected {manifest_path}. "
            f"Check {root_dir}/LATEST or {root_dir}/{suite_id}.latest"
        )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"corrupt suite run manifest: {manifest_path}")
    stored_suite = str(data.get("suite_id") or "")
    if stored_suite and stored_suite != suite_id:
        raise AssertionError(
            f"suite run {run_id!r} belongs to suite {stored_suite!r}, "
            f"not {suite_id!r}"
        )
    workspace_raw = data.get("workspace")
    workspace = (
        Path(str(workspace_raw))
        if workspace_raw
        else root / "workspace"
    )
    completed = data.get("completed_stages") or []
    if not isinstance(completed, list):
        completed = []
    return SuiteRunState(
        run_id=run_id,
        suite_id=suite_id,
        root=root,
        workspace=workspace,
        completed_stages=[str(x) for x in completed],
        failed_stage=(
            str(data["failed_stage"]) if data.get("failed_stage") else None
        ),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
    )


def _new_run_id(suite_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", suite_id).strip("-") or "suite"
    return f"{slug}-{stamp}-{uuid4().hex[:6]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_latest_pointers(runs_dir: Path, suite_id: str, run_id: str) -> None:
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "LATEST").write_text(run_id + "\n", encoding="utf-8")
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", suite_id).strip("-") or "suite"
    (runs_dir / f"{safe}.latest").write_text(run_id + "\n", encoding="utf-8")


def _announce(state: SuiteRunState, suite: SuiteSpec) -> None:
    mode = "RESUME" if state.resumed else "START"
    lines = [
        "",
        "=" * 72,
        f" MECHA SUITE RUN  [{mode}]  suite={suite.id}",
        f" run_id={state.run_id}",
        f" root={state.root}",
        f" workspace={state.workspace}",
        f" manifest={state.manifest_path}",
        f" timing={state.root / 'TIMING.jsonl'}",
        f" completed={len(state.completed_stages)}/{len(suite.stages)}"
        + (f"  from={state.from_stage}" if state.from_stage else ""),
        " Rerun from a stage:",
        f"   MECHA_SUITE_RUN_ID={state.run_id} \\",
        "   MECHA_SUITE_FROM=<story/scenario|scenario|index> \\",
        "   pytest -q tests/stories/test_user_story_suites.py -k "
        f"{suite.id}",
        "=" * 72,
        "",
    ]
    text = "\n".join(lines)
    # stdout (visible with pytest -s) + warning (visible under default capture).
    sys.stdout.write(text)
    sys.stdout.flush()
    warnings.warn(
        f"suite run_id={state.run_id} root={state.root} "
        f"(cat {state.root.parent / 'LATEST'}; resume with "
        f"MECHA_SUITE_RUN_ID={state.run_id})",
        UserWarning,
        stacklevel=2,
    )
    try:
        (state.root / "BANNER.txt").write_text(text, encoding="utf-8")
    except OSError:
        pass


def manifest_public_fields(state: SuiteRunState) -> dict[str, Any]:
    """Small dict for tests / debugging."""
    return {
        "run_id": state.run_id,
        "suite_id": state.suite_id,
        "workspace": str(state.workspace),
        "completed_stages": list(state.completed_stages),
        "failed_stage": state.failed_stage,
        "resumed": state.resumed,
        "from_stage": state.from_stage,
    }


__all__ = [
    "SuiteRunState",
    "manifest_public_fields",
    "resolve_stage_index",
    "resolve_suite_run",
    "stages_to_run",
    "suite_runs_dir",
]
