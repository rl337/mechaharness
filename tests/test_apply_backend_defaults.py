"""``apply_backend_defaults`` fills base_url / api_key / OPENAI_API_KEY."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mechaharness.config import Settings
from mechaharness.di import apply_backend_defaults


def _settings(
    *,
    backend: str,
    api_key: str | None,
    base_url: str | None = None,
) -> Settings:
    return Settings.model_construct(
        inference_backend=backend,
        api_key=api_key,
        base_url=base_url,
        model="gpt-6-luna",
        harness_family="tool_loop",
        system_prompt=None,
        max_turns=8,
        temperature=None,
        max_tokens=None,
        host="127.0.0.1",
        port=8080,
    )


@dataclass(frozen=True)
class ApiKeyCase:
    label: str
    mecha_api_key: str | None
    openai_api_key: str | None
    backend: str
    expect_api_key: str | None


@pytest.mark.parametrize(
    "case",
    [
        ApiKeyCase(
            label="openai_key_when_mecha_unset",
            mecha_api_key=None,
            openai_api_key="sk-from-openai",
            backend="openai",
            expect_api_key="sk-from-openai",
        ),
        ApiKeyCase(
            label="mecha_wins_over_openai",
            mecha_api_key="sk-mecha",
            openai_api_key="sk-from-openai",
            backend="openai",
            expect_api_key="sk-mecha",
        ),
        ApiKeyCase(
            label="openai_local_placeholder_without_openai_env",
            mecha_api_key=None,
            openai_api_key=None,
            backend="openai_local",
            expect_api_key="local",
        ),
        ApiKeyCase(
            label="openai_local_keeps_placeholder_when_openai_env_set",
            mecha_api_key=None,
            openai_api_key="sk-cloud",
            backend="openai_local",
            expect_api_key="local",
        ),
    ],
    ids=lambda c: c.label,
)
def test_apply_backend_defaults_api_key(
    case: ApiKeyCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    if case.openai_api_key is None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENAI_API_KEY", case.openai_api_key)
    resolved = apply_backend_defaults(
        _settings(backend=case.backend, api_key=case.mecha_api_key)
    )
    assert resolved.api_key == case.expect_api_key


def test_settings_default_model_is_luna() -> None:
    assert Settings.model_fields["model"].default == "gpt-6-luna"


def test_openai_backend_default_base_url() -> None:
    resolved = apply_backend_defaults(
        _settings(backend="openai", api_key="sk-test", base_url=None)
    )
    assert resolved.base_url == "https://api.openai.com/v1"


def test_openai_api_key_fallback_strips_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", " sk-env-key ")
    resolved = apply_backend_defaults(_settings(backend="openai", api_key=None))
    assert resolved.api_key == "sk-env-key"
