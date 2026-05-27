from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from agent_redteam.agents.base import AgentContext
from agent_redteam.llm.types import AgentMessage, ModelRequest, ProviderHarness
from agent_redteam.tools.executor import ToolExecutor
from agent_redteam.tools.registry import ToolRegistry
from agent_redteam.tools.types import ToolCall, ToolResult

DEFAULT_MAX_ITERATIONS = 9999


@dataclass(frozen=True)
class AgentLoopLimits:
    max_iterations: int = DEFAULT_MAX_ITERATIONS


@dataclass(frozen=True)
class AgentLoopResult:
    success: bool
    final_message: str | None
    messages: tuple[AgentMessage, ...]
    tool_results: tuple[ToolResult, ...]
    iterations: int
    usage: tuple[dict[str, Any], ...] = ()
    error: str | None = None


class AgentLoop:
    def __init__(
        self,
        *,
        provider: ProviderHarness,
        tool_registry: ToolRegistry,
        limits: AgentLoopLimits | None = None,
    ) -> None:
        self._provider = provider
        self._tool_registry = tool_registry
        self._tool_executor = ToolExecutor(tool_registry)
        self._limits = limits or AgentLoopLimits()

    async def run(
        self,
        context: AgentContext,
        initial_messages: Sequence[AgentMessage],
    ) -> AgentLoopResult:
        messages = list(initial_messages)
        tool_results: list[ToolResult] = []
        usage_events: list[dict[str, Any]] = []

        for iteration in range(1, self._limits.max_iterations + 1):
            tools = tuple(self._tool_registry.definitions())
            request = ModelRequest(
                context=context,
                messages=tuple(messages),
                tools=tools,
                iteration=iteration,
                metadata={"rendered_tools": self._provider.render_tools(tools)},
            )

            turn = await self._collect_turn(request)
            usage_events.extend(turn.usage)
            if turn.error is not None:
                return AgentLoopResult(
                    success=False,
                    final_message=None,
                    messages=tuple(messages),
                    tool_results=tuple(tool_results),
                    iterations=iteration,
                    usage=tuple(usage_events),
                    error=turn.error,
                )

            assistant_message = _build_assistant_message(turn.message, turn.tool_calls)
            if assistant_message is not None:
                messages.append(assistant_message)

            if turn.tool_calls:
                results = await self._tool_executor.execute_batch(context, turn.tool_calls)
                tool_results.extend(results)
                messages.extend(self._provider.format_tool_results(results))
                continue

            return AgentLoopResult(
                success=True,
                final_message=turn.message,
                messages=tuple(messages),
                tool_results=tuple(tool_results),
                iterations=iteration,
                usage=tuple(usage_events),
            )

        return AgentLoopResult(
            success=False,
            final_message=None,
            messages=tuple(messages),
            tool_results=tuple(tool_results),
            iterations=self._limits.max_iterations,
            usage=tuple(usage_events),
            error=f"Agent loop exceeded max iterations ({self._limits.max_iterations}).",
        )

    async def _collect_turn(self, request: ModelRequest) -> "_CollectedTurn":
        message_delta_parts: list[str] = []
        message_done: str | None = None
        tool_calls: list[ToolCall] = []
        usage: list[dict[str, Any]] = []

        try:
            async for event in self._provider.stream(request):
                if event.event_type == "message_delta" and event.content:
                    message_delta_parts.append(event.content)
                elif event.event_type == "message_done":
                    message_done = event.content or ""
                elif event.event_type == "tool_call" and event.tool_call is not None:
                    tool_calls.append(event.tool_call)
                elif event.event_type == "usage" and event.usage is not None:
                    usage.append(event.usage)
                elif event.event_type == "error":
                    return _CollectedTurn(
                        message=None,
                        tool_calls=tool_calls,
                        usage=usage,
                        error=event.error or "Model provider returned an error event.",
                    )
        except Exception as exc:
            return _CollectedTurn(
                message=None,
                tool_calls=tool_calls,
                usage=usage,
                error=f"{type(exc).__name__}: {exc}",
            )

        return _CollectedTurn(
            message=message_done if message_done is not None else "".join(message_delta_parts),
            tool_calls=tool_calls,
            usage=usage,
            error=None,
        )


def _build_assistant_message(
    text: str | None, tool_calls: Sequence[ToolCall]
) -> AgentMessage | None:
    if not text and not tool_calls:
        return None
    return AgentMessage(
        role="assistant",
        content=text or "",
        provider_metadata={
            "tool_calls": [
                {
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                    "freeform_input": call.freeform_input,
                    "provider_metadata": call.provider_metadata,
                }
                for call in tool_calls
            ]
        },
    )


@dataclass(frozen=True)
class _CollectedTurn:
    message: str | None
    tool_calls: list[ToolCall]
    usage: list[dict[str, Any]]
    error: str | None
