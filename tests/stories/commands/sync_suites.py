"""Regenerate suite.json stage lists from suite.yaml + stages/*.yaml."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pyiv.command import CLICommand

from tests.stories.catalog import clear_story_case_cache
from tests.stories.suite_catalog import (
    generated_suite_json_payload,
    iter_suite_cases,
    load_suite_dir,
    static_suites_root,
    validate_suite_fixtures,
)


class SyncSuitesCommand(CLICommand):
    """Write or check generated ``suite.json`` from authored suite.yaml + stages."""

    @classmethod
    def get_name(cls) -> str:
        return "sync-suites"

    @classmethod
    def get_description(cls) -> str:
        return (
            "Regenerate suite.json stages from suite.yaml + lexicographic "
            "stages/*.yaml (natural name order)."
        )

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="exit 1 if suite.json drifts from discovered stages",
        )
        parser.add_argument(
            "--root",
            type=Path,
            default=None,
            help="suites root (default: static/fixture/v1/suites)",
        )

    def run(self) -> None:
        root: Path = self.args.root or static_suites_root()
        # Authoring rewrites stages on disk; drop discovery caches first.
        clear_story_case_cache()
        errors = validate_suite_fixtures(require_full_static_coverage=True)
        if errors:
            for err in errors:
                print(err)
            self._exit_code = 1
            return

        written = 0
        drifted = 0
        for case in iter_suite_cases():
            if self.args.root is not None and root not in case.root.parents and case.root != root:
                if not str(case.root).startswith(str(root)):
                    continue
            suite = load_suite_dir(case.root)
            payload = generated_suite_json_payload(suite)
            path = case.root / "suite.json"
            text = json.dumps(payload, indent=2) + "\n"
            if self.args.check:
                if not path.is_file() or path.read_text(encoding="utf-8") != text:
                    print(f"drift: {path}")
                    drifted += 1
                continue
            path.write_text(text, encoding="utf-8")
            written += 1

        if self.args.check:
            if drifted:
                print(f"{drifted} suite.json file(s) out of date")
                self._exit_code = 1
                return
            print(f"ok: suite.json matches stages under {root}")
            self._exit_code = 0
            return

        print(f"wrote {written} suite.json file(s) under {root}")
        self._exit_code = 0
