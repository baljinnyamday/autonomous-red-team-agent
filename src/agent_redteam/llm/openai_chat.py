"""OpenAI Chat Completions API harness.

The Chat Completions contract (``POST /v1/chat/completions``) is the
industry-standard wire protocol implemented by virtually every model server
outside OpenAI itself: vLLM, Ollama, llama.cpp, LM Studio, TGI, Together AI,
Groq, OpenRouter, DeepSeek, Mistral, Fireworks, Cerebras, NVIDIA NIM, etc.

This harness is intentionally separate from ``OpenAIResponsesHarness`` because
the two endpoints use different shapes:

- Messages use plain ``{role, content}`` plus ``tool_calls`` / ``tool_call_id``
  fields. The system prompt is a regular ``system`` message, not a top-level
  ``instructions`` parameter.
- Tool specs are nested under ``{"type": "function", "function": {...}}``.
- There is no concept of "custom" / freeform tools; freeform inputs are
  expressed as a JSON-schema function tool that takes a single string arg.

Pass ``base_url`` and ``api_key`` to point at any OpenAI-compatible server
(e.g. ``http://localhost:11434/v1`` for Ollama, ``https://api.together.xyz/v1``
for Together, etc.).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any, cast

from agent_redteam.llm.types import AgentMessage, ModelEvent, ModelRequest
from agent_redteam.tools.patch import APPLY_PATCH_TOOL_NAME, PATCH_TEXT_SCHEMA
from agent_redteam.tools.types import ToolCall, ToolDefinition, ToolResult

if TYPE_CHECKING:
    from openai import AsyncOpenAI


class OpenAIChatCompletionsHarness:
    def __init__(
        self,
        *,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        parallel_tool_calls: bool | None = True,
        strict_tools: bool = False,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.parallel_tool_calls = parallel_tool_calls
        self.strict_tools = strict_tools
        self._client = client

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        client = self._resolve_client()
        wire_messages = self._build_messages(request.messages)
        tools = self.render_tools(request.tools)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": wire_messages,
        }
        if tools:
            kwargs["tools"] = tools
            if self.parallel_tool_calls is not None:
                kwargs["parallel_tool_calls"] = self.parallel_tool_calls

        completion = await client.chat.completions.create(**kwargs)
        completion_dict = _model_to_dict(completion)
        for event in self.normalize_completion(completion_dict):
            yield event

    def render_tools(self, tools: Sequence[ToolDefinition]) -> list[dict[str, Any]]:
        return [self._render_tool(tool) for tool in tools]

    def format_tool_results(self, results: Sequence[ToolResult]) -> list[AgentMessage]:
        messages: list[AgentMessage] = []
        for result in results:
            wire_message: dict[str, Any] = {
                "role": "tool",
                "tool_call_id": result.call_id,
                "content": result.output,
            }
            messages.append(
                AgentMessage(
                    role="tool",
                    content=result.output,
                    provider_metadata={
                        "wire_message": wire_message,
                        "success": result.success,
                        "error": result.error,
                    },
                )
            )
        return messages

    def normalize_completion(self, completion: dict[str, Any]) -> list[ModelEvent]:
        choices = completion.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return [
                ModelEvent(
                    event_type="error",
                    error="Chat completion response had no choices.",
                    provider_metadata=completion,
                )
            ]

        events: list[ModelEvent] = []
        first_choice = choices[0]
        message = first_choice.get("message") if isinstance(first_choice, dict) else None
        if not isinstance(message, dict):
            return [
                ModelEvent(
                    event_type="error",
                    error="Chat completion choice missing message.",
                    provider_metadata=completion,
                )
            ]

        text = message.get("content")
        if isinstance(text, str) and text:
            events.append(
                ModelEvent(event_type="message_done", content=text, provider_metadata=message)
            )

        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for raw_call in tool_calls:
                if not isinstance(raw_call, dict):
                    continue
                events.append(
                    ModelEvent(event_type="tool_call", tool_call=_function_tool_call(raw_call))
                )

        usage = completion.get("usage")
        if isinstance(usage, dict):
            events.append(ModelEvent(event_type="usage", usage=usage))

        finish_reason = (
            first_choice.get("finish_reason") if isinstance(first_choice, dict) else None
        )
        if finish_reason in {"length", "content_filter"}:
            events.append(
                ModelEvent(
                    event_type="error",
                    error=f"Chat completion stopped early: finish_reason={finish_reason}.",
                    provider_metadata=completion,
                )
            )
            return events

        events.append(ModelEvent(event_type="completed", provider_metadata=completion))
        return events

    def _build_messages(self, messages: Sequence[AgentMessage]) -> list[dict[str, Any]]:
        wire_messages: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                if message.content:
                    wire_messages.append({"role": "system", "content": message.content})
                continue

            if message.role == "user":
                wire_messages.append({"role": "user", "content": message.content})
                continue

            if message.role == "assistant":
                wire_message: dict[str, Any] = {"role": "assistant"}
                if message.content:
                    wire_message["content"] = message.content
                tool_calls = [
                    _assistant_tool_call_wire(call)
                    for call in message.provider_metadata.get("tool_calls", [])
                ]
                if tool_calls:
                    wire_message["tool_calls"] = tool_calls
                    wire_message.setdefault("content", None)
                wire_messages.append(wire_message)
                continue

            if message.role == "tool":
                wire = message.provider_metadata.get("wire_message")
                if isinstance(wire, dict):
                    wire_messages.append(wire)
                else:
                    wire_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": message.provider_metadata.get("call_id", ""),
                            "content": message.content,
                        }
                    )
        return wire_messages

    def _render_tool(self, tool: ToolDefinition) -> dict[str, Any]:
        parameters = tool.input_schema
        if tool.input_mode == "freeform":
            parameters = _freeform_function_schema(tool)

        function_spec: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description,
            "parameters": parameters,
        }
        if self.strict_tools:
            function_spec["strict"] = True
        return {"type": "function", "function": function_spec}

    def _resolve_client(self) -> AsyncOpenAI:
        if self._client is not None:
            return self._client
        from openai import AsyncOpenAI

        kwargs: dict[str, Any] = {}
        if self.base_url is not None:
            kwargs["base_url"] = self.base_url
        if self.api_key is not None:
            kwargs["api_key"] = self.api_key
        self._client = AsyncOpenAI(**kwargs)
        return self._client


def _assistant_tool_call_wire(call: dict[str, Any]) -> dict[str, Any]:
    provider_metadata = call.get("provider_metadata")
    if isinstance(provider_metadata, dict) and provider_metadata.get("type") == "function":
        return cast(dict[str, Any], provider_metadata)

    arguments = call.get("arguments") or {}
    if call.get("freeform_input") is not None:
        arguments = {"input": call.get("freeform_input", "")}

    return {
        "id": call.get("call_id", ""),
        "type": "function",
        "function": {
            "name": call.get("name", ""),
            "arguments": json.dumps(arguments),
        },
    }


def _function_tool_call(raw_call: dict[str, Any]) -> ToolCall:
    function = raw_call.get("function") or {}
    if not isinstance(function, dict):
        function = {}
    arguments = function.get("arguments", "{}")
    parsed_arguments: dict[str, Any] = {}
    if isinstance(arguments, str) and arguments:
        parsed = json.loads(arguments)
        if isinstance(parsed, dict):
            parsed_arguments = parsed
    elif isinstance(arguments, dict):
        parsed_arguments = arguments

    return ToolCall(
        call_id=str(raw_call.get("id", "")),
        name=str(function.get("name", "")),
        arguments=parsed_arguments,
        provider_metadata=raw_call,
    )


def _freeform_function_schema(tool: ToolDefinition) -> dict[str, Any]:
    if tool.name == APPLY_PATCH_TOOL_NAME:
        return PATCH_TEXT_SCHEMA
    return {
        "type": "object",
        "properties": {
            "input": {"type": "string"},
        },
        "required": ["input"],
        "additionalProperties": False,
    }


def _model_to_dict(completion: object) -> dict[str, Any]:
    if isinstance(completion, dict):
        return cast(dict[str, Any], completion)
    dumper = getattr(completion, "model_dump", None)
    if callable(dumper):
        result = dumper()
        if isinstance(result, dict):
            return cast(dict[str, Any], result)
    raise TypeError("Chat completion is not convertible to dict.")
