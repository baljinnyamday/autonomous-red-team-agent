from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from inspect import isawaitable
from typing import cast

from agent_redteam.agents.base import AgentContext
from agent_redteam.tools.types import ToolCall, ToolDefinition

ToolHandler = Callable[[AgentContext, ToolCall], str | Awaitable[str]]


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    handler: ToolHandler


class ToolRegistry:
    def __init__(self, tools: Iterable[RegisteredTool] = ()) -> None:
        self._tools: dict[str, RegisteredTool] = {tool.definition.name: tool for tool in tools}

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        self._tools[definition.name] = RegisteredTool(definition=definition, handler=handler)

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]

    async def call(self, context: AgentContext, tool_call: ToolCall) -> str:
        registered = self._tools[tool_call.name]
        output = registered.handler(context, tool_call)
        if isawaitable(output):
            return await cast(Awaitable[str], output)
        return output

    def __contains__(self, name: object) -> bool:
        return name in self._tools
