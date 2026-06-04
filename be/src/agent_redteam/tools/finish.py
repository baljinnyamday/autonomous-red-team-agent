from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition

FINISH_TOOL_NAME = "finish"


class FinishArgs(ToolArgs):
    reason: str = Field(
        default="",
        description="Short summary of why the engagement objective is complete.",
    )


def finish_definition() -> ToolDefinition:
    return ToolDefinition(
        name=FINISH_TOOL_NAME,
        description=(
            "Declare the engagement objective complete and end the autonomous run. "
            "Call this only when the objective is genuinely met, and do not call any "
            "further tools afterward."
        ),
        input_schema=tool_input_schema(FinishArgs),
        input_model=FinishArgs,
        parallel_safe=True,
        mutating=False,
    )


async def finish(_context: AgentContext, tool_call: ToolCall) -> str:
    arguments = FinishArgs.model_validate(tool_call.arguments or {})
    if arguments.reason:
        return f"Objective marked complete: {arguments.reason}"
    return "Objective marked complete."
