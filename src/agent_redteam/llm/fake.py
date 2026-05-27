from collections.abc import AsyncIterator, Sequence

from agent_redteam.llm.types import AgentMessage, ModelEvent, ModelRequest
from agent_redteam.tools.types import ToolDefinition, ToolResult


class FakeProviderHarness:
    def __init__(self, turns: Sequence[Sequence[ModelEvent]]) -> None:
        self._turns = [list(turn) for turn in turns]
        self._cursor = 0
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        self.requests.append(request)
        if self._cursor >= len(self._turns):
            yield ModelEvent(
                event_type="error",
                error="FakeProviderHarness has no scripted turn left.",
            )
            return

        turn = self._turns[self._cursor]
        self._cursor += 1
        for event in turn:
            yield event

    def render_tools(self, tools: Sequence[ToolDefinition]) -> list[dict[str, object]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "input_mode": tool.input_mode,
                "parallel_safe": tool.parallel_safe,
                "mutating": tool.mutating,
            }
            for tool in tools
        ]

    def format_tool_results(self, results: Sequence[ToolResult]) -> list[AgentMessage]:
        return [
            AgentMessage(
                role="tool",
                content=result.output,
                provider_metadata={
                    "call_id": result.call_id,
                    "success": result.success,
                    "error": result.error,
                },
            )
            for result in results
        ]
