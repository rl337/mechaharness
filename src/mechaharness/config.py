"""Settings loaded from environment / .env for CLI and API."""

from __future__ import annotations

from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment / ``.env`` (``MECHA_`` prefix).

    Used by the CLI, HTTP API, and ``SettingsConfig``. Hosts that construct
    strategies directly may pass a ``Settings`` instance into constructors.

    Judge-lane connection: prefer ``MECHA_JUDGE_*``. Legacy ``MECHA_DECIDE_*``
    names are accepted as aliases for one migration window.
    """

    model_config = SettingsConfigDict(env_prefix="MECHA_", env_file=".env", extra="ignore")

    inference_backend: str = "openai"
    harness_family: str = "tool_loop"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    base_url: str | None = None
    # Judge lane (System One / future hosted judge APIs)
    judge_base_url: str | None = None
    judge_model: str | None = None
    judge_path: str = "/v1/systemone"
    judge_url: str | None = None
    judge_api_key: str | None = None
    judge_timeout_seconds: float = 60.0
    # Legacy env aliases (MECHA_DECIDE_*) — copied into judge_* when unset
    decide_base_url: str | None = None
    decide_model: str | None = None
    system_prompt: str | None = None
    max_turns: int = 8
    temperature: float | None = None
    max_tokens: int | None = None
    host: str = "127.0.0.1"
    port: int = 8080

    @model_validator(mode="before")
    @classmethod
    def _migrate_decide_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if out.get("judge_base_url") in (None, "") and out.get("decide_base_url"):
            out["judge_base_url"] = out["decide_base_url"]
        if out.get("judge_model") in (None, "") and out.get("decide_model"):
            out["judge_model"] = out["decide_model"]
        return out


def get_settings() -> Settings:
    """Load ``Settings`` from the current process environment."""
    return Settings()
