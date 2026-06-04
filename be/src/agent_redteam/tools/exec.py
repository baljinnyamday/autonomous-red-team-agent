from pathlib import Path

from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings, get_settings
from agent_redteam.execution.run_on_host import run_on_host
from agent_redteam.targets.scope import TargetScope
from agent_redteam.targets.state import EngagementState, default_state_path
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition


class ExecArgs(ToolArgs):
    host: str = Field(description="Topology host id to run the command on.")
    command: str = Field(description="Shell command to execute via bash -lc on that host.")


def exec_definition() -> ToolDefinition:
    return ToolDefinition(
        name="exec",
        description=(
            "Run a shell command on an in-scope engagement host. Use host ids from the "
            "topology (local operator or remote via on-host runner). Do not embed ssh; "
            "the rm command is blocked."
        ),
        input_schema=tool_input_schema(ExecArgs),
        input_model=ExecArgs,
        parallel_safe=False,
        mutating=True,
    )


async def exec_tool(context: AgentContext, tool_call: ToolCall) -> str:
    arguments = ExecArgs.model_validate(tool_call.arguments or {})
    state = _require_engagement_state(context)
    settings = _settings_from_context(context)
    scope = context.metadata.get("target_scope")
    scope_model = scope if isinstance(scope, TargetScope) else None

    output, new_state = await run_on_host(
        state,
        arguments.host,
        arguments.command,
        settings,
        scope=scope_model,
    )
    context.metadata["engagement_state"] = new_state
    _persist_state(context, new_state, settings)
    return output


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


def _persist_state(context: AgentContext, state: EngagementState, settings: Settings) -> None:
    path = context.metadata.get("engagement_state_path")
    state_path = Path(path) if path else default_state_path(settings)
    state.persist(state_path)
