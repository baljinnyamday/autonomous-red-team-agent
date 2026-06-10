"""Live-path tests for ``OpenAIChatCompletionsHarness`` (industry-standard
OpenAI-compatible endpoint used by vLLM, Ollama, Together, Groq, OpenRouter,
etc.)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.loop import AgentLoop
from agent_redteam.llm.openai_chat import OpenAIChatCompletionsHarness
from agent_redteam.llm.types import AgentMessage
from agent_redteam.tools.fake import build_test_tool_registry
from agent_redteam.tools.patch import apply_patch_tool_definition


def _context() -> AgentContext:
    return AgentContext(engagement_id="engagement-1", metadata={})


@dataclass
class _Recorded:
    kwargs: dict[str, Any]


class _FakeChatCompletions:
    def __init__(self, payloads: Sequence[dict[str, Any]]) -> None:
        self._payloads = list(payloads)
        self.calls: list[_Recorded] = []

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(_Recorded(kwargs=kwargs))
        return self._payloads[len(self.calls) - 1]


@dataclass
class _FakeChat:
    completions: _FakeChatCompletions


@dataclass
class _FakeOpenAIClient:
    chat: _FakeChat


def test_chat_completions_renders_function_tool_with_nested_function_key() -> None:
    harness = OpenAIChatCompletionsHarness(model="llama-test")
    rendered = harness.render_tools([apply_patch_tool_definition("json")])[0]

    assert rendered["type"] == "function"
    assert "function" in rendered
    assert rendered["function"]["name"] == "apply_patch"
    assert rendered["function"]["parameters"]["properties"]["patchText"]["type"] == "string"
    assert "strict" not in rendered["function"]


def test_chat_completions_strict_tools_flag_emits_strict_true() -> None:
    harness = OpenAIChatCompletionsHarness(model="gpt-test", strict_tools=True)
    rendered = harness.render_tools([apply_patch_tool_definition("json")])[0]

    assert rendered["function"]["strict"] is True


def test_chat_completions_loop_runs_tool_then_finishes_and_replays_tool_calls() -> None:
    payloads = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "echo_json",
                                    "arguments": '{"value": "ok"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7},
        },
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "all done"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 3},
        },
    ]
    completions = _FakeChatCompletions(payloads=payloads)
    client = _FakeOpenAIClient(chat=_FakeChat(completions=completions))
    harness = OpenAIChatCompletionsHarness(
        model="llama-test",
        base_url="http://localhost:11434/v1",
        api_key="dummy",
        client=client,  # type: ignore[arg-type]
    )
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
    assert len(result.usage) == 2

    first_kwargs = completions.calls[0].kwargs
    assert first_kwargs["model"] == "llama-test"
    assert first_kwargs["parallel_tool_calls"] is True
    assert first_kwargs["messages"] == [
        {"role": "system", "content": "be careful"},
        {"role": "user", "content": "please echo"},
    ]
    assert first_kwargs["tools"][0]["type"] == "function"

    second_kwargs = completions.calls[1].kwargs
    wire_messages = second_kwargs["messages"]
    assistant_messages = [m for m in wire_messages if m.get("role") == "assistant"]
    tool_messages = [m for m in wire_messages if m.get("role") == "tool"]
    assert len(assistant_messages) == 1
    assistant_tool_calls = assistant_messages[0]["tool_calls"]
    assert assistant_tool_calls[0]["id"] == "call_1"
    assert assistant_tool_calls[0]["type"] == "function"
    assert assistant_tool_calls[0]["function"]["name"] == "echo_json"
    assert json.loads(assistant_tool_calls[0]["function"]["arguments"]) == {"value": "ok"}
    assert tool_messages == [
        {"role": "tool", "tool_call_id": "call_1", "content": '{"value": "ok"}'}
    ]


def test_chat_completions_surfaces_provider_errors_via_error_event() -> None:
    class _Boom:
        async def create(self, **_: Any) -> dict[str, Any]:
            raise RuntimeError("connection refused")

    client = _FakeOpenAIClient(chat=_FakeChat(completions=_Boom()))  # type: ignore[arg-type]
    harness = OpenAIChatCompletionsHarness(model="llama-test", client=client)  # type: ignore[arg-type]
    loop = AgentLoop(provider=harness, tool_registry=build_test_tool_registry())

    result = asyncio.run(loop.run(_context(), [AgentMessage(role="user", content="go")]))

    assert result.success is False
    assert result.error is not None
    assert "connection refused" in result.error


def test_chat_completions_treats_length_finish_reason_as_error() -> None:
    payloads = [
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "partial..."},
                    "finish_reason": "length",
                }
            ]
        }
    ]
    completions = _FakeChatCompletions(payloads=payloads)
    client = _FakeOpenAIClient(chat=_FakeChat(completions=completions))
    harness = OpenAIChatCompletionsHarness(model="llama-test", client=client)  # type: ignore[arg-type]
    loop = AgentLoop(provider=harness, tool_registry=build_test_tool_registry())

    result = asyncio.run(loop.run(_context(), [AgentMessage(role="user", content="long")]))

    assert result.success is False
    assert result.error is not None
    assert "length" in result.error
