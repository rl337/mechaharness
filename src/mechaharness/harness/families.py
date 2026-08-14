"""Model-family specializations that tweak message / tool encoding."""

from __future__ import annotations

from mechaharness.harness.tool_loop import ToolLoopHarness


class OpenAIToolsHarness(ToolLoopHarness):
    """OpenAI / OpenAI-compat native function-calling loop."""

    family = "openai_tools"


class AnthropicToolsHarness(ToolLoopHarness):
    """Anthropic tool_use loop. Encoding is handled by AnthropicStrategy."""

    family = "anthropic_tools"
