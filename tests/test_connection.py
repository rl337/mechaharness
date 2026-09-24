"""APIConnectionConfig / SimpleHttpConnectionConfig tests."""

from __future__ import annotations

import pytest

from mechaharness.config import Settings
from mechaharness.connection import SimpleHttpConnectionConfig


def test_simple_http_joins_base_and_path() -> None:
    conn = SimpleHttpConnectionConfig(
        base_url="http://localhost:8009",
        path="/v1/systemone",
        model="laya",
    )
    assert conn.endpoint_url() == "http://localhost:8009/v1/systemone"
    assert conn.model_id() == "laya"


def test_full_url_override() -> None:
    conn = SimpleHttpConnectionConfig(
        base_url="http://ignored:9",
        url="https://api.example.com/v2/judge",
    )
    assert conn.endpoint_url() == "https://api.example.com/v2/judge"


def test_custom_path() -> None:
    conn = SimpleHttpConnectionConfig(
        base_url="http://localhost:8009/",
        path="v1/custom",
    )
    assert conn.endpoint_url() == "http://localhost:8009/v1/custom"


def test_for_judge_from_settings() -> None:
    settings = Settings(
        judge_base_url="http://j:8009",
        judge_path="/v1/systemone",
        judge_model="laya",
        judge_api_key="secret",
    )
    conn = SimpleHttpConnectionConfig.for_judge(settings)
    assert conn.endpoint_url() == "http://j:8009/v1/systemone"
    assert conn.headers()["Authorization"] == "Bearer secret"


def test_legacy_decide_env_aliases() -> None:
    settings = Settings(decide_base_url="http://legacy:8009", decide_model="kev")
    assert settings.judge_base_url == "http://legacy:8009"
    assert settings.judge_model == "kev"


def test_missing_base_raises() -> None:
    conn = SimpleHttpConnectionConfig(base_url=None)
    with pytest.raises(ValueError, match="judge_base_url"):
        conn.endpoint_url()
