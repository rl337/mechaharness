"""ProjectCoding only remaps bare ``openai`` when base_url is local."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mechaharness.project_coding import _settings_for_project_coding


@dataclass(frozen=True)
class RemapCase:
    label: str
    env: dict[str, str]
    expect_backend: str


@pytest.mark.parametrize(
    "case",
    [
        RemapCase(
            label="local_base_remaps_openai_to_openai_local",
            env={
                "MECHA_BASE_URL": "http://127.0.0.1:1234/v1",
                "MECHA_API_KEY": "local",
            },
            expect_backend="openai_local",
        ),
        RemapCase(
            label="cloud_base_keeps_openai",
            env={
                "MECHA_BASE_URL": "https://api.openai.com/v1",
                "MECHA_API_KEY": "sk-test",
            },
            expect_backend="openai",
        ),
        RemapCase(
            label="explicit_backend_env_skips_remap",
            env={
                "MECHA_INFERENCE_BACKEND": "openai",
                "MECHA_BASE_URL": "http://127.0.0.1:1234/v1",
                "MECHA_API_KEY": "local",
            },
            expect_backend="openai",
        ),
    ],
    ids=lambda c: c.label,
)
def test_project_coding_openai_remap(
    case: RemapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in (
        "MECHA_INFERENCE_BACKEND",
        "MECHA_BASE_URL",
        "MECHA_API_KEY",
        "MECHA_MODEL",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    # Settings defaults inference_backend to openai when env unset.
    for key, value in case.env.items():
        monkeypatch.setenv(key, value)
    resolved = _settings_for_project_coding()
    assert resolved.inference_backend == case.expect_backend
