"""Select static vs live story backend from env (incl. legacy MECHA_LIVE_*)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

StoryMode = Literal["static", "live"]

CLOUD_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_CLOUD_OPENAI_MODEL = "gpt-6-luna"

# ``None`` default_model = live with no cassette model filter (cloud OpenAI).
_LEGACY_LIVE_MODELS: dict[str, str | None] = {
    "MECHA_LIVE_OPENAI": None,
    "MECHA_LIVE_OPENAI_COMPAT": "openai_compat/qwen3-30b-thinking",
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


STATIC_OPENAI_COMPAT_BASE_URL = "http://story.invalid/v1"
STATIC_OPENAI_COMPAT_API_KEY = "story"


def resolve_openai_story_api_key(*, static_fallback: str = STATIC_OPENAI_COMPAT_API_KEY) -> str:
    """Live credential helper: ``MECHA_API_KEY``, then ``OPENAI_API_KEY``.

    Static / cassette paths must not call this — use
    ``STATIC_OPENAI_COMPAT_API_KEY`` instead so operator secrets never
    influence offline runs.
    """
    return (
        os.environ.get("MECHA_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
        or static_fallback
    )


def wants_cloud_openai() -> bool:
    """True only when the operator explicitly opts into cloud OpenAI live."""
    if os.environ.get("MECHA_LIVE_OPENAI") == "1":
        return True
    return os.environ.get("MECHA_INFERENCE_BACKEND", "").strip().lower() == "openai"


def resolve_live_openai_compat_endpoint() -> tuple[str, str]:
    """Return ``(base_url, api_key)`` for **live** OpenAI-compat Completer wiring.

    Cloud OpenAI is used only when explicitly opted in (``MECHA_LIVE_OPENAI=1``
    or ``MECHA_INFERENCE_BACKEND=openai``) and ``MECHA_BASE_URL`` is unset.
    A bare ``OPENAI_API_KEY`` in the environment does **not** select cloud.
    """
    explicit_base = os.environ.get("MECHA_BASE_URL", "").strip()
    api_key = resolve_openai_story_api_key()
    if explicit_base and not wants_cloud_openai():
        return explicit_base, api_key
    if wants_cloud_openai():
        # Cloud opt-in ignores a leftover local MECHA_BASE_URL from env.sh.
        return CLOUD_OPENAI_BASE_URL, api_key
    if explicit_base:
        return explicit_base, api_key
    raise AssertionError(
        "MECHA_BASE_URL is required for live openai_compat stories "
        "(or set MECHA_LIVE_OPENAI=1 / MECHA_INFERENCE_BACKEND=openai for cloud)"
    )


def resolve_live_openai_compat_model(fallback: str) -> str:
    """Prefer ``MECHA_MODEL``, then ``fallback``, then Luna for cloud live."""
    explicit = os.environ.get("MECHA_MODEL", "").strip()
    if explicit:
        return explicit
    if fallback.strip():
        return fallback
    return DEFAULT_CLOUD_OPENAI_MODEL
