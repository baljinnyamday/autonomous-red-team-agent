from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import DEFAULT_BASH_TIMEOUT_SECONDS, Settings, get_settings
from agent_redteam.execution.run_on_host import run_on_host
from agent_redteam.targets.state import EngagementState
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition


class BashArgs(ToolArgs):
    host: str = Field(
        description="Topology host id to run on (e.g. operator, web-10-0-0-12).",
    )
    command: str = Field(description="Shell command to execute via bash -lc.")
    timeout_seconds: float = Field(
        default=DEFAULT_BASH_TIMEOUT_SECONDS,
        ge=1,
        le=86400,
        description="Wall-clock limit in seconds (1-86400).",
    )


def bash_definition() -> ToolDefinition:
    return ToolDefinition(
        name="bash",
        description=(
            "Run a shell command on an engagement topology host via bash -lc.\n\n"
            "Usage:\n"
            "- Set host to a topology id. NEVER embed ssh in command; remote execution "
            "uses internal SSH from topology address, user, jump hosts, and identity-file.\n"
            "- ALWAYS use grep for regex content search. NEVER invoke grep or rg via bash.\n"
            "- Operator host (operator) runs locally; other hosts run on the target machine."
        ),
        input_schema=tool_input_schema(BashArgs),
        input_model=BashArgs,
        parallel_safe=True,
        mutating=False,
    )


async def bash_tool(context: AgentContext, tool_call: ToolCall) -> str:
    arguments = BashArgs.model_validate(tool_call.arguments or {})
    state = _require_engagement_state(context)
    settings = _settings_from_context(context)

    timeout = settings.resolved_bash_timeout_seconds(arguments.timeout_seconds)
    output, new_state = await run_on_host(
        state,
        arguments.host,
        arguments.command,
        settings,
        timeout_seconds=timeout,
    )
    context.metadata["engagement_state"] = new_state
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
