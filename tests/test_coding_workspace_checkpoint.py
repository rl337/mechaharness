"""Coding workspace filesystem checkpoint save / restore / empty-guard."""

from __future__ import annotations

from pathlib import Path

from mechaharness.coding_workspace_checkpoint import (
    coding_workspace_checkpoint_dir,
    restore_coding_workspace_checkpoint,
    save_coding_workspace_checkpoint,
)


def test_save_overwrites_prior_checkpoint(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "a.txt").write_text("one\n", encoding="utf-8")
    save_coding_workspace_checkpoint(ws)
    ck = coding_workspace_checkpoint_dir(ws)
    assert (ck / "a.txt").read_text(encoding="utf-8") == "one\n"

    (ws / "a.txt").write_text("two\n", encoding="utf-8")
    (ws / "b.txt").write_text("new\n", encoding="utf-8")
    save_coding_workspace_checkpoint(ws)
    assert (ck / "a.txt").read_text(encoding="utf-8") == "two\n"
    assert (ck / "b.txt").read_text(encoding="utf-8") == "new\n"


def test_restore_replaces_workspace_from_checkpoint(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "calc.py").write_text("good\n", encoding="utf-8")
    save_coding_workspace_checkpoint(ws)
    (ws / "calc.py").write_text("trash\n", encoding="utf-8")
    (ws / "extra.py").write_text("x\n", encoding="utf-8")

    assert restore_coding_workspace_checkpoint(ws) is True
    assert (ws / "calc.py").read_text(encoding="utf-8") == "good\n"
    assert not (ws / "extra.py").exists()


def test_restore_refuses_empty_checkpoint_over_nonempty_workspace(
    tmp_path: Path,
) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "calc.py").write_text("keep\n", encoding="utf-8")
    # Simulate the old once-at-empty-010 checkpoint.
    ck = coding_workspace_checkpoint_dir(ws)
    ck.mkdir(parents=True)
    assert restore_coding_workspace_checkpoint(ws) is False
    assert (ws / "calc.py").read_text(encoding="utf-8") == "keep\n"


def test_suite_style_success_advances_baseline(tmp_path: Path) -> None:
    """After stage N success, escalate restore on N+1 uses green N tree."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    # Stage 010-ish: empty then write.
    save_coding_workspace_checkpoint(ws)  # empty (suite start mistake)
    (ws / "calc.py").write_text("def evaluate(e): return 1\n", encoding="utf-8")
    save_coding_workspace_checkpoint(ws)  # after successful stage

    (ws / "calc.py").write_text("return eval(e)\n", encoding="utf-8")
    assert restore_coding_workspace_checkpoint(ws) is True
    assert "evaluate" in (ws / "calc.py").read_text(encoding="utf-8")
