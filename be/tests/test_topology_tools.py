import asyncio
from pathlib import Path

import pytest

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.store import EngagementStore
from agent_redteam.targets.topology import Transport
from agent_redteam.tools.topology import read_topology_tool, update_topology_tool
from agent_redteam.tools.types import ToolCall


def _context(tmp_path: Path) -> AgentContext:
    state = EngagementState(
        engagement_id="eng-1",
        hosts={"operator": HostRuntime(transport=Transport.LOCAL)},
    )
    store = EngagementStore.connect(tmp_path / "eng.db")
    store.save_state(state)
    return AgentContext(
        engagement_id="eng-1",
        metadata={
            "engagement_state": state,
            "engagement_store": store,
            "settings": Settings(_env_file=None),
        },
    )


def test_update_topology_records_discoveries(tmp_path: Path) -> None:
    context = _context(tmp_path)
    output = asyncio.run(
        update_topology_tool(
            context,
            ToolCall(
                call_id="u1",
                name="update_topology",
                arguments={
                    "host": "web",
                    "address": "10.0.0.12",
                    "tags": ["web"],
                    "services": [{"port": 443, "protocol": "tcp", "product": "nginx"}],
                    "note": "HTTPS landing page",
                },
            ),
        )
    )
    assert "web" in output
    state = context.metadata["engagement_state"]
    assert isinstance(state, EngagementState)
    assert "web" in state.hosts
    assert state.hosts["web"].tags == ["web"]
    assert len(state.hosts["web"].services) == 1


def test_read_topology_returns_verbose_report(tmp_path: Path) -> None:
    context = _context(tmp_path)
    asyncio.run(
        update_topology_tool(
            context,
            ToolCall(
                call_id="u1",
                name="update_topology",
                arguments={"host": "web", "address": "10.0.0.12", "os": "Linux"},
            ),
        )
    )
    report = asyncio.run(
        read_topology_tool(
            context,
            ToolCall(call_id="r1", name="read_topology", arguments={"host": "web"}),
        )
    )
    assert "web:" in report
    assert "os: Linux" in report
    assert "endpoint: 10.0.0.12" in report


def test_create_rejects_duplicate_address(tmp_path: Path) -> None:
    context = _context(tmp_path)
    asyncio.run(
        update_topology_tool(
            context,
            ToolCall(
                call_id="u1",
                name="update_topology",
                arguments={"host": "web-a", "address": "10.0.0.12"},
            ),
        )
    )
    with pytest.raises(ConfigurationError, match="already recorded as host_id 'web-a'"):
        asyncio.run(
            update_topology_tool(
                context,
                ToolCall(
                    call_id="u2",
                    name="update_topology",
                    arguments={"host": "web-b", "address": "10.0.0.12"},
                ),
            )
        )


def test_create_requires_address_for_new_remote_host(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(ConfigurationError, match="requires address"):
        asyncio.run(
            update_topology_tool(
                context,
                ToolCall(call_id="u1", name="update_topology", arguments={"host": "web"}),
            )
        )


def test_existing_host_rejects_connection_overwrite(tmp_path: Path) -> None:
    context = _context(tmp_path)
    asyncio.run(
        update_topology_tool(
            context,
            ToolCall(
                call_id="u1",
                name="update_topology",
                arguments={"host": "web", "address": "10.0.0.12"},
            ),
        )
    )
    with pytest.raises(ConfigurationError, match="Connection fields are immutable"):
        asyncio.run(
            update_topology_tool(
                context,
                ToolCall(
                    call_id="u2",
                    name="update_topology",
                    arguments={"host": "web", "address": "10.0.0.99"},
                ),
            )
        )


def test_existing_host_appends_findings_without_connection_change(tmp_path: Path) -> None:
    context = _context(tmp_path)
    asyncio.run(
        update_topology_tool(
            context,
            ToolCall(
                call_id="u1",
                name="update_topology",
                arguments={"host": "web", "address": "10.0.0.12"},
            ),
        )
    )
    asyncio.run(
        update_topology_tool(
            context,
            ToolCall(
                call_id="u2",
                name="update_topology",
                arguments={
                    "host": "web",
                    "address": "10.0.0.12",
                    "note": "still the same machine",
                },
            ),
        )
    )
    state = context.metadata["engagement_state"]
    assert isinstance(state, EngagementState)
    assert state.hosts["web"].address == "10.0.0.12"
    assert state.hosts["web"].notes == ["still the same machine"]


def test_operator_connection_fields_are_protected(tmp_path: Path) -> None:
    context = _context(tmp_path)
    with pytest.raises(ConfigurationError, match="operator connection fields"):
        asyncio.run(
            update_topology_tool(
                context,
                ToolCall(
                    call_id="u1",
                    name="update_topology",
                    arguments={"host": "operator", "address": "127.0.0.1"},
                ),
            )
        )


def test_overwrite_connection_allows_explicit_change(tmp_path: Path) -> None:
    context = _context(tmp_path)
    asyncio.run(
        update_topology_tool(
            context,
            ToolCall(
                call_id="u1",
                name="update_topology",
                arguments={"host": "web", "address": "10.0.0.12", "user": "ubuntu"},
            ),
        )
    )
    asyncio.run(
        update_topology_tool(
            context,
            ToolCall(
                call_id="u2",
                name="update_topology",
                arguments={
                    "host": "web",
                    "address": "10.0.0.12",
                    "user": "root",
                    "overwrite_connection": True,
                },
            ),
        )
    )
    state = context.metadata["engagement_state"]
    assert isinstance(state, EngagementState)
    assert state.hosts["web"].user == "root"
