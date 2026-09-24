"""HTTP connection configuration for inference adapters.

``APIConnectionConfig`` is the injectable “how to reach this service” bundle
(endpoint + credentials + timeout). Wire shape stays on ``JudgeProvider`` /
``InferenceStrategy``. Hosts swap implementations (simple HTTP, later OAuth)
via Config hooks without proliferating URL-only and auth-only types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from mechaharness.config import Settings

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
    def for_judge(cls, settings: Settings) -> SimpleHttpConnectionConfig:
        """Build a judge-lane connection from ``Settings`` / ``MECHA_JUDGE_*``."""
        return cls(
            base_url=settings.judge_base_url,
            path=settings.judge_path or DEFAULT_JUDGE_PATH,
            url=settings.judge_url,
            api_key=settings.judge_api_key or settings.api_key,
            model=settings.judge_model,
            timeout=float(settings.judge_timeout_seconds),
        )

    def endpoint_url(self) -> str:
        if self._url:
            return self._url
        if not self._base_url:
            raise ValueError(
                "judge_base_url / MECHA_JUDGE_BASE_URL is required when judge_url is unset"
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
