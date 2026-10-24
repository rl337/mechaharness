"""Materialize stage ``*.files.json`` from a suite ``sources/`` tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from pyiv.command import CLICommand

from tests.stories.suite_catalog import load_suite_author, static_suites_root


def _collect_tree(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = path.read_text(encoding="utf-8")
    return files


def _stage_source_dir(suite_dir: Path, stage_stem: str, sources_rel: str) -> Path | None:
    """Map ``010_slug`` → ``sources/00_…`` or ``sources/010_…`` when present."""
    sources = suite_dir / sources_rel
    if not sources.is_dir():
        return None
    # Prefer exact stem match, then numeric prefix match against child dirs/files.
    exact = sources / stage_stem
    if exact.is_dir():
        return exact
    # calc_cli: sources/00_parse_number.py (single file) — skip tree materialize
    # unless a directory exists.
    prefix = stage_stem.split("_", 1)[0]
    for child in sorted(sources.iterdir()):
        if child.is_dir() and (
            child.name.startswith(prefix) or child.name.endswith(stage_stem)
        ):
            return child
    return None


class MaterializeStageFilesCommand(CLICommand):
    """Rebuild ``stages/*.files.json`` from suite ``sources/`` when configured."""

    @classmethod
    def get_name(cls) -> str:
        return "materialize-stage-files"

    @classmethod
    def get_description(cls) -> str:
        return (
            "For suites with suite.yaml sources:, write stages/*.files.json "
            "from the matching sources tree (does not own narrative)."
        )

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="exit 1 if files.json drifts from sources/",
        )
        parser.add_argument(
            "--suite",
            action="append",
            default=None,
            help="limit to suite id (repeatable); default all with sources:",
        )

    def run(self) -> None:
        root = static_suites_root()
        wanted = set(self.args.suite or [])
        written = 0
        drifted = 0
        scanned = 0
        for suite_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            author_path = suite_dir / "suite.yaml"
            if not author_path.is_file():
                continue
            author = load_suite_author(author_path)
            if wanted and author.id not in wanted:
                continue
            if not author.sources:
                continue
            stages_dir = suite_dir / "stages"
            if not stages_dir.is_dir():
                continue
            for stage_path in sorted(stages_dir.glob("*.yaml")):
                data = yaml.safe_load(stage_path.read_text(encoding="utf-8")) or {}
                env = data.get("environment") if isinstance(data, dict) else None
                fs = env.get("filesystem") if isinstance(env, dict) else None
                contents = fs.get("contents") if isinstance(fs, dict) else None
                if not contents:
                    continue
                src_dir = _stage_source_dir(suite_dir, stage_path.stem, author.sources)
                if src_dir is None:
                    # Single-file sources (calc_cli) — leave existing files.json.
                    continue
                scanned += 1
                payload = _collect_tree(src_dir)
                text = json.dumps(payload, indent=2) + "\n"
                out = stages_dir / str(contents)
                if self.args.check:
                    if not out.is_file() or out.read_text(encoding="utf-8") != text:
                        print(f"drift: {out}")
                        drifted += 1
                    continue
                out.write_text(text, encoding="utf-8")
                written += 1

        if self.args.check:
            if drifted:
                print(f"{drifted} files.json out of date")
                self._exit_code = 1
                return
            print(f"ok: {scanned} stage files.json match sources/")
            self._exit_code = 0
            return

        print(f"wrote {written} files.json from sources/ ({scanned} trees)")
        self._exit_code = 0
