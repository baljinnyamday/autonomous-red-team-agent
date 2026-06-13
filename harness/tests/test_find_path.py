import asyncio

from agent_redteam.agents.base import AgentContext
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.topology import Transport
from agent_redteam.tools.find_path import find_path_definition, find_path_tool
from agent_redteam.tools.types import ToolCall


def _state() -> EngagementState:
    return EngagementState(
        engagement_id="eng-1",
        hosts={
            "operator": HostRuntime(transport=Transport.LOCAL),
            "web": HostRuntime(
                transport=Transport.REMOTE, address="10.0.0.10", discovered_from="operator"
            ),
            "db": HostRuntime(
                transport=Transport.REMOTE, address="10.0.0.11", discovered_from="web"
            ),
        },
    )


def _call(arguments: dict[str, object]) -> str:
    context = AgentContext(engagement_id="eng-1", metadata={"engagement_state": _state()})
    tool_call = ToolCall(call_id="c1", name="find_path", arguments=arguments)
    return asyncio.run(find_path_tool(context, tool_call))


def test_find_path_schema_is_strict_openai_compatible() -> None:
    schema = find_path_definition().input_schema
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["source", "target"]
    assert schema["properties"]["source"]["default"] is None


def test_find_path_lists_reachable_from_operator() -> None:
    assert "reachable from operator (2): db, web" in _call({})


def test_find_path_returns_shortest_path_to_target() -> None:
    assert "operator -> web -> db (2 hops)" in _call({"target": "db"})


def test_find_path_reports_unknown_target() -> None:
    assert "Unknown target host" in _call({"target": "ghost"})
