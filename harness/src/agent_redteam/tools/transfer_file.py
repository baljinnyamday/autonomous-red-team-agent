from typing import Literal

from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import (
    DEFAULT_TRANSFER_TIMEOUT_SECONDS,
    Settings,
    get_settings,
)
from agent_redteam.execution.artifacts import resolve_artifact_path
from agent_redteam.execution.transfer import transfer_file_on_host
from agent_redteam.targets.state import EngagementState
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition

TransferDirection = Literal["download", "upload"]


class TransferFileArgs(ToolArgs):
    host: str = Field(
        description="Topology host id to transfer with (e.g. operator, web-10-0-0-12).",
    )
    direction: TransferDirection = Field(
        description='Transfer direction: "download" from host to operator, "upload" to host.',
    )
    remote_path: str = Field(
        description="Absolute path on the target host.",
    )
    local_name: str | None = Field(
        default=None,
        description="Artifact filename under .runs/engagement-{id}/artifacts/{host}/.",
    )
    timeout_seconds: float = Field(
        default=DEFAULT_TRANSFER_TIMEOUT_SECONDS,
        ge=1,
        le=86400,
        description="Wall-clock limit in seconds (1-86400).",
    )


def transfer_file_definition() -> ToolDefinition:
    return ToolDefinition(
        name="transfer_file",
        description=(
            "Transfer a file between an engagement topology host and the operator machine.\n\n"
            "Usage:\n"
            "- ALWAYS use transfer_file for operator↔host file moves. NEVER invoke scp, "
            "sftp, or rsync via bash.\n"
            "- Downloads land under .runs/engagement-{id}/artifacts/{host}/.\n"
            "- After download, inspect text with grep(host=operator) or bash; record "
            "findings via update_topology.\n"
            "- Prefer grep/cat on remote for small text secrets; download for binary, "
            "large, or proof artifacts."
        ),
        input_schema=tool_input_schema(TransferFileArgs),
        input_model=TransferFileArgs,
        parallel_safe=True,
        mutating=True,
    )


async def transfer_file_tool(context: AgentContext, tool_call: ToolCall) -> str:
    arguments = TransferFileArgs.model_validate(tool_call.arguments or {})
    state = _require_engagement_state(context)
    settings = _settings_from_context(context)
    engagement_id = context.engagement_id or state.engagement_id

    local_path = resolve_artifact_path(
        settings,
        engagement_id,
        arguments.host,
        local_name=arguments.local_name,
        remote_path=arguments.remote_path,
    )
    timeout = settings.resolved_transfer_timeout_seconds(arguments.timeout_seconds)
    size, new_state = await transfer_file_on_host(
        state,
        arguments.host,
        direction=arguments.direction,
        remote_path=arguments.remote_path,
        local_path=local_path,
        settings=settings,
        timeout_seconds=timeout,
    )
    context.metadata["engagement_state"] = new_state
    remote_spec = f"{arguments.host}:{arguments.remote_path}"
    if arguments.direction == "download":
        summary = f"{remote_spec} -> {local_path}"
    else:
        summary = f"{local_path} -> {remote_spec}"
    return f"Transferred {size} bytes: {arguments.direction} {summary}"


def _require_engagement_state(context: AgentContext) -> EngagementState:
    raw = context.metadata.get("engagement_state")
    if isinstance(raw, EngagementState):
        return raw
    msg = "engagement_state is missing from agent context metadata."
    raise RuntimeError(msg)


def _settings_from_context(context: AgentContext) -> Settings:
    raw = context.metadata.get("settings")
    if isinstance(raw, Settings):
        return raw
    return get_settings()
