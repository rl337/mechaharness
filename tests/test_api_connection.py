"""APIConnectionConfig / SimpleHttpConnectionConfig tests."""

from __future__ import annotations

import pytest
from pyiv.process import MemoryEnvironment

from mechaharness.api_connection import SimpleHttpConnectionConfig


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


def test_from_env_judge() -> None:
    env = MemoryEnvironment(
        {
            "MECHA_JUDGE_BASE_URL": "http://j:8009",
            "MECHA_JUDGE_PATH": "/v1/systemone",
            "MECHA_JUDGE_MODEL": "laya",
            "MECHA_JUDGE_API_KEY": "secret",
        }
    )
    conn = SimpleHttpConnectionConfig.from_env(env=env)
    assert conn.endpoint_url() == "http://j:8009/v1/systemone"
    assert conn.headers()["Authorization"] == "Bearer secret"
    assert conn.model_id() == "laya"


def test_from_env_legacy_decide_aliases() -> None:
    env = MemoryEnvironment(
        {
            "MECHA_DECIDE_BASE_URL": "http://legacy:8009",
            "MECHA_DECIDE_MODEL": "kev",
        }
    )
    conn = SimpleHttpConnectionConfig.for_judge(env=env)
    assert conn.endpoint_url() == "http://legacy:8009/v1/systemone"
    assert conn.model_id() == "kev"


def test_for_judge_overrides_env() -> None:
    env = MemoryEnvironment({"MECHA_JUDGE_BASE_URL": "http://env:8009"})
    conn = SimpleHttpConnectionConfig.for_judge(
        env=env, base_url="http://override:9", model="x"
    )
    assert conn.endpoint_url() == "http://override:9/v1/systemone"
    assert conn.model_id() == "x"


def test_missing_base_raises() -> None:
    conn = SimpleHttpConnectionConfig(base_url=None)
    with pytest.raises(ValueError, match="MECHA_JUDGE_BASE_URL"):
        conn.endpoint_url()


def test_for_judge_requires_env() -> None:
    with pytest.raises(TypeError, match="env"):
        SimpleHttpConnectionConfig.for_judge()
