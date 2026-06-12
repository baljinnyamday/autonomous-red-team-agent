import asyncio
from pathlib import Path

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings
from agent_redteam.llm.fake import FakeProviderHarness
from agent_redteam.llm.types import ModelEvent
from agent_redteam.simple_react import build_production_registry
from agent_redteam.targets.state import EngagementState
from agent_redteam.targets.store import EngagementStore
from agent_redteam.tools.delegate import (
    PROVIDER_HARNESS_KEY,
    REGISTRY_FACTORY_KEY,
    delegate_definition,
    delegate_tool,
)
from agent_redteam.tools.types import ToolCall


def test_delegate_schema_is_strict_openai_compatible() -> None:
    schema = delegate_definition().input_schema
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(properties.keys())
    assert "default" not in properties["objective"]
    assert properties["max_iterations"]["default"] == 25


def test_child_registry_omits_delegate_for_depth_cap() -> None:
    assert "delegate" in build_production_registry(frozenset({"delegate"}))
    assert "delegate" not in build_production_registry()


def test_delegate_runs_subagent_and_threads_discoveries_back(tmp_path: Path) -> None:
    store = EngagementStore.connect(tmp_path / "engagement-eng-1.db")
    store.ensure_local_host("eng-1")
    state = store.load_state("eng-1")

    # Sub-agent records a new host, then ends its turn with a summary message.
    provider = FakeProviderHarness(
        [
            [
                ModelEvent(
                    event_type="tool_call",
                    tool_call=ToolCall(
                        call_id="c1",
                        name="update_topology",
                        arguments={
                            "host": "db",
                            "address": "10.0.0.99",
                            "discovered_from": "operator",
                        },
                    ),
                )
            ],
            [ModelEvent(event_type="message_done", content="foothold on db established")],
        ]
    )

    context = AgentContext(
        engagement_id="eng-1",
        metadata={
            "settings": Settings(),
            "engagement_state": state,
            "engagement_store": store,
            "system_prompt_base": "base prompt",
            PROVIDER_HARNESS_KEY: provider,
            REGISTRY_FACTORY_KEY: lambda: build_production_registry(),
        },
    )
    tool_call = ToolCall(
        call_id="d1",
        name="delegate",
        arguments={"objective": "get a foothold on the db host"},
    )

    summary = asyncio.run(delegate_tool(context, tool_call))

    assert "discovered_hosts=db" in summary
    assert "foothold on db established" in summary
    assert store.host_exists("eng-1", "db")
    threaded: EngagementState = context.metadata["engagement_state"]
    assert "db" in threaded.hosts
