"""Provider policy normalizes exact wire bodies without logging raw prompts."""

from __future__ import annotations

import pytest
from pyiv.http import MemoryAsyncHttpClient

from mechaharness.config import Settings
from mechaharness.core.types import ChatMessage, CompletionRequest, Role, ToolDefinition
from mechaharness.di import SettingsConfig, get_injector
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.openai_compat import OpenAICompatStrategy
from mechaharness.inference.openai_request import OpenAIRequestCapabilities, OpenAIRequestPolicy
from mechaharness.model_input_manifest import content_digest


@pytest.mark.parametrize(
    "endpoint,model,field",
    [
        ("https://api.openai.com/v1", "gpt-6-luna", "max_completion_tokens"),
        ("https://api.openai.com.example.invalid/v1", "local", "max_tokens"),
        ("https://example.invalid/api.openai.com", "local", "max_tokens"),
        ("http://127.0.0.1:8000/v1", "not-luna-local", "max_tokens"),
    ],
)
def test_provider_and_model_detection_is_anchored(endpoint: str, model: str, field: str) -> None:
    prepared = OpenAIRequestPolicy().prepare(
        {"model": model, "max_tokens": 12}, {}, endpoint=endpoint
    )
    assert prepared.body[field] == 12
    assert len([k for k in prepared.body if k.startswith("max_")]) == 1


def test_explicit_limit_wins_and_internal_metadata_is_reported_as_omitted() -> None:
    prepared = OpenAIRequestPolicy().prepare(
        {"model": "gpt-6-luna", "max_tokens": 12},
        {"max_completion_tokens": 24, "node_id": "internal", "unsupported": "value"},
        endpoint="https://api.openai.com/v1",
    )
    assert prepared.body["max_completion_tokens"] == 24
    assert "max_tokens" not in prepared.body
    assert prepared.omitted_fields == ("node_id", "unsupported")
    assert prepared.diagnostics()["provider_cache_observed"] is False


class ProxyPolicy(OpenAIRequestPolicy):
    def capabilities_for(self, endpoint: str, model: str) -> OpenAIRequestCapabilities:
        return OpenAIRequestCapabilities(completion_token_field="max_completion_tokens")


def test_config_owns_custom_proxy_capabilities() -> None:
    class ProxyConfig(SettingsConfig):
        def get_openai_request_policy(self):
            return ProxyPolicy

    config = ProxyConfig(
        Settings(
            inference_backend="openai_compat", model="local", base_url="https://proxy.invalid/v1"
        )
    )
    injector = get_injector(config)
    strategy = injector.inject(InferenceStrategy)
    assert strategy.request_policy is injector.inject(OpenAIRequestPolicy)
    request = CompletionRequest(model="local", messages=[], max_tokens=5)
    assert strategy.prepare_request(request).body["max_completion_tokens"] == 5


@pytest.mark.asyncio
async def test_fingerprint_matches_sent_body_and_includes_tool_descriptions() -> None:
    class RecordingClient(MemoryAsyncHttpClient):
        async def post(self, url, **kwargs):
            self.sent_body = kwargs["json"]
            return await super().post(url, **kwargs)

    client = RecordingClient()
    endpoint = "http://example.invalid/v1"
    client.add(
        "POST",
        endpoint + "/chat/completions",
        json={
            "id": "test",
            "created": 0,
            "model": "local",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
        },
    )
    strategy = OpenAICompatStrategy(Settings(model="local", base_url=endpoint), client)
    request = CompletionRequest(
        model="local",
        messages=[ChatMessage(role=Role.USER, content="private prompt")],
        tools=[ToolDefinition(name="read", description="first")],
    )
    prepared = strategy.prepare_request(request)
    await strategy.complete(request)
    assert prepared.diagnostics()["request_body_digest"] == content_digest(client.sent_body)
    second = request.model_copy(
        update={"tools": [ToolDefinition(name="read", description="second")]}
    )
    assert strategy.prepare_request(second).diagnostics() != prepared.diagnostics()
    assert "private prompt" not in str(prepared.diagnostics())
