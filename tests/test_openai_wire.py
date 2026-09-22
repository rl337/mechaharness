"""OpenAI wire models: validate/serialize Chat Completions JSON."""

from __future__ import annotations

from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    Role,
    ToolCall,
    ToolDefinition,
)
from mechaharness.inference.openai_compat import (
    domain_request_to_wire,
    wire_response_to_domain,
)
from mechaharness.inference.openai_wire import (
    OpenAIChatCompletionChunk,
    OpenAIChatCompletionResponse,
    OpenAIResponseMessage,
    decode_tool_arguments,
)


def test_request_round_trip_dump_excludes_none() -> None:
    domain = CompletionRequest(
        model="m1",
        messages=[ChatMessage(role=Role.USER, content="hi")],
        tools=[
            ToolDefinition(
                name="add",
                description="Add",
                parameters={"type": "object", "properties": {}},
            )
        ],
        temperature=0.2,
    )
    wire = domain_request_to_wire(domain, default_model="fallback")
    body = wire.model_dump(mode="json", exclude_none=True)
    assert body["model"] == "m1"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["function"]["name"] == "add"
    assert body["temperature"] == 0.2
    assert "stream" not in body
    assert "max_tokens" not in body


def test_response_missing_usage_still_maps() -> None:
    wire = OpenAIChatCompletionResponse.model_validate(
        {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )
    assert wire.usage is None
    domain = wire_response_to_domain(wire)
    assert domain.message.content == "ok"
    assert domain.usage is not None
    assert domain.usage.prompt_tokens is None
    assert domain.usage.completion_tokens is None
    assert domain.usage.total_tokens is None


def test_reasoning_content_string() -> None:
    msg = OpenAIResponseMessage.model_validate(
        {"role": "assistant", "content": "ans", "reasoning_content": "think"}
    )
    assert msg.resolved_reasoning_content == "think"
    domain = wire_response_to_domain(
        OpenAIChatCompletionResponse.model_validate(
            {
                "choices": [{"message": msg.model_dump(mode="json"), "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }
        )
    )
    assert domain.message.reasoning_content == "think"
    assert domain.usage is not None
    assert domain.usage.total_tokens == 3


def test_reasoning_object_coalesce() -> None:
    msg = OpenAIResponseMessage.model_validate(
        {"role": "assistant", "content": "ans", "reasoning": {"content": "nested"}}
    )
    assert msg.resolved_reasoning_content == "nested"


def test_tool_call_arguments_json_string() -> None:
    assert decode_tool_arguments('{"a": 1}') == {"a": 1}
    wire = OpenAIChatCompletionResponse.model_validate(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "1",
                                "type": "function",
                                "function": {
                                    "name": "add",
                                    "arguments": '{"a": 2, "b": 3}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )
    domain = wire_response_to_domain(wire)
    assert domain.message.tool_calls is not None
    assert domain.message.tool_calls[0] == ToolCall(
        id="1", name="add", arguments={"a": 2, "b": 3}
    )


def test_stream_chunk_delta_content() -> None:
    chunk = OpenAIChatCompletionChunk.model_validate(
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "hel"},
                    "finish_reason": None,
                }
            ]
        }
    )
    assert chunk.choices[0].delta.content == "hel"


def test_domain_request_includes_tool_calls_on_assistant() -> None:
    domain = CompletionRequest(
        model="m",
        messages=[
            ChatMessage(
                role=Role.ASSISTANT,
                content=None,
                tool_calls=[ToolCall(id="c1", name="echo", arguments={"text": "x"})],
            )
        ],
    )
    body = domain_request_to_wire(domain, default_model="m").model_dump(
        mode="json", exclude_none=True
    )
    call = body["messages"][0]["tool_calls"][0]
    assert call["id"] == "c1"
    assert call["function"]["name"] == "echo"
    assert call["function"]["arguments"] == '{"text": "x"}'
