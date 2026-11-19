"""Provider-owned OpenAI request normalization and diagnostic body fingerprints.

Fingerprints describe the exact normalized JSON body, not a provider cache key.
Headers, endpoint routing, tenant scope, and cache hit counters are excluded.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from mechaharness.model_input_manifest import content_digest

# Completer ``extra`` keys used by MechaHarness runners — never forward to HTTP.
_MH_COMPLETION_EXTRA_DENY = frozenset(
    {
        "node_id",
        "script_key",
        "snapshot_id",
        "invocation_id",
        "parent_node_id",
        "execution_node_id",
        "run_id",
    }
)

# OpenAI Chat Completions params commonly set via ``request.extra``.
_OPENAI_BODY_EXTRA_ALLOW = frozenset(
    {
        "reasoning_effort",
        "max_completion_tokens",
        "response_format",
        "tool_choice",
        "parallel_tool_calls",
        "stream_options",
        "user",
        "seed",
        "top_p",
        "n",
        "frequency_penalty",
        "presence_penalty",
        "logit_bias",
        "logprobs",
        "top_logprobs",
        "modalities",
        "audio",
        "prediction",
        "store",
        "metadata",
        "service_tier",
    }
)


@dataclass(frozen=True)
class OpenAIRequestCapabilities:
    completion_token_field: str = "max_tokens"
    allowed_extra_fields: frozenset[str] | None = None
    tool_reasoning_effort: str | None = None


@dataclass(frozen=True)
class PreparedOpenAIRequest:
    """Transport body and omitted field names; diagnostics never contain raw values."""

    body: dict[str, Any]
    omitted_fields: tuple[str, ...]

    def diagnostics(self) -> dict[str, Any]:
        return {
            "request_body_digest": content_digest(self.body),
            "omitted_fields": list(self.omitted_fields),
            "provider_cache_observed": False,
        }


class OpenAIRequestPolicy:
    """Injectable provider policy; hosts override capabilities for custom/proxy endpoints."""

    def capabilities_for(self, endpoint: str, model: str) -> OpenAIRequestCapabilities:
        cloud = urlsplit(endpoint).hostname == "api.openai.com"
        luna = re.fullmatch(r"gpt-6-luna(?:-[a-z0-9-]+)?", model.lower()) is not None
        return OpenAIRequestCapabilities(
            completion_token_field="max_completion_tokens" if cloud or luna else "max_tokens",
            allowed_extra_fields=_OPENAI_BODY_EXTRA_ALLOW if cloud or luna else None,
            tool_reasoning_effort="none" if luna else None,
        )

    def prepare(
        self, body: dict[str, Any], extras: dict[str, Any], *, endpoint: str
    ) -> PreparedOpenAIRequest:
        normalized = dict(body)
        caps = self.capabilities_for(endpoint, str(body["model"]))
        omitted = []
        for key, value in extras.items():
            if key in _MH_COMPLETION_EXTRA_DENY or (
                caps.allowed_extra_fields is not None and key not in caps.allowed_extra_fields
            ):
                omitted.append(key)
            else:
                normalized[key] = value
        if normalized.get("tools") and caps.tool_reasoning_effort is not None:
            normalized.setdefault("reasoning_effort", caps.tool_reasoning_effort)
        if "max_tokens" in normalized and caps.completion_token_field != "max_tokens":
            tokens = normalized.pop("max_tokens")
            normalized.setdefault(caps.completion_token_field, tokens)
        # Detach nested extras from caller-owned containers and reject non-JSON values.
        normalized = json.loads(json.dumps(normalized, allow_nan=False))
        return PreparedOpenAIRequest(normalized, tuple(sorted(omitted)))
