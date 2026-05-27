from pydantic import Field

from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import InputMode, ToolDefinition

APPLY_PATCH_TOOL_NAME = "apply_patch"


class PatchArgs(ToolArgs):
    patch_text: str = Field(
        alias="patchText",
        description="Patch text to render or route. V1 does not apply it.",
    )


PATCH_TEXT_SCHEMA = tool_input_schema(PatchArgs)


def apply_patch_tool_definition(input_mode: InputMode) -> ToolDefinition:
    schema = PATCH_TEXT_SCHEMA if input_mode == "json" else {"type": "string"}
    return ToolDefinition(
        name=APPLY_PATCH_TOOL_NAME,
        description="Accept a patch-shaped payload. V1 records/renders only and does not apply it.",
        input_schema=schema,
        input_model=PatchArgs if input_mode == "json" else None,
        input_mode=input_mode,
        parallel_safe=False,
        mutating=True,
    )
