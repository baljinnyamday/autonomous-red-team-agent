from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition

FINISH_TOOL_NAME = "finish"


class FinishArgs(ToolArgs):
    reason: str = Field(
        description="Why the engagement objective is complete (one short paragraph).",
    )


def finish_definition() -> ToolDefinition:
    return ToolDefinition(
        name=FINISH_TOOL_NAME,
        description=(
            "End the autonomous run when the engagement objective is complete.\n\n"
            "Usage:\n"
            "- Call once when the objective is genuinely met or in-scope actions are "
            "exhausted.\n"
            "- Do not call any further tools after finish."
        ),
        input_schema=tool_input_schema(FinishArgs),
        input_model=FinishArgs,
        parallel_safe=True,
        mutating=False,
    )


async def finish(_context: AgentContext, tool_call: ToolCall) -> str:
    arguments = FinishArgs.model_validate(tool_call.arguments or {})
    return f"Objective marked complete: {arguments.reason}"
