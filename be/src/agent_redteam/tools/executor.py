import asyncio

from pydantic import ValidationError

from agent_redteam.agents.base import AgentContext
from agent_redteam.tools.registry import ToolRegistry
from agent_redteam.tools.types import ToolCall, ToolDefinition, ToolResult
from agent_redteam.tools.validation import validate_json_arguments


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute_batch(
        self, context: AgentContext, tool_calls: list[ToolCall]
    ) -> list[ToolResult]:
        results: list[ToolResult | None] = [None] * len(tool_calls)
        parallel_group: list[tuple[int, ToolCall]] = []

        async def flush_parallel_group() -> None:
            if not parallel_group:
                return
            group = list(parallel_group)
            parallel_group.clear()
            group_results = await asyncio.gather(
                *(self._execute_one(context, tool_call) for _, tool_call in group)
            )
            for (index, _), result in zip(group, group_results, strict=True):
                results[index] = result

        for index, tool_call in enumerate(tool_calls):
            registered = self._registry.get(tool_call.name)
            if registered is None or registered.definition.parallel_safe:
                parallel_group.append((index, tool_call))
                continue

            await flush_parallel_group()
            results[index] = await self._execute_one(context, tool_call)

        await flush_parallel_group()
        return [result for result in results if result is not None]

    async def _execute_one(self, context: AgentContext, tool_call: ToolCall) -> ToolResult:
        registered = self._registry.get(tool_call.name)
        if registered is None:
            return ToolResult(
                call_id=tool_call.call_id,
                success=False,
                output=f"Tool {tool_call.name!r} is not registered.",
                error="unknown_tool",
            )

        validation_error = _validate_tool_call(registered.definition, tool_call)
        if validation_error is not None:
            return ToolResult(
                call_id=tool_call.call_id,
                success=False,
                output=validation_error,
                error="validation_error",
            )

        try:
            output = await self._registry.call(context, tool_call)
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ToolResult(
                call_id=tool_call.call_id,
                success=False,
                output=f"Tool {tool_call.name!r} failed.",
                error=type(exc).__name__,
            )

        return ToolResult(call_id=tool_call.call_id, success=True, output=output)


def _validate_tool_call(definition: ToolDefinition, tool_call: ToolCall) -> str | None:
    if definition.input_mode == "freeform":
        if tool_call.freeform_input is None:
            return f"Tool {definition.name!r} requires freeform input."
        return None

    if tool_call.arguments is None:
        return f"Tool {definition.name!r} requires JSON arguments."

    if definition.input_model is not None:
        try:
            definition.input_model.model_validate(tool_call.arguments)
        except ValidationError as exc:
            return f"Tool {definition.name!r} arguments failed validation: {exc}."
        return None

    errors = validate_json_arguments(tool_call.arguments, definition.input_schema)
    if errors:
        return f"Tool {definition.name!r} arguments failed validation: {'; '.join(errors)}."
    return None
