"""APIConnectionConfig / SimpleHttpConnectionConfig tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pyiv.process import MemoryEnvironment

from mechaharness.api_connection import SimpleHttpConnectionConfig


@dataclass(frozen=True)
class _EndpointCase:
    id: str
    kwargs: dict
    endpoint: str
    model: str | None = None


_ENDPOINT_CASES = [
    _EndpointCase(
        "joins_base_and_path",
        {"base_url": "http://localhost:8009", "path": "/v1/systemone", "model": "laya"},
        "http://localhost:8009/v1/systemone",
        model="laya",
    ),
    _EndpointCase(
        "full_url_override",
        {"base_url": "http://ignored:9", "url": "https://api.example.com/v2/judge"},
        "https://api.example.com/v2/judge",
    ),
    _EndpointCase(
        "custom_path_strips_slashes",
        {"base_url": "http://localhost:8009/", "path": "v1/custom"},
        "http://localhost:8009/v1/custom",
    ),
]


@pytest.mark.parametrize("case", _ENDPOINT_CASES, ids=lambda c: c.id)
def test_endpoint_url_from_fields(case: _EndpointCase) -> None:
    conn = SimpleHttpConnectionConfig(**case.kwargs)
    assert conn.endpoint_url() == case.endpoint
    if case.model is not None:
        assert conn.model_id() == case.model


@dataclass(frozen=True)
class _EnvCase:
    id: str
    env: dict[str, str]
    factory: str  # "from_env" | "for_judge"
    overrides: dict
    endpoint: str
    model: str
    auth_bearer: str | None = None


_ENV_CASES = [
    _EnvCase(
        "from_env_judge",
        {
            "MECHA_JUDGE_BASE_URL": "http://j:8009",
            "MECHA_JUDGE_PATH": "/v1/systemone",
            "MECHA_JUDGE_MODEL": "laya",
            "MECHA_JUDGE_API_KEY": "secret",
        },
        "from_env",
        {},
        "http://j:8009/v1/systemone",
        "laya",
        auth_bearer="secret",
    ),
    _EnvCase(
        "for_judge_legacy_decide_aliases",
        {
            "MECHA_DECIDE_BASE_URL": "http://legacy:8009",
            "MECHA_DECIDE_MODEL": "kev",
        },
        "for_judge",
        {},
        "http://legacy:8009/v1/systemone",
        "kev",
    ),
    _EnvCase(
        "for_judge_overrides_env",
        {"MECHA_JUDGE_BASE_URL": "http://env:8009"},
        "for_judge",
        {"base_url": "http://override:9", "model": "x"},
        "http://override:9/v1/systemone",
        "x",
    ),
]


@pytest.mark.parametrize("case", _ENV_CASES, ids=lambda c: c.id)
def test_env_and_for_judge_builders(case: _EnvCase) -> None:
    env = MemoryEnvironment(case.env)
    if case.factory == "from_env":
        conn = SimpleHttpConnectionConfig.from_env(env=env, **case.overrides)
    else:
        conn = SimpleHttpConnectionConfig.for_judge(env=env, **case.overrides)
    assert conn.endpoint_url() == case.endpoint
    assert conn.model_id() == case.model
    if case.auth_bearer is not None:
        assert conn.headers()["Authorization"] == f"Bearer {case.auth_bearer}"


@dataclass(frozen=True)
class _ErrorCase:
    id: str
    call: object
    exc: type[BaseException]
    match: str


_ERROR_CASES = [
    _ErrorCase(
        "missing_base_raises",
        lambda: SimpleHttpConnectionConfig(base_url=None).endpoint_url(),
        ValueError,
        "MECHA_JUDGE_BASE_URL",
    ),
    _ErrorCase(
        "for_judge_requires_env",
        lambda: SimpleHttpConnectionConfig.for_judge(),
        TypeError,
        "env",
    ),
]


@pytest.mark.parametrize("case", _ERROR_CASES, ids=lambda c: c.id)
def test_connection_errors(case: _ErrorCase) -> None:
    with pytest.raises(case.exc, match=case.match):
        case.call()  # type: ignore[operator]
