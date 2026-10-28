"""Suite run id resolve / resume / stage-from helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.stories.suite_run import (
    resolve_stage_index,
    resolve_suite_run,
    stages_to_run,
)
from tests.stories.suite_spec import SuiteExecution, SuiteSpec, SuiteStage


def _suite() -> SuiteSpec:
    return SuiteSpec(
        id="calc_cli",
        title="t",
        persona="fangore",
        execution=SuiteExecution(mode="sequential", ordered=True),
        workspace="temp",
        setup=["ensure_workspace"],
        stages=[
            SuiteStage(story="fangore_calc_parse_number", scenario="bootstrap"),
            SuiteStage(story="fangore_calc_add_sub", scenario="add_sub"),
            SuiteStage(story="fangore_calc_mul_div", scenario="mul_div"),
        ],
    )


def test_new_suite_run_writes_conspicuous_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("MECHA_SUITE_RUN_ID", raising=False)
    monkeypatch.delenv("MECHA_SUITE_FROM", raising=False)
    monkeypatch.setenv("MECHA_SUITE_RUNS_DIR", str(tmp_path))
    suite = _suite()
    state = resolve_suite_run(suite, runs_dir=tmp_path)
    out = capsys.readouterr().out
    assert "MECHA SUITE RUN" in out
    assert state.run_id in out
    assert (state.root / "RUN_ID.txt").read_text().strip() == state.run_id
    assert (state.root / "BANNER.txt").is_file()
    assert (tmp_path / "LATEST").read_text().strip() == state.run_id
    assert (tmp_path / "calc_cli.latest").read_text().strip() == state.run_id
    manifest = json.loads(state.manifest_path.read_text())
    assert manifest["suite_id"] == "calc_cli"
    assert state.workspace.is_dir()


def test_resume_from_stage_skips_prior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MECHA_SUITE_RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("MECHA_SUITE_RUN_ID", raising=False)
    monkeypatch.delenv("MECHA_SUITE_FROM", raising=False)
    suite = _suite()
    first = resolve_suite_run(suite, runs_dir=tmp_path)
    first.mark_completed(suite.stages[0])
    first.mark_completed(suite.stages[1])
    (first.workspace / "calc.py").write_text("print(1)\n", encoding="utf-8")

    monkeypatch.setenv("MECHA_SUITE_RUN_ID", first.run_id)
    monkeypatch.setenv("MECHA_SUITE_FROM", "mul_div")
    resumed = resolve_suite_run(suite, runs_dir=tmp_path)
    assert resumed.resumed is True
    assert resumed.run_id == first.run_id
    assert resumed.workspace == first.workspace
    assert (resumed.workspace / "calc.py").read_text() == "print(1)\n"
    # FROM clears completion from mul_div onward; prior stages stay marked.
    assert resumed.completed_stages == [
        "fangore_calc_parse_number/bootstrap",
        "fangore_calc_add_sub/add_sub",
    ]
    pending = stages_to_run(suite, resumed)
    assert len(pending) == 1
    assert pending[0][1].scenario == "mul_div"


def test_from_without_run_id_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MECHA_SUITE_RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("MECHA_SUITE_RUN_ID", raising=False)
    monkeypatch.setenv("MECHA_SUITE_FROM", "2")
    with pytest.raises(AssertionError, match="MECHA_SUITE_FROM requires"):
        resolve_suite_run(_suite(), runs_dir=tmp_path)


def test_resolve_stage_index_forms() -> None:
    suite = _suite()
    assert resolve_stage_index(suite, "0") == 0
    assert resolve_stage_index(suite, "2") == 2
    assert resolve_stage_index(suite, "mul_div") == 2
    assert resolve_stage_index(suite, "fangore_calc_add_sub/add_sub") == 1
    with pytest.raises(AssertionError, match="out of range"):
        resolve_stage_index(suite, "9")


def test_resume_continues_after_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MECHA_SUITE_RUNS_DIR", str(tmp_path))
    monkeypatch.delenv("MECHA_SUITE_FROM", raising=False)
    suite = _suite()
    first = resolve_suite_run(suite, runs_dir=tmp_path)
    first.mark_completed(suite.stages[0])
    monkeypatch.setenv("MECHA_SUITE_RUN_ID", first.run_id)
    resumed = resolve_suite_run(suite, runs_dir=tmp_path)
    pending = stages_to_run(suite, resumed)
    assert [s.scenario for _, s in pending] == ["add_sub", "mul_div"]
