import asyncio
from pathlib import Path

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings
from agent_redteam.targets.store import EngagementStore
from agent_redteam.tools.record_attempt import record_attempt_definition, record_attempt_tool
from agent_redteam.tools.types import ToolCall


def _context(store: EngagementStore) -> AgentContext:
    return AgentContext(
        engagement_id="eng-1",
        metadata={"engagement_store": store, "settings": Settings()},
    )


def _record(context: AgentContext, arguments: dict[str, object]) -> str:
    tool_call = ToolCall(call_id="a1", name="record_attempt", arguments=arguments)
    return asyncio.run(record_attempt_tool(context, tool_call))


def test_record_attempt_schema_is_strict_openai_compatible() -> None:
    schema = record_attempt_definition().input_schema
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(properties.keys())
    assert "default" not in properties["technique"]
    assert "default" not in properties["outcome"]
    assert properties["target"]["default"] is None


def test_ledger_accumulates_and_persists(tmp_path: Path) -> None:
    store = EngagementStore.connect(tmp_path / "engagement-eng-1.db")
    context = _context(store)

    _record(context, {"technique": "ssh spray", "target": "web", "outcome": "failure"})
    out = _record(context, {"technique": "exploit struts", "target": "web", "outcome": "success"})

    assert "attempts: 2" in out
    assert "[failure] ssh spray -> web" in out
    assert "[success] exploit struts -> web" in out
    assert len(store.list_attempts("eng-1")) == 2


def test_repeat_of_failed_technique_is_flagged(tmp_path: Path) -> None:
    store = EngagementStore.connect(tmp_path / "engagement-eng-1.db")
    context = _context(store)

    _record(context, {"technique": "ssh spray", "target": "web", "outcome": "blocked"})
    out = _record(context, {"technique": "ssh spray", "target": "web", "outcome": "failure"})

    assert out.startswith("⚠ repeat")
