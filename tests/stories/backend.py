"""Select static vs live story backend from env (incl. legacy MECHA_LIVE_*)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

StoryMode = Literal["static", "live"]

_LEGACY_LIVE_MODELS: dict[str, str] = {
    "MECHA_LIVE_JUNESPARK": "openai_compat/qwen3-30b-thinking",
    "MECHA_LIVE_QWEN": "openai_compat/qwen-qwen3.6-35b-a3b",
    "MECHA_LIVE_JUDGE": "systemone/laya",
    "MECHA_LIVE_DECIDE": "systemone/laya",
}


@dataclass(frozen=True)
class StoryBackend:
    mode: StoryMode
    model_filter: str | None = None


def resolve_story_backend() -> StoryBackend:
    """Resolve dual-mode settings.

    Precedence:
    1. ``MECHA_STORY_BACKEND`` / ``MECHA_STORY_MODEL``
    2. Legacy ``MECHA_LIVE_*`` (implies live + default model for that alias)
    3. Default ``static`` with no model filter (all fixtures)
    """
    explicit = os.environ.get("MECHA_STORY_BACKEND", "").strip().lower()
    model = os.environ.get("MECHA_STORY_MODEL", "").strip() or None

    if explicit in ("static", "live"):
        return StoryBackend(mode=explicit, model_filter=model)  # type: ignore[arg-type]

    for env_name, default_model in _LEGACY_LIVE_MODELS.items():
        if os.environ.get(env_name) == "1":
            return StoryBackend(mode="live", model_filter=model or default_model)

    return StoryBackend(mode="static", model_filter=model)
