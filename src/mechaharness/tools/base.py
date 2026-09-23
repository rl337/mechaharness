"""Tool protocol and in-process tool registry."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Union

from mechaharness.core.access import Ability, grant_key
from mechaharness.core.types import ToolDefinition, ToolResult

ToolHandler = Callable[..., Union[str, Awaitable[str]]]


class Tool:
    """A named callable exposed to harnesses as a ToolDefinition."""

    def __init__(
        self,
        name: str,
        handler: ToolHandler,
        *,
        description: str = "",
        parameters: dict[str, Any] | None = None,
        grants: Sequence[object] | None = None,
        ability: Ability = Ability.SIMPLE,
    ) -> None:
        self.name = name
        self.handler = handler
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}}
        self.grants = [grant_key(item) for item in (grants or [])]
        self.ability = ability

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    async def invoke(self, arguments: dict[str, Any], tool_call_id: str) -> ToolResult:
        try:
            result = self.handler(**arguments)
            if inspect.isawaitable(result):
                result = await result
            return ToolResult(tool_call_id=tool_call_id, content=str(result))
        except TypeError as exc:
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"Invalid arguments for tool {self.name}: {exc}",
                is_error=True,
            )
        except Exception as exc:  # noqa: BLE001 - surface tool failures to the model
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"Tool {self.name} failed: {exc}",
                is_error=True,
            )


class ToolRegistry:
    """In-process map of tool name → ``Tool`` for harness tool calling."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Add or replace a tool by name."""
        self._tools[tool.name] = tool

    def tool(
        self,
        name: str | None = None,
        *,
        description: str = "",
        parameters: dict[str, Any] | None = None,
        grants: Sequence[object] | None = None,
        ability: Ability = Ability.SIMPLE,
    ) -> Callable[[ToolHandler], ToolHandler]:
        """Decorator that registers the wrapped function as a tool."""

        def decorator(fn: ToolHandler) -> ToolHandler:
            tool_name = name or fn.__name__
            self.register(
                Tool(
                    tool_name,
                    fn,
                    description=description or (fn.__doc__ or "").strip(),
                    parameters=parameters,
                    grants=grants,
                    ability=ability,
                )
            )
            return fn

        return decorator

    def definitions(self) -> list[ToolDefinition]:
        """Provider-agnostic schemas for the current tool set."""
        return [t.definition() for t in self._tools.values()]

    def get(self, name: str) -> Tool:
        """Return a registered tool or raise ``KeyError``."""
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    async def execute(self, name: str, arguments: dict[str, Any], tool_call_id: str) -> ToolResult:
        return await self.get(name).invoke(arguments, tool_call_id)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
