import asyncio
import json

from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.tools.registry import ToolRegistry
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition


class EchoJsonArgs(ToolArgs):
    value: object = Field(description="Value to echo back to the model.")


class SlowEchoArgs(ToolArgs):
    message: str = Field(description="Message to return after the delay.")
    delay: float = Field(description="Delay in seconds before returning the message.")


def echo_json_definition(*, parallel_safe: bool = True) -> ToolDefinition:
    return ToolDefinition(
        name="echo_json",
        description="Return the supplied JSON arguments as a deterministic JSON string.",
        input_schema=tool_input_schema(EchoJsonArgs),
        input_model=EchoJsonArgs,
        parallel_safe=parallel_safe,
        mutating=False,
    )


def slow_echo_definition(*, parallel_safe: bool = True) -> ToolDefinition:
    return ToolDefinition(
        name="slow_echo",
        description="Sleep for delay seconds, then return message.",
        input_schema=tool_input_schema(SlowEchoArgs),
        input_model=SlowEchoArgs,
        parallel_safe=parallel_safe,
        mutating=False,
    )


def build_test_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(echo_json_definition(), echo_json)
    registry.register(slow_echo_definition(), slow_echo)
    return registry


async def echo_json(_context: AgentContext, tool_call: ToolCall) -> str:
    return json.dumps(tool_call.arguments or {}, sort_keys=True)


async def slow_echo(_context: AgentContext, tool_call: ToolCall) -> str:
    arguments = SlowEchoArgs.model_validate(tool_call.arguments or {})
    await asyncio.sleep(arguments.delay)
    return arguments.message
