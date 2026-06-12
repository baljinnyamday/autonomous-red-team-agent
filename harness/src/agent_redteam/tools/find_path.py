from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.targets.graph import OPERATOR_HOST_ID
from agent_redteam.targets.nx_graph import build_digraph, reachable_from, shortest_path
from agent_redteam.targets.state import EngagementState
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition


class FindPathArgs(ToolArgs):
    source: str | None = Field(
        default=None,
        description="Host id to start from. Defaults to operator.",
    )
    target: str | None = Field(
        default=None,
        description="Host id to reach. Omit to list everything reachable from source.",
    )


def find_path_definition() -> ToolDefinition:
    return ToolDefinition(
        name="find_path",
        description=(
            "Query the discovered topology graph for reachability and the shortest known "
            "path between hosts. Derived from recorded provenance (discovered_from / via); "
            "reflects only what has been found so far.\n\n"
            "Usage:\n"
            "- Call to plan a pivot: which hosts are reachable from a foothold, or the "
            "hop sequence to a goal host.\n"
            "- Record new hosts with update_topology first so they appear in the graph.\n"
            "- Read-only; never changes state."
        ),
        input_schema=tool_input_schema(FindPathArgs),
        input_model=FindPathArgs,
        parallel_safe=True,
        mutating=False,
    )


async def find_path_tool(context: AgentContext, tool_call: ToolCall) -> str:
    arguments = FindPathArgs.model_validate(tool_call.arguments or {})
    state = _require_engagement_state(context)
    graph = build_digraph(state)

    source = arguments.source or OPERATOR_HOST_ID
    if source not in graph:
        return f"Unknown source host {source!r}. Use a host id from the topology."

    if arguments.target:
        if arguments.target not in graph:
            return (
                f"Unknown target host {arguments.target!r}. Record it with update_topology first."
            )
        path = shortest_path(graph, source, arguments.target)
        if path is None:
            return f"No known path from {source} to {arguments.target}."
        return f"path {source} -> {arguments.target}: {' -> '.join(path)} ({len(path) - 1} hops)"

    reachable = sorted(reachable_from(graph, source))
    if not reachable:
        return f"No hosts reachable from {source} in the discovered graph yet."
    return f"reachable from {source} ({len(reachable)}): {', '.join(reachable)}"


def _require_engagement_state(context: AgentContext) -> EngagementState:
    raw = context.metadata.get("engagement_state")
    if isinstance(raw, EngagementState):
        return raw
    msg = "engagement_state is missing from agent context metadata."
    raise RuntimeError(msg)
