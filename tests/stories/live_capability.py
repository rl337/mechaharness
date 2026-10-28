"""Which story cases are meaningful under ``MECHA_STORY_BACKEND=live``.

Live is for catching cassette fantasy: HTTP twins plus static stories that
actually call a model (``infer`` / ``judge`` / ``judge_route``), and
``project_coding`` walks whose local-work Completer upgrades onto the real
reason lane (offline ``coding_write`` stubs are ignored in live mode).
"""

from __future__ import annotations

import yaml

from tests.stories.catalog import StoryCase

_LIVE_MODEL_VERBS = frozenset({"infer", "judge", "judge_route"})
_LIVE_EXCLUDE_VERBS = frozenset({"tool_loop"})


def scenario_verbs(case: StoryCase) -> frozenset[str]:
    """Product verbs named in the case's scenario YAML (if any)."""
    path = case.scenario_path()
    if path is None or not path.is_file():
        return frozenset()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    verbs: set[str] = set()
    for step in data.get("steps") or []:
        do = step.get("do") if isinstance(step, dict) else None
        if isinstance(do, dict):
            verbs.update(do)
    for cmd in data.get("commands") or []:
        if isinstance(cmd, dict):
            verbs.update(k for k in cmd if k not in {"expect", "expect_error"})
    return frozenset(verbs)


def scenario_backend(case: StoryCase) -> str | None:
    path = case.scenario_path()
    if path is None or not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    env = data.get("environment") if isinstance(data, dict) else None
    if isinstance(env, dict):
        backend = env.get("backend")
        return str(backend) if backend is not None else None
    return None


def scenario_local_work(case: StoryCase) -> str | None:
    """``environment.local_work`` from the scenario YAML, if set."""
    path = case.scenario_path()
    if path is None or not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    env = data.get("environment") if isinstance(data, dict) else None
    if isinstance(env, dict) and env.get("local_work") is not None:
        return str(env.get("local_work"))
    return None


def live_eligible(case: StoryCase) -> bool:
    """Return True when this case should be collected / run in live mode."""
    if case.adapter != "in_process":
        return True
    verbs = scenario_verbs(case)
    if verbs & _LIVE_EXCLUDE_VERBS:
        return False
    if scenario_backend(case) == "anthropic":
        # No Junespark Anthropic endpoint; keep cassette-only.
        return False
    if scenario_local_work(case) == "project_coding":
        # Live upgrades ProjectCodingLocalWork onto a real Completer.
        return True
    return bool(verbs & _LIVE_MODEL_VERBS)


def filter_live_cases(cases: list[StoryCase]) -> list[StoryCase]:
    return [c for c in cases if live_eligible(c)]
