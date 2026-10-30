"""Paths and discovery for versioned model story fixtures (YAML SSOT)."""

from __future__ import annotations

import functools
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tests.stories.scenarios.cli_scenario import load_cli_scenario
from tests.stories.scenarios.user_story_scenario import load_user_story_scenario

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "models"
REQUIRED_STORY_FIELDS = (
    "id",
    "persona",
    "title",
    "kind",
    "narrative",
    "implementation",
    "validation",
)
TWIN_PARITY_FIELDS = (
    "persona",
    "title",
    "kind",
    "narrative",
    "implementation",
    "validation",
    "footnotes",
)
_PROSE_KEYS = (
    "id",
    "suite",
    "persona",
    "title",
    "kind",
    "narrative",
    "implementation",
    "validation",
    "footnotes",
)


@dataclass(frozen=True)
class StoryCase:
    """One (model version, story[, scenario]) under ``tests/fixtures/models``.

    Suite stages live at ``suites/<suite>/stages/<stem>.yaml``. Twin / orphan
    cases live at ``stories/<id>/scenarios/<stem>.yaml``. Prose fields are in
    the YAML itself (no ``story.json``).
    """

    family: str
    model: str
    version: str
    story_id: str
    adapter: str
    root: Path
    scenario_relpath: str | None = None
    suite_id: str | None = None

    @property
    def model_key(self) -> str:
        return f"{self.family}/{self.model}"

    @property
    def label(self) -> str:
        base = f"{self.model_key}/{self.version}/{self.story_id}"
        if self.scenario_relpath:
            stem = Path(self.scenario_relpath).stem
            return f"{base}/{stem}"
        return base

    def asset_root(self) -> Path:
        """Directory for binds/plans/response.json (suite assets or story root)."""
        if self.suite_id is not None:
            suite_dir = self.root.parent  # …/suites/<id>/stages → suite
            base = self.story_id.split("__", 1)[0]
            for candidate in (
                suite_dir / "assets" / self.story_id,
                suite_dir / "assets" / base,
            ):
                if candidate.is_dir():
                    return candidate
        return self.root

    def path(self, name: str) -> Path:
        return self.asset_root() / name

    def scenario_path(self) -> Path | None:
        if self.scenario_relpath is None:
            return None
        return self.root / self.scenario_relpath

    def load_json(self, name: str) -> dict[str, Any]:
        import json

        return json.loads(self.path(name).read_text(encoding="utf-8"))

    def load_meta(self) -> dict[str, Any]:
        """Prose / kind fields from the stage or scenario YAML."""
        path = self.scenario_path()
        if path is None or not path.is_file():
            raise FileNotFoundError(f"{self.label}: missing scenario YAML")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path}: root must be a mapping")
        meta = {k: data.get(k) for k in _PROSE_KEYS if k in data or k == "footnotes"}
        if "footnotes" not in meta:
            meta["footnotes"] = data.get("footnotes") or []
        if "id" not in meta or not meta["id"]:
            meta["id"] = self.story_id
        return meta


def _load_manifest(manifest_path: Path) -> tuple[str, str, str, str]:
    import json

    version_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    family = str(manifest["family"])
    model = str(manifest["model"])
    version = str(manifest.get("version") or version_dir.name)
    adapter = str(manifest.get("adapter") or family)
    return family, model, version, adapter


def _discover_story_cases(*, model_filter: str | None = None) -> list[StoryCase]:
    """Walk suite stages and twin ``stories/*/scenarios/*.yaml`` trees."""
    cases: list[StoryCase] = []
    if not FIXTURES_ROOT.is_dir():
        return cases
    for manifest_path in sorted(FIXTURES_ROOT.glob("*/*/v*/manifest.json")):
        version_dir = manifest_path.parent
        family, model, version, adapter = _load_manifest(manifest_path)
        model_key = f"{family}/{model}"
        if model_filter and model_key != model_filter and model != model_filter:
            continue

        suites_dir = version_dir / "suites"
        if suites_dir.is_dir():
            for suite_dir in sorted(p for p in suites_dir.iterdir() if p.is_dir()):
                stages_dir = suite_dir / "stages"
                if not stages_dir.is_dir():
                    continue
                for yaml_path in sorted(stages_dir.glob("*.yaml")):
                    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                    story_id = str(data.get("id") or yaml_path.stem)
                    cases.append(
                        StoryCase(
                            family=family,
                            model=model,
                            version=version,
                            story_id=story_id,
                            adapter=adapter,
                            root=stages_dir,
                            scenario_relpath=yaml_path.name,
                            suite_id=suite_dir.name,
                        )
                    )

        stories_dir = version_dir / "stories"
        if stories_dir.is_dir():
            for story_dir in sorted(p for p in stories_dir.iterdir() if p.is_dir()):
                scenarios_dir = story_dir / "scenarios"
                if not scenarios_dir.is_dir():
                    continue
                for yaml_path in sorted(scenarios_dir.glob("*.yaml")):
                    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                    story_id = str(data.get("id") or story_dir.name)
                    cases.append(
                        StoryCase(
                            family=family,
                            model=model,
                            version=version,
                            story_id=story_id,
                            adapter=adapter,
                            root=story_dir,
                            scenario_relpath=f"scenarios/{yaml_path.name}",
                            suite_id=(
                                str(data["suite"])
                                if isinstance(data.get("suite"), str)
                                else None
                            ),
                        )
                    )
    return cases


@functools.lru_cache(maxsize=16)
def _iter_story_cases_cached(model_filter: str | None) -> tuple[StoryCase, ...]:
    """Cached discovery; fixtures are static for the life of a test process."""
    return tuple(_discover_story_cases(model_filter=model_filter))


