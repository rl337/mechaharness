"""Story backend resolution including ``MECHA_LIVE_OPENAI`` cloud path."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from tests.stories.backend import (
    CLOUD_OPENAI_BASE_URL,
    DEFAULT_CLOUD_OPENAI_MODEL,
    STATIC_OPENAI_COMPAT_API_KEY,
    STATIC_OPENAI_COMPAT_BASE_URL,
    resolve_live_openai_compat_endpoint,
    resolve_live_openai_compat_model,
    resolve_openai_story_api_key,
    resolve_story_backend,
    wants_cloud_openai,
)


@dataclass(frozen=True)
class LiveAliasCase:
    label: str
    env: dict[str, str]
    expect_mode: str
    expect_filter: str | None


@pytest.mark.parametrize(
    "case",
    [
        LiveAliasCase(
            label="live_openai_no_filter",
            env={"MECHA_LIVE_OPENAI": "1"},
            expect_mode="live",
            expect_filter=None,
        ),
        LiveAliasCase(
            label="live_openai_with_story_model",
            env={
                "MECHA_LIVE_OPENAI": "1",
                "MECHA_STORY_MODEL": "openai_compat/qwen3-30b-thinking",
            },
            expect_mode="live",
            expect_filter="openai_compat/qwen3-30b-thinking",
        ),
        LiveAliasCase(
            label="live_openai_compat_legacy",
            env={"MECHA_LIVE_OPENAI_COMPAT": "1"},
            expect_mode="live",
            expect_filter="openai_compat/qwen3-30b-thinking",
        ),
        LiveAliasCase(
            label="explicit_live_wins",
            env={
                "MECHA_STORY_BACKEND": "live",
                "MECHA_LIVE_OPENAI": "1",
                "MECHA_STORY_MODEL": "custom/filter",
            },
            expect_mode="live",
            expect_filter="custom/filter",
        ),
        LiveAliasCase(
            label="default_static_despite_openai_key",
            env={"OPENAI_API_KEY": "sk-cloud"},
            expect_mode="static",
            expect_filter=None,
        ),
    ],
    ids=lambda c: c.label,
)
def test_resolve_story_backend_live_aliases(
    case: LiveAliasCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in (
        "MECHA_STORY_BACKEND",
        "MECHA_STORY_MODEL",
        "MECHA_LIVE_OPENAI",
        "MECHA_LIVE_OPENAI_COMPAT",
        "MECHA_LIVE_QWEN",
        "MECHA_LIVE_JUDGE",
        "MECHA_LIVE_DECIDE",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in case.env.items():
        monkeypatch.setenv(key, value)
    backend = resolve_story_backend()
    assert backend.mode == case.expect_mode
    assert backend.model_filter == case.expect_filter


@dataclass(frozen=True)
class EndpointCase:
    label: str
    env: dict[str, str]
    expect_base: str
    expect_key: str
    expect_error: bool = False


@pytest.mark.parametrize(
    "case",
    [
        EndpointCase(
            label="explicit_base_url_local_live",
            env={
                "MECHA_BASE_URL": "http://127.0.0.1:8000/v1",
                "MECHA_API_KEY": "local",
            },
            expect_base="http://127.0.0.1:8000/v1",
            expect_key="local",
        ),
        EndpointCase(
            label="openai_key_alone_does_not_select_cloud",
            env={"OPENAI_API_KEY": "sk-cloud"},
            expect_base="",
            expect_key="",
            expect_error=True,
        ),
        EndpointCase(
            label="cloud_via_live_openai_flag",
            env={"MECHA_LIVE_OPENAI": "1", "OPENAI_API_KEY": "sk-cloud"},
            expect_base=CLOUD_OPENAI_BASE_URL,
            expect_key="sk-cloud",
        ),
        EndpointCase(
            label="cloud_opt_in_ignores_local_base_url",
            env={
                "MECHA_LIVE_OPENAI": "1",
                "MECHA_BASE_URL": "http://127.0.0.1:1234/v1",
                "OPENAI_API_KEY": "sk-cloud",
            },
            expect_base=CLOUD_OPENAI_BASE_URL,
            expect_key="sk-cloud",
        ),
        EndpointCase(
            label="cloud_via_inference_backend",
            env={
                "MECHA_INFERENCE_BACKEND": "openai",
                "MECHA_API_KEY": "sk-mecha",
            },
            expect_base=CLOUD_OPENAI_BASE_URL,
            expect_key="sk-mecha",
        ),
        EndpointCase(
            label="missing_base_without_cloud_opt_in_errors",
            env={},
            expect_base="",
            expect_key="",
            expect_error=True,
        ),
    ],
    ids=lambda c: c.label,
)
def test_resolve_live_openai_compat_endpoint(
    case: EndpointCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in (
        "MECHA_BASE_URL",
        "MECHA_API_KEY",
        "OPENAI_API_KEY",
        "MECHA_LIVE_OPENAI",
        "MECHA_INFERENCE_BACKEND",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in case.env.items():
        monkeypatch.setenv(key, value)
    if case.expect_error:
        with pytest.raises(AssertionError, match="MECHA_BASE_URL"):
            resolve_live_openai_compat_endpoint()
        return
    base, key = resolve_live_openai_compat_endpoint()
    assert base == case.expect_base
    assert key == case.expect_key


def test_wants_cloud_openai_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MECHA_LIVE_OPENAI", raising=False)
    monkeypatch.delenv("MECHA_INFERENCE_BACKEND", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-cloud")
    assert wants_cloud_openai() is False
    monkeypatch.setenv("MECHA_LIVE_OPENAI", "1")
    assert wants_cloud_openai() is True


def test_static_openai_compat_constants_are_offline() -> None:
    assert STATIC_OPENAI_COMPAT_BASE_URL.startswith("http://story.invalid")
    assert STATIC_OPENAI_COMPAT_API_KEY == "story"
    assert "openai.com" not in STATIC_OPENAI_COMPAT_BASE_URL


def test_resolve_openai_story_api_key_prefers_mecha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MECHA_API_KEY", "sk-mecha")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    assert resolve_openai_story_api_key() == "sk-mecha"


def test_resolve_live_openai_compat_model_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MECHA_MODEL", raising=False)
    assert resolve_live_openai_compat_model("") == DEFAULT_CLOUD_OPENAI_MODEL
    assert resolve_live_openai_compat_model("cassette-model") == "cassette-model"
    monkeypatch.setenv("MECHA_MODEL", "gpt-6-luna")
    assert resolve_live_openai_compat_model("cassette-model") == "gpt-6-luna"
