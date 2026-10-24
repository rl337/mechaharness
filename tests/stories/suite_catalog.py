"""Discover and validate user-story suites under fixture trees (YAML SSOT)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tests.stories.catalog import FIXTURES_ROOT, StoryCase, iter_story_cases
from tests.stories.suite_author import SuiteAuthorSpec
from tests.stories.suite_spec import SuiteSpec, SuiteStage

KNOWN_SUITE_HOOKS = frozenset({"ensure_workspace"})


@dataclass(frozen=True)
class SuiteCase:
    """One loaded suite under a model version tree."""

    family: str
    model: str
    version: str
    suite: SuiteSpec
    root: Path

    @property
    def suite_id(self) -> str:
        return self.suite.id

    @property
    def label(self) -> str:
        return f"{self.family}/{self.model}/{self.version}/{self.suite_id}"


def suites_root_for(version_dir: Path) -> Path:
    return version_dir / "suites"


def static_suites_root() -> Path:
    return FIXTURES_ROOT / "static" / "fixture" / "v1" / "suites"


def load_suite_author(path: Path) -> SuiteAuthorSpec:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        return SuiteAuthorSpec.model_validate(data)
    except Exception as exc:
        raise ValueError(f"{path}: invalid suite.yaml: {exc}") from exc


def discover_stage_rows(suite_dir: Path) -> list[SuiteStage]:
    """Lexicographic stages from ``stages/*.yaml`` (natural name order)."""
    stages_dir = suite_dir / "stages"
    if not stages_dir.is_dir():
        return []
    rows: list[SuiteStage] = []
    for yaml_path in sorted(stages_dir.glob("*.yaml")):
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        story_id = str(data.get("id") or yaml_path.stem)
        rows.append(SuiteStage(story=story_id, scenario=yaml_path.stem))
    return rows


def author_to_suite_spec(author: SuiteAuthorSpec, stages: list[SuiteStage]) -> SuiteSpec:
    if not stages:
        raise ValueError(f"suite {author.id!r}: no stages under stages/")
    return SuiteSpec(
        id=author.id,
        title=author.title,
        persona=author.persona,
        execution=author.execution,
        vars=author.vars,
        setup=author.setup,
        cleanup=author.cleanup,
        workspace=author.workspace,
        stages=stages,
    )


def load_suite_dir(suite_dir: Path) -> SuiteSpec:
    """Load authored suite.yaml + discover stages (preferred).

    Falls back to suite.json when suite.yaml is missing (transition).
    """
    author_path = suite_dir / "suite.yaml"
    if author_path.is_file():
        author = load_suite_author(author_path)
        if author.id != suite_dir.name:
            raise ValueError(
                f"{author_path}: directory name {suite_dir.name!r} != id {author.id!r}"
            )
        stages = discover_stage_rows(suite_dir)
        return author_to_suite_spec(author, stages)
    path = suite_dir / "suite.json"
    if not path.is_file():
        raise ValueError(f"{suite_dir}: missing suite.yaml (or legacy suite.json)")
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        suite = SuiteSpec.model_validate(data)
    except Exception as exc:
        raise ValueError(f"{path}: invalid suite.json: {exc}") from exc
    if suite.id != suite_dir.name:
        raise ValueError(
            f"{path}: directory name {suite_dir.name!r} != id {suite.id!r}"
        )
    return suite


def load_suite_json(path: Path) -> SuiteSpec:
    """Compatibility: load suite.json or suite.yaml sibling."""
    if path.name == "suite.json" and (path.parent / "suite.yaml").is_file():
        return load_suite_dir(path.parent)
    if path.name == "suite.yaml":
        return load_suite_dir(path.parent)
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        return SuiteSpec.model_validate(data)
    except Exception as exc:
        raise ValueError(f"{path}: invalid suite.json: {exc}") from exc


def generated_suite_json_payload(suite: SuiteSpec) -> dict[str, Any]:
    return {
        "id": suite.id,
        "title": suite.title,
        "persona": suite.persona,
        "execution": suite.execution.model_dump(),
        "vars": suite.vars,
        "setup": suite.setup,
        "cleanup": suite.cleanup,
        "workspace": suite.workspace,
        "stages": [s.model_dump() for s in suite.stages],
    }


def iter_suite_cases(*, model_filter: str | None = None) -> list[SuiteCase]:
    """Walk ``family/model/version/suites/*/`` (suite.yaml or suite.json)."""
    cases: list[SuiteCase] = []
    if not FIXTURES_ROOT.is_dir():
        return cases
    for manifest_path in sorted(FIXTURES_ROOT.glob("*/*/v*/manifest.json")):
        version_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        family = str(manifest["family"])
        model = str(manifest["model"])
        version = str(manifest.get("version") or version_dir.name)
        model_key = f"{family}/{model}"
        if model_filter and model_key != model_filter and model != model_filter:
            continue
        suites_dir = suites_root_for(version_dir)
        if not suites_dir.is_dir():
            continue
        for suite_dir in sorted(p for p in suites_dir.iterdir() if p.is_dir()):
            if not (suite_dir / "suite.yaml").is_file() and not (
                suite_dir / "suite.json"
            ).is_file():
                continue
            suite = load_suite_dir(suite_dir)
            cases.append(
                SuiteCase(
                    family=family,
                    model=model,
                    version=version,
                    suite=suite,
                    root=suite_dir,
                )
            )
    return cases


def _scenario_stem(case: StoryCase) -> str | None:
    if case.scenario_relpath is None:
        return None
    return Path(case.scenario_relpath).stem


def static_story_scenario_keys() -> set[tuple[str, str]]:
    """All ``(story_id, scenario_stem)`` under ``static/fixture`` suite stages."""
    keys: set[tuple[str, str]] = set()
    for case in iter_story_cases():
        if "static/fixture" not in case.root.as_posix():
            continue
        if case.suite_id is None:
            continue
        stem = _scenario_stem(case)
        if stem is None:
            continue
        keys.add((case.story_id, stem))
    return keys


def suite_stage_keys(suites: list[SuiteSpec] | None = None) -> set[tuple[str, str]]:
    if suites is None:
        suites = [c.suite for c in iter_suite_cases()]
    return {(s.story, s.scenario) for suite in suites for s in suite.stages}


def is_static_suite_covered(case: StoryCase) -> bool:
    """True when this static fixture case is a suite stage."""
    if "static/fixture" not in case.root.as_posix():
        return False
    if case.suite_id is not None:
        return True
    stem = _scenario_stem(case)
    if stem is None:
        return False
    return (case.story_id, stem) in suite_stage_keys()


def resolve_stage_story_case(
    stage: SuiteStage,
    *,
    model_filter: str | None = None,
) -> StoryCase:
    """Resolve a suite stage to a StoryCase."""
    matches = [
        c
        for c in iter_story_cases()
        if c.story_id == stage.story and _scenario_stem(c) == stage.scenario
    ]
    if not matches:
        # Allow resolve by scenario stem alone when story id matches yaml id.
        matches = [
            c
            for c in iter_story_cases()
            if _scenario_stem(c) == stage.scenario
            and (c.story_id == stage.story or stage.scenario.endswith(stage.story))
        ]
    if not matches:
        raise LookupError(
            f"suite stage {stage.story!r}/{stage.scenario!r}: no story case"
        )
    if model_filter:
        filtered = [
            c
            for c in matches
            if c.model_key == model_filter or c.model == model_filter
        ]
        if filtered:
            return filtered[0]
    preferred = next(
        (c for c in matches if "static/fixture" in c.root.as_posix()),
        matches[0],
    )
    return preferred


def validate_suite_fixtures(*, require_full_static_coverage: bool = True) -> list[str]:
    """Validate suite schema, stage refs, exclusive membership, coverage."""
    errors: list[str] = []
    try:
        suite_cases = iter_suite_cases()
    except ValueError as exc:
        return [str(exc)]

    seen_ids: set[str] = set()
    for case in suite_cases:
        sid = case.suite.id
        if sid in seen_ids:
            errors.append(f"duplicate suite id {sid!r} at {case.root}")
        seen_ids.add(sid)
        for hook in [*case.suite.setup, *case.suite.cleanup]:
            if hook not in KNOWN_SUITE_HOOKS:
                errors.append(
                    f"{case.root}/suite.yaml: unknown hook {hook!r}; "
                    f"known: {sorted(KNOWN_SUITE_HOOKS)}"
                )
        if case.suite.workspace is not None and case.suite.execution.mode == "parallel":
            if not str(case.suite.workspace).strip():
                errors.append(
                    f"{case.root}/suite.yaml: workspace must be non-empty when set"
                )

    static_keys = static_story_scenario_keys()
    owned: dict[tuple[str, str], str] = {}
    for case in suite_cases:
        for stage in case.suite.stages:
            key = (stage.story, stage.scenario)
            prior = owned.get(key)
            if prior is not None and prior != case.suite.id:
                errors.append(
                    f"stage {stage.story!r}/{stage.scenario!r} in both "
                    f"{prior!r} and {case.suite.id!r}"
                )
            owned[key] = case.suite.id
            if key not in static_keys and case.family == "static":
                errors.append(
                    f"{case.root}: stage {stage.story!r}/{stage.scenario!r} "
                    f"has no stage YAML"
                )

    story_owners: dict[str, set[str]] = {}
    for case in suite_cases:
        for stage in case.suite.stages:
            story_owners.setdefault(stage.story, set()).add(case.suite.id)
    for story_id, owners in sorted(story_owners.items()):
        if len(owners) > 1:
            errors.append(
                f"story {story_id!r} appears in multiple suites: {sorted(owners)}"
            )

    if require_full_static_coverage:
        missing = sorted(static_keys - set(owned))
        for story, scenario in missing:
            errors.append(
                f"static story scenario {story!r}/{scenario!r} is not in any suite"
            )

    return errors


def suite_meta_for_guide() -> list[dict[str, Any]]:
    """Canonical suite summaries for the generated user-stories guide."""
    rows: list[dict[str, Any]] = []
    for case in iter_suite_cases():
        if case.family != "static":
            continue
        suite = case.suite
        story_ids = sorted({s.story for s in suite.stages})
        rows.append(
            {
                "id": suite.id,
                "title": suite.title,
                "persona": suite.persona,
                "mode": suite.execution.mode,
                "ordered": suite.execution.ordered,
                "stories": story_ids,
                "stage_count": len(suite.stages),
            }
        )
    return rows


__all__ = [
    "KNOWN_SUITE_HOOKS",
    "SuiteCase",
    "author_to_suite_spec",
    "discover_stage_rows",
    "generated_suite_json_payload",
    "is_static_suite_covered",
    "iter_suite_cases",
    "load_suite_author",
    "load_suite_dir",
    "load_suite_json",
    "resolve_stage_story_case",
    "static_suites_root",
    "static_story_scenario_keys",
    "suite_meta_for_guide",
    "suite_stage_keys",
    "validate_suite_fixtures",
]