def iter_story_cases(*, model_filter: str | None = None) -> list[StoryCase]:
    """Walk suite stages and twin ``stories/*/scenarios/*.yaml`` trees.

    Results are cached per ``model_filter``. Call ``clear_story_case_cache`` if
    fixtures change mid-process (rare; sync/authoring tools).
    """
    return list(_iter_story_cases_cached(model_filter))


def clear_story_case_cache() -> None:
    """Drop cached story / suite catalog indexes (after fixture rewrites)."""
    _iter_story_cases_cached.cache_clear()
    # Suite catalog indexes depend on this list; clear lazily via import.
    try:
        from tests.stories import suite_catalog as _suite_catalog
    except ImportError:
        return
    clear = getattr(_suite_catalog, "clear_suite_catalog_cache", None)
    if clear is not None:
        clear()


def _validate_footnotes(data: dict[str, Any], *, path: Path) -> list[str]:
    errors: list[str] = []
    footnotes = data.get("footnotes")
    if footnotes is None:
        errors.append(f"{path}: missing required field 'footnotes' (use [] if none)")
        return errors
    if not isinstance(footnotes, list):
        errors.append(f"{path}: footnotes must be a list")
        return errors
    seen: set[str] = set()
    for i, item in enumerate(footnotes):
        if not isinstance(item, dict):
            errors.append(f"{path}: footnotes[{i}] must be an object")
            continue
        fid = item.get("id")
        label = item.get("label")
        url = item.get("url")
        if not isinstance(fid, str) or not fid.strip():
            errors.append(f"{path}: footnotes[{i}].id must be a non-empty string")
            continue
        if fid in seen:
            errors.append(f"{path}: duplicate footnote id {fid!r}")
        seen.add(fid)
        if not isinstance(label, str) or not label.strip():
            errors.append(f"{path}: footnotes[{i}].label must be a non-empty string")
        if not isinstance(url, str) or not url.strip():
            errors.append(f"{path}: footnotes[{i}].url must be a non-empty string")
        note = item.get("note")
        if note is not None and not isinstance(note, str):
            errors.append(f"{path}: footnotes[{i}].note must be a string when set")
    return errors


def validate_story_payload(data: dict[str, Any], *, path: Path) -> list[str]:
    """Return human-readable errors for one stage/scenario prose payload."""
    errors: list[str] = []
    for field in REQUIRED_STORY_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{path}: missing or empty required field {field!r}")
    errors.extend(_validate_footnotes(data, path=path))
    return errors


def collect_canonical_stories() -> dict[str, dict[str, Any]]:
    """Return story_id -> prose meta, preferring static/fixture when present."""
    by_id: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for case in iter_story_cases():
        path = case.scenario_path()
        if path is None:
            continue
        data = case.load_meta()
        by_id[str(data.get("id") or case.story_id)].append((path, data))

    canonical: dict[str, dict[str, Any]] = {}
    for story_id, copies in sorted(by_id.items()):
        preferred = next(
            (data for path, data in copies if "static/fixture" in path.as_posix()),
            copies[0][1],
        )
        canonical[story_id] = preferred
    return canonical


def validate_story_fixtures() -> list[str]:
    """Validate required fields, twin parity, harness kinds, and YAML load."""
    from tests.stories.harness.registry import HARNESSES, known_ops_for

    errors: list[str] = []
    by_id: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    seen_cases: set[str] = set()
    for case in iter_story_cases():
        path = case.scenario_path()
        if path is None:
            errors.append(f"{case.label}: missing scenario path")
            continue
        try:
            data = case.load_meta()
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            continue
        errors.extend(validate_story_payload(data, path=path))
        by_id[str(data.get("id") or case.story_id)].append((path, data))

        kind = data.get("kind")
        case_key = f"{case.family}/{case.model}/{case.story_id}/{path.name}"
        if case_key in seen_cases:
            continue
        seen_cases.add(case_key)
        if not isinstance(kind, str) or not kind.strip():
            continue
        if kind not in HARNESSES:
            errors.append(
                f"{path}: kind {kind!r} is not a registered story harness; "
                f"known: {sorted(HARNESSES)}"
            )
            continue
        if kind in {"cli", "user_story"}:
            try:
                if kind == "user_story":
                    load_user_story_scenario(path)
                else:
                    load_cli_scenario(path)
            except (ValueError, OSError) as exc:
                errors.append(str(exc))
            continue
        req_path = case.path("request.json")
        if not req_path.is_file():
            errors.append(f"{req_path}: missing request.json (required for harness op)")
            continue
        request = case.load_json("request.json")
        op = request.get("op")
        ops = known_ops_for(kind) or frozenset()
        if not isinstance(op, str) or not op.strip():
            errors.append(
                f"{req_path}: missing non-empty string 'op' for harness {kind!r}"
            )
        elif op not in ops:
            errors.append(
                f"{req_path}: unknown op {op!r} for harness {kind!r}; "
                f"known: {sorted(ops)}"
            )

    for story_id, copies in sorted(by_id.items()):
        if len(copies) < 2:
            continue
        base = copies[0][1]
        for path, data in copies[1:]:
            for field in TWIN_PARITY_FIELDS:
                if data.get(field) != base.get(field):
                    errors.append(
                        f"twin drift for {story_id!r}: {field} differs at {path}"
                    )

    footnote_owners: dict[str, str] = {}
    for story_id, data in collect_canonical_stories().items():
        for item in data.get("footnotes") or []:
            if not isinstance(item, dict):
                continue
            fid = item.get("id")
            if not isinstance(fid, str):
                continue
            prior = footnote_owners.get(fid)
            if prior is not None and prior != story_id:
                errors.append(
                    f"footnote id {fid!r} used by both {prior!r} and {story_id!r}"
                )
            footnote_owners[fid] = story_id

    return errors
