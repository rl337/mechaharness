"""Settings loaded from environment / .env for CLI and API."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment / ``.env`` (``MECHA_`` prefix).

    Used by the CLI, HTTP API, and ``SettingsConfig``. Hosts that construct
    strategies directly may pass a ``Settings`` instance into constructors.
    """

    model_config = SettingsConfigDict(env_prefix="MECHA_", env_file=".env", extra="ignore")

    inference_backend: str = "openai"
    harness_family: str = "tool_loop"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    base_url: str | None = None
    decide_base_url: str | None = None
    decide_model: str | None = None
    system_prompt: str | None = None
    max_turns: int = 8
    temperature: float | None = None
    max_tokens: int | None = None
    host: str = "127.0.0.1"
    port: int = 8080


def get_settings() -> Settings:
    """Load ``Settings`` from the current process environment."""
    return Settings()
