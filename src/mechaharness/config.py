"""Settings loaded from environment / .env for CLI and API.

Shared run surface only. Lane- and provider-specific knobs belong on the
owning injectable (e.g. ``APIConnectionConfig.from_env`` for judge HTTP) —
do not grow this class into a provider bag. See ``.cursor/rules/di-first.mdc``.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for CLI / HTTP / reason-lane OpenAI-compat (transitional).

    Reason ``base_url`` / ``api_key`` / ``model`` here are known debt to migrate
    onto connection config later. Do not add judge/media/OAuth fields.
    """

    model_config = SettingsConfigDict(env_prefix="MECHA_", env_file=".env", extra="ignore")

    inference_backend: str = "openai"
    harness_family: str = "tool_loop"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    base_url: str | None = None
    system_prompt: str | None = None
    max_turns: int = 8
    temperature: float | None = None
    max_tokens: int | None = None
    host: str = "127.0.0.1"
    port: int = 8080


def get_settings() -> Settings:
    """Load ``Settings`` from the current process environment."""
    return Settings()
