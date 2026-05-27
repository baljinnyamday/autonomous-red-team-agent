from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from agent_redteam.agents.base import AgentContext
from agent_redteam.tools.types import ToolCall, ToolDefinition, ToolResult

MessageRole = Literal["system", "user", "assistant", "tool"]
ModelEventType = Literal[
    "message_delta",
    "message_done",
    "tool_call",
    "usage",
    "completed",
    "error",
]


@dataclass(frozen=True)
class AgentMessage:
    role: MessageRole
    content: str
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelRequest:
    context: AgentContext
    messages: tuple[AgentMessage, ...]
    tools: tuple[ToolDefinition, ...]
    iteration: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelEvent:
    event_type: ModelEventType
    content: str | None = None
    tool_call: ToolCall | None = None
    usage: dict[str, Any] | None = None
    error: str | None = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)


class ProviderHarness(Protocol):
    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        """Yield provider output as normalized model events."""

    def render_tools(self, tools: Sequence[ToolDefinition]) -> list[dict[str, Any]]:
        """Render internal tool definitions into provider-native specs."""

    def format_tool_results(self, results: Sequence[ToolResult]) -> list[AgentMessage]:
        """Format tool outputs for the next model request."""
