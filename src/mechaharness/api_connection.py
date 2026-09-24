"""HTTP connection configuration for inference adapters.

``APIConnectionConfig`` is the injectable “how to reach this service” bundle
(endpoint + credentials + timeout). Wire shape stays on ``JudgeProvider`` /
``InferenceStrategy``. Hosts swap implementations (simple HTTP, later OAuth)
via Config hooks without proliferating URL-only and auth-only types.

Judge-lane env knobs (``MECHA_JUDGE_*``) bind here via ``from_env`` — not on
``Settings``.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

DEFAULT_JUDGE_PATH = "/v1/systemone"


class APIConnectionConfig(ABC):
    """How to open an HTTP connection to an inference / judge endpoint."""

    @abstractmethod
    def endpoint_url(self) -> str:
        """Absolute URL used for the request (no further path joining)."""

    def headers(self) -> dict[str, str]:
        """Extra HTTP headers (Authorization, etc.)."""
        return {}

    def timeout_seconds(self) -> float:
        return 60.0

    def model_id(self) -> str | None:
        """Optional model id for JSON bodies that accept ``model``."""
        return None


class SimpleHttpConnectionConfig(APIConnectionConfig):
    """Base URL + path (or full URL) with optional API key header.

    Default judge path is ``/v1/systemone``. Set ``url`` to override the full
    endpoint (e.g. a hosted provider with a different scheme).
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        path: str = DEFAULT_JUDGE_PATH,
        url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        header_name: str = "Authorization",
        header_value_template: str = "Bearer {api_key}",
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._path = path if path.startswith("/") else f"/{path}"
        self._url = url.rstrip("/") if url else None
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._header_name = header_name
        self._header_value_template = header_value_template

    @classmethod
    def from_env(
        cls,
        *,
        prefix: str = "MECHA_JUDGE",
        legacy_prefix: str | None = "MECHA_DECIDE",
        default_path: str = DEFAULT_JUDGE_PATH,
        fallback_api_key_env: str = "MECHA_API_KEY",
    ) -> SimpleHttpConnectionConfig:
        """Bind connection knobs from the process environment.

        Reads ``{prefix}_BASE_URL``, ``_PATH``, ``_URL``, ``_MODEL``,
        ``_API_KEY``, ``_TIMEOUT_SECONDS``. When ``legacy_prefix`` is set,
        falls back for base URL / model (judge migration window).
        """

        def _get(*keys: str) -> str | None:
            for key in keys:
                value = os.environ.get(key)
                if value is not None and value != "":
                    return value
            return None

        base = _get(f"{prefix}_BASE_URL")
        model = _get(f"{prefix}_MODEL")
        if legacy_prefix:
            if base is None:
                base = _get(f"{legacy_prefix}_BASE_URL")
            if model is None:
                model = _get(f"{legacy_prefix}_MODEL")
        path = _get(f"{prefix}_PATH") or default_path
        url = _get(f"{prefix}_URL")
        api_key = _get(f"{prefix}_API_KEY", fallback_api_key_env)
        timeout_raw = _get(f"{prefix}_TIMEOUT_SECONDS")
        timeout = float(timeout_raw) if timeout_raw else 60.0
        return cls(
            base_url=base,
            path=path,
            url=url,
            api_key=api_key,
            model=model,
            timeout=timeout,
        )

    @classmethod
    def for_judge(cls, **overrides: Any) -> SimpleHttpConnectionConfig:
        """Judge-lane connection from env, with optional constructor overrides."""
        conn = cls.from_env()
        if not overrides:
            return conn
        return cls(
            base_url=overrides.get("base_url", conn._base_url or None),
            path=overrides.get("path", conn._path),
            url=overrides.get("url", conn._url),
            api_key=overrides.get("api_key", conn._api_key),
            model=overrides.get("model", conn._model),
            timeout=float(overrides.get("timeout", conn._timeout)),
            header_name=overrides.get("header_name", conn._header_name),
            header_value_template=overrides.get(
                "header_value_template", conn._header_value_template
            ),
        )

    def endpoint_url(self) -> str:
        if self._url:
            return self._url
        if not self._base_url:
            raise ValueError(
                "MECHA_JUDGE_BASE_URL is required when MECHA_JUDGE_URL is unset"
            )
        return f"{self._base_url}{self._path}"

    def headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        value = self._header_value_template.format(api_key=self._api_key)
        return {self._header_name: value}

    def timeout_seconds(self) -> float:
        return self._timeout

    def model_id(self) -> str | None:
        return self._model


def connection_as_dict(conn: APIConnectionConfig) -> dict[str, Any]:
    """Debug helper — never log secrets from headers."""
    return {
        "endpoint_url": conn.endpoint_url(),
        "timeout_seconds": conn.timeout_seconds(),
        "model_id": conn.model_id(),
        "header_keys": sorted(conn.headers()),
    }
