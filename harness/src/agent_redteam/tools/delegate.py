"""Delegate a bounded objective to a fresh sub-agent (orchestrator-worker pattern).

The parent planner hands one sub-objective to a child ReAct loop that has its own
context window and the same low-level tools (minus delegate, so depth = 1). The
child shares the engagement store, so its topology discoveries persist to SQLite
and flow back to the parent. Only a summary returns to the parent's context.
"""

from collections.abc import Callable

from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.loop import AgentLoop, AgentLoopLimits
from agent_redteam.llm.types import AgentMessage, ProviderHarness
from agent_redteam.targets.state import EngagementState
from agent_redteam.tools.registry import ToolRegistry
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition

DEFAULT_DELEGATE_MAX_ITERATIONS = 25

# Set by simple_react.main(): a zero-arg factory returning a registry WITHOUT
# delegate (depth cap), and the live provider harness for the child loop.
REGISTRY_FACTORY_KEY = "delegate_registry_factory"
PROVIDER_HARNESS_KEY = "provider_harness"


class DelegateArgs(ToolArgs):
    objective: str = Field(
        description="One bounded objective for the sub-agent (e.g. 'get a foothold on "
        "db-10-0-0-9 using the creds recorded for web-10-0-0-12').",
    )
    host: str | None = Field(
        default=None,
        description="Optional topology host id the sub-objective centers on, for context.",
    )
    max_iterations: int = Field(
        default=DEFAULT_DELEGATE_MAX_ITERATIONS,
        ge=1,
        le=200,
        description="Step budget for the sub-agent loop (1-200).",
    )


def delegate_definition() -> ToolDefinition:
    return ToolDefinition(
        name="delegate",
        description=(
            "Hand one bounded objective to a sub-agent with its own context and the same "
            "low-level tools. Returns the sub-agent's summary plus any hosts it discovered.\n\n"
            "Usage:\n"
            "- Use for a self-contained chunk of work (a pivot, a host's recon) to keep "
            "your own context focused.\n"
            "- The sub-agent shares the topology store; its findings persist — read_topology "
            "after to see them.\n"
            "- The sub-agent cannot delegate further (depth is capped at one)."
        ),
        input_schema=tool_input_schema(DelegateArgs),
        input_model=DelegateArgs,
        parallel_safe=False,
        mutating=True,
    )


async def delegate_tool(context: AgentContext, tool_call: ToolCall) -> str:
    arguments = DelegateArgs.model_validate(tool_call.arguments or {})
    provider = _require_provider(context)
    build_child_registry = _require_registry_factory(context)
    parent_state = _require_engagement_state(context)
    base_prompt = _system_prompt_base(context)

    before_hosts = set(parent_state.hosts)

    child_context = AgentContext(
        engagement_id=context.engagement_id,
        metadata=dict(context.metadata),  # shallow copy: shared store/settings, isolated turn state
    )
    loop = AgentLoop(
        provider=provider,
        tool_registry=build_child_registry(),
        limits=AgentLoopLimits(max_iterations=arguments.max_iterations),
    )
    child_system = _child_system_prompt(base_prompt, parent_state, arguments)
    child_messages = [
        AgentMessage(role="system", content=child_system),
        AgentMessage(role="user", content=arguments.objective),
    ]
    result = await loop.run(child_context, child_messages)

    final_state = _require_engagement_state(child_context)
    context.metadata["engagement_state"] = final_state
    new_hosts = sorted(set(final_state.hosts) - before_hosts)
    outcome = "finished" if result.success else f"stopped after {result.iterations} steps"
    summary = result.final_message or "(no summary returned)"
    discovered = f" discovered_hosts={', '.join(new_hosts)}" if new_hosts else ""
    return f"delegation {outcome}.{discovered}\n{summary}"


def _child_system_prompt(base: str, state: EngagementState, arguments: DelegateArgs) -> str:
    focus = f"\nFocus host: {arguments.host}" if arguments.host else ""
    return (
        f"{base}\n\n## Current topology\n\n{state.topology_prompt_block()}\n\n"
        f"## Delegated objective\n\nYou are a sub-agent. Achieve ONLY this objective, then "
        f"call finish with a concise summary of what you did and what you found.{focus}"
    )


def _require_provider(context: AgentContext) -> ProviderHarness:
    raw = context.metadata.get(PROVIDER_HARNESS_KEY)
    if raw is None:
        msg = f"{PROVIDER_HARNESS_KEY} is missing from agent context metadata."
        raise RuntimeError(msg)
    return raw  # type: ignore[return-value]


def _require_registry_factory(context: AgentContext) -> Callable[[], ToolRegistry]:
    raw = context.metadata.get(REGISTRY_FACTORY_KEY)
    if not callable(raw):
        msg = f"{REGISTRY_FACTORY_KEY} is missing from agent context metadata."
        raise RuntimeError(msg)
    return raw


def _require_engagement_state(context: AgentContext) -> EngagementState:
    raw = context.metadata.get("engagement_state")
    if isinstance(raw, EngagementState):
        return raw
    msg = "engagement_state is missing from agent context metadata."
    raise RuntimeError(msg)


def _system_prompt_base(context: AgentContext) -> str:
    raw = context.metadata.get("system_prompt_base")
    return raw if isinstance(raw, str) else ""
