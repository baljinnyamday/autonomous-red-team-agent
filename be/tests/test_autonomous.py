import asyncio

import pytest

from agent_redteam.agents.autonomous import parse_duration, run_autonomous
from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.events import LoopEvent
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.llm.fake import FakeProviderHarness
from agent_redteam.llm.types import AgentMessage, ModelEvent
from agent_redteam.tools.fake import build_test_tool_registry
from agent_redteam.tools.finish import finish, finish_definition
from agent_redteam.tools.types import ToolCall


def _registry():
    registry = build_test_tool_registry()
    registry.register(finish_definition(), finish)
    return registry


def _noop(_event: LoopEvent) -> None:
    pass


def _run(provider: FakeProviderHarness, *, deadline: float, now: float):
    return asyncio.run(
        run_autonomous(
            context=AgentContext(engagement_id="eng-1", metadata={}),
            provider=provider,
            registry=_registry(),
            observer=_noop,
            objective="recon the lab",
            messages=[AgentMessage(role="system", content="sys")],
            deadline=deadline,
            clock=lambda: now,
        )
    )


def test_supervisor_reruns_until_agent_calls_finish() -> None:
    provider = FakeProviderHarness(
        [
            [ModelEvent(event_type="message_done", content="working")],
            [
                ModelEvent(
                    event_type="tool_call",
                    tool_call=ToolCall(call_id="c1", name="finish", arguments={"reason": "done"}),
                )
            ],
            [ModelEvent(event_type="message_done", content="all done")],
        ]
    )

    outcome = _run(provider, deadline=1000.0, now=0.0)

    assert outcome.stop_reason == "finished"
    assert outcome.cycles == 2
    assert outcome.result.success is True


def test_supervisor_stops_on_wall_clock_duration() -> None:
    provider = FakeProviderHarness(
        [[ModelEvent(event_type="message_done", content="still working")]]
    )

    outcome = _run(provider, deadline=0.0, now=100.0)

    assert outcome.stop_reason == "duration"
    assert outcome.cycles == 1


def test_parse_duration_accepts_units_and_rejects_bad_input() -> None:
    assert parse_duration("30m") == 1800
    assert parse_duration("45s") == 45
    assert parse_duration("1h") == 3600
    assert parse_duration("90") == 90
    with pytest.raises(ConfigurationError):
        parse_duration("soon")
    with pytest.raises(ConfigurationError):
        parse_duration("0")
