import asyncio

from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.events import LoopEvent, fan_out
from agent_redteam.llm.fake import FakeProviderHarness
from agent_redteam.llm.types import AgentMessage, ModelEvent
from agent_redteam.simple_react import _load_system_prompt, _run_task, _usage_observer
from agent_redteam.tools.registry import ToolRegistry


def test_load_system_prompt_from_packaged_markdown() -> None:
    prompt = _load_system_prompt()

    assert prompt
    assert prompt == prompt.strip()


def test_run_task_uses_markdown_system_prompt() -> None:
    provider = FakeProviderHarness([[ModelEvent(event_type="message_done", content="done")]])

    asyncio.run(
        _run_task(
            AgentContext(engagement_id="engagement-1", metadata={}),
            provider,
            ToolRegistry(),
            fan_out([]),
            "hello",
        )
    )

    messages = provider.requests[0].messages
    assert messages[0].role == "system"
    assert messages[0].content == _load_system_prompt()
    assert messages[1].role == "user"
    assert messages[1].content == "hello"


def test_run_task_appends_new_task_to_existing_history() -> None:
    provider = FakeProviderHarness([[ModelEvent(event_type="message_done", content="new done")]])
    history = [
        AgentMessage(role="system", content="system"),
        AgentMessage(role="user", content="old task"),
        AgentMessage(role="assistant", content="old done"),
    ]

    result = asyncio.run(
        _run_task(
            AgentContext(engagement_id="engagement-1", metadata={}),
            provider,
            ToolRegistry(),
            fan_out([]),
            "new task",
            history,
        )
    )

    messages = provider.requests[0].messages
    assert [message.content for message in messages] == [
        "system",
        "old task",
        "old done",
        "new task",
    ]
    assert [message.content for message in result.messages] == [
        "system",
        "old task",
        "old done",
        "new task",
        "new done",
    ]


def test_usage_observer_collects_usage_events() -> None:
    usage_events: list[dict[str, object]] = []
    observe = _usage_observer(usage_events)

    observe(LoopEvent(type="usage", usage={"input_tokens": 10}))
    observe(LoopEvent(type="assistant_message", text="done"))

    assert usage_events == [{"input_tokens": 10}]
