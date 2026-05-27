"""Live-path tests for the OpenAI and Anthropic harnesses.

The SDK clients are replaced with lightweight fakes so we exercise the wire
shapes (input items, system prompt, tool specs) without touching the network.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.loop import AgentLoop
from agent_redteam.llm.claude import ClaudeMessagesHarness
from agent_redteam.llm.openai import OpenAIResponsesHarness
from agent_redteam.llm.types import AgentMessage
from agent_redteam.tools.fake import build_test_tool_registry


def _context() -> AgentContext:
    return AgentContext(engagement_id="engagement-1", target="example.com", metadata={})


@dataclass
class _Recorded:
    kwargs: dict[str, Any]


class _FakeOpenAIResponses:
    def __init__(self, payloads: Sequence[dict[str, Any]]) -> None:
        self._payloads = list(payloads)
        self.calls: list[_Recorded] = []

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(_Recorded(kwargs=kwargs))
        return self._payloads[len(self.calls) - 1]


@dataclass
class _FakeOpenAIClient:
    responses: _FakeOpenAIResponses


class _FakeAnthropicMessages:
    def __init__(self, payloads: Sequence[dict[str, Any]]) -> None:
        self._payloads = list(payloads)
        self.calls: list[_Recorded] = []

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(_Recorded(kwargs=kwargs))
        return self._payloads[len(self.calls) - 1]


@dataclass
class _FakeAnthropicClient:
    messages: _FakeAnthropicMessages = field(default_factory=lambda: _FakeAnthropicMessages([]))


def test_openai_loop_runs_tool_then_finishes_and_replays_function_call_history() -> None:
    responses = _FakeOpenAIResponses(
        payloads=[
            {
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "echo_json",
                        "arguments": '{"value": "ok"}',
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "all done"}],
                    }
                ],
            },
        ]
    )
    client = _FakeOpenAIClient(responses=responses)
    harness = OpenAIResponsesHarness(model="gpt-test", client=client)  # type: ignore[arg-type]
    loop = AgentLoop(provider=harness, tool_registry=build_test_tool_registry())

    result = asyncio.run(
        loop.run(
            _context(),
            [
                AgentMessage(role="system", content="be careful"),
                AgentMessage(role="user", content="please echo"),
            ],
        )
    )

    assert result.success is True
    assert result.final_message == "all done"
    assert [usage for usage in result.usage] == [{"input_tokens": 10, "output_tokens": 5}]

    first_call = responses.calls[0].kwargs
    assert first_call["model"] == "gpt-test"
    assert first_call["instructions"] == "be careful"
    assert first_call["parallel_tool_calls"] is True
    assert {"role": "user", "content": "please echo"} in first_call["input"]
    tool_spec = first_call["tools"][0]
    assert tool_spec["type"] == "function"
    assert tool_spec["strict"] is True

    second_call = responses.calls[1].kwargs
    items = second_call["input"]
    function_call_items = [item for item in items if item.get("type") == "function_call"]
    function_output_items = [item for item in items if item.get("type") == "function_call_output"]
    assert len(function_call_items) == 1
    assert function_call_items[0]["call_id"] == "call_1"
    assert function_call_items[0]["name"] == "echo_json"
    assert json.loads(function_call_items[0]["arguments"]) == {"value": "ok"}
    assert function_output_items == [
        {"type": "function_call_output", "call_id": "call_1", "output": '{"value": "ok"}'}
    ]


def test_claude_loop_runs_tool_then_finishes_and_replays_tool_use_history() -> None:
    messages = _FakeAnthropicMessages(
        payloads=[
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "calling tool"},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "echo_json",
                        "input": {"value": "ok"},
                    },
                ],
                "usage": {"input_tokens": 8, "output_tokens": 3},
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "all done"}],
                "usage": {"input_tokens": 4, "output_tokens": 2},
            },
        ]
    )
    client = _FakeAnthropicClient(messages=messages)
    harness = ClaudeMessagesHarness(
        model="claude-test",
        max_tokens=512,
        client=client,  # type: ignore[arg-type]
    )
    loop = AgentLoop(provider=harness, tool_registry=build_test_tool_registry())

    result = asyncio.run(
        loop.run(
            _context(),
            [
                AgentMessage(role="system", content="follow the rules"),
                AgentMessage(role="user", content="please echo"),
            ],
        )
    )

    assert result.success is True
    assert result.final_message == "all done"
    assert len(result.usage) == 2

    first_call = messages.calls[0].kwargs
    assert first_call["model"] == "claude-test"
    assert first_call["max_tokens"] == 512
    assert first_call["system"] == "follow the rules"
    wire_messages_first = first_call["messages"]
    assert wire_messages_first == [
        {"role": "user", "content": [{"type": "text", "text": "please echo"}]}
    ]
    tool_spec = first_call["tools"][0]
    assert set(tool_spec.keys()) == {"name", "description", "input_schema"}

    second_call = messages.calls[1].kwargs
    wire_messages_second = second_call["messages"]
    assert wire_messages_second[0]["role"] == "user"
    assert wire_messages_second[1]["role"] == "assistant"
    assistant_blocks = wire_messages_second[1]["content"]
    assert any(block.get("type") == "text" for block in assistant_blocks)
    assert any(
        block.get("type") == "tool_use" and block.get("id") == "toolu_1"
        for block in assistant_blocks
    )
    assert wire_messages_second[2]["role"] == "user"
    tool_result_blocks = wire_messages_second[2]["content"]
    assert tool_result_blocks == [
        {
            "type": "tool_result",
            "tool_use_id": "toolu_1",
            "content": '{"value": "ok"}',
            "is_error": False,
        }
    ]


def test_openai_stream_surfaces_provider_errors_via_error_event() -> None:
    class _Boom:
        async def create(self, **_: Any) -> dict[str, Any]:
            raise RuntimeError("network down")

    client = _FakeOpenAIClient(responses=_Boom())  # type: ignore[arg-type]
    harness = OpenAIResponsesHarness(model="gpt-test", client=client)  # type: ignore[arg-type]
    loop = AgentLoop(provider=harness, tool_registry=build_test_tool_registry())

    result = asyncio.run(loop.run(_context(), [AgentMessage(role="user", content="go")]))

    assert result.success is False
    assert result.error is not None
    assert "network down" in result.error


def test_claude_stream_surfaces_provider_errors_via_error_event() -> None:
    class _Boom:
        async def create(self, **_: Any) -> dict[str, Any]:
            raise RuntimeError("rate limited")

    client = _FakeAnthropicClient(messages=_Boom())  # type: ignore[arg-type]
    harness = ClaudeMessagesHarness(model="claude-test", client=client)  # type: ignore[arg-type]
    loop = AgentLoop(provider=harness, tool_registry=build_test_tool_registry())

    result = asyncio.run(loop.run(_context(), [AgentMessage(role="user", content="go")]))

    assert result.success is False
    assert result.error is not None
    assert "rate limited" in result.error
