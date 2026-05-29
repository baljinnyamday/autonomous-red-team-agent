"""OpenAI Responses API harness.

Follows the official OpenAI Responses API contract (October 2025+):

- ``client.responses.create(...)`` with model, input items, tools, instructions,
  and ``parallel_tool_calls``.
- ``input`` is a list of input items. User/assistant text uses
  ``{"role": ..., "content": <str>}`` (EasyInputMessage); replays of prior
  response output items go back in verbatim so reasoning and tool-call context
  stays intact when managed manually.
- Tool results are ``{"type": "function_call_output", "call_id", "output"}``
  items, and ``{"type": "custom_tool_call_output", ...}`` for custom tools.
- Function tools are ``{"type": "function", "name", "description", "parameters", "strict"}``;
  custom (freeform) tools are ``{"type": "custom", "name", "description"}``.
- System prompt is the ``instructions`` parameter, not a message.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any, Literal, cast

from agent_redteam.llm.types import AgentMessage, ModelEvent, ModelRequest
from agent_redteam.tools.patch import APPLY_PATCH_TOOL_NAME, PATCH_TEXT_SCHEMA
from agent_redteam.tools.types import ToolCall, ToolDefinition, ToolResult

if TYPE_CHECKING:
    from openai import AsyncOpenAI

ApplyPatchMode = Literal["function", "freeform"]


class OpenAIResponsesHarness:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        parallel_tool_calls: bool = True,
        apply_patch_mode: ApplyPatchMode = "function",
        reasoning_summary: bool = True,
        prompt_cache_key: str | None = None,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.parallel_tool_calls = parallel_tool_calls
        self.apply_patch_mode = apply_patch_mode
        self.reasoning_summary = reasoning_summary
        self.prompt_cache_key = prompt_cache_key
        self._client = client

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        client = self._resolve_client()
        instructions, input_items = self._build_input(request.messages)
        tools = self.render_tools(request.tools)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": input_items,
            "parallel_tool_calls": self.parallel_tool_calls,
        }
        if tools:
            kwargs["tools"] = tools
        if instructions is not None:
            kwargs["instructions"] = instructions
        if self.reasoning_summary:
            kwargs["reasoning"] = {"summary": "auto"}
        if self.prompt_cache_key:
            kwargs["prompt_cache_key"] = self.prompt_cache_key

        response = await client.responses.create(**kwargs)
        response_dict = _model_to_dict(response)
        for event in self.normalize_response(response_dict):
            yield event

    def render_tools(self, tools: Sequence[ToolDefinition]) -> list[dict[str, Any]]:
        return [self._render_tool(tool) for tool in tools]

    def format_tool_results(self, results: Sequence[ToolResult]) -> list[AgentMessage]:
        messages: list[AgentMessage] = []
        for result in results:
            output_item: dict[str, Any] = {
                "type": "function_call_output",
                "call_id": result.call_id,
                "output": result.output,
            }
            messages.append(
                AgentMessage(
                    role="tool",
                    content=result.output,
                    provider_metadata={
                        "input_item": output_item,
                        "success": result.success,
                        "error": result.error,
                    },
                )
            )
        return messages

    def normalize_response(self, response: dict[str, Any]) -> list[ModelEvent]:
        events = self.normalize_output_items(response.get("output", []))
        usage = response.get("usage")
        if isinstance(usage, dict):
            events.append(
                ModelEvent(
                    event_type="usage",
                    usage={
                        **usage,
                        "provider": "openai",
                        "model": _string(response.get("model")) or self.model,
                    },
                )
            )
        if response.get("error") is not None:
            events.append(
                ModelEvent(
                    event_type="error",
                    error=str(response["error"]),
                    provider_metadata={"response": response},
                )
            )
        elif response.get("status") in {"completed", None}:
            output_items = response.get("output", [])
            events.append(
                ModelEvent(
                    event_type="completed",
                    provider_metadata={
                        "response": response,
                        "input_items": output_items if isinstance(output_items, list) else [],
                    },
                )
            )
        return events

    def normalize_output_items(self, output_items: object) -> list[ModelEvent]:
        if not isinstance(output_items, list):
            return [
                ModelEvent(
                    event_type="error",
                    error="OpenAI response output must be a list.",
                )
            ]

        events: list[ModelEvent] = []
        for raw_item in output_items:
            if not isinstance(raw_item, dict):
                continue
            item = cast(dict[str, Any], raw_item)
            item_type = item.get("type")
            if item_type == "reasoning":
                summary = _extract_reasoning_summary(item)
                if summary:
                    events.append(ModelEvent(event_type="thinking", content=summary))
            elif item_type == "message":
                events.append(
                    ModelEvent(
                        event_type="message_done",
                        content=_extract_message_text(item),
                        provider_metadata=item,
                    )
                )
            elif item_type == "function_call":
                events.append(
                    ModelEvent(event_type="tool_call", tool_call=_function_tool_call(item))
                )
            elif item_type == "custom_tool_call":
                events.append(ModelEvent(event_type="tool_call", tool_call=_custom_tool_call(item)))
        return events

    def _build_input(
        self, messages: Sequence[AgentMessage]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        instructions_parts: list[str] = []
        input_items: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                if message.content:
                    instructions_parts.append(message.content)
                continue
            if message.role == "user":
                input_items.append({"role": "user", "content": message.content})
                continue
            if message.role == "assistant":
                if _append_input_items(input_items, message.provider_metadata.get("input_items")):
                    continue
                for call in message.provider_metadata.get("tool_calls", []):
                    input_items.append(_assistant_tool_call_item(call))
                if message.content:
                    input_items.append({"role": "assistant", "content": message.content})
                continue
            if message.role == "tool":
                item = message.provider_metadata.get("input_item")
                if isinstance(item, dict):
                    input_items.append(item)
                else:
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": message.provider_metadata.get("call_id", ""),
                            "output": message.content,
                        }
                    )
        instructions = "\n\n".join(part for part in instructions_parts if part) or None
        return instructions, input_items

    def _render_tool(self, tool: ToolDefinition) -> dict[str, Any]:
        if tool.input_mode == "freeform" and self.apply_patch_mode == "freeform":
            return {
                "type": "custom",
                "name": tool.name,
                "description": tool.description,
            }

        parameters = tool.input_schema
        if tool.input_mode == "freeform":
            parameters = _freeform_function_schema(tool)

        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": parameters,
            "strict": True,
        }

    def _resolve_client(self) -> AsyncOpenAI:
        if self._client is not None:
            return self._client
        if self.api_key is None:
            msg = "OpenAI API key must be provided explicitly by runtime settings."
            raise ValueError(msg)
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client


def _assistant_tool_call_item(call: dict[str, Any]) -> dict[str, Any]:
    provider_metadata = call.get("provider_metadata")
    if isinstance(provider_metadata, dict) and provider_metadata.get("type") in {
        "function_call",
        "custom_tool_call",
    }:
        return cast(dict[str, Any], provider_metadata)

    if call.get("freeform_input") is not None:
        return {
            "type": "custom_tool_call",
            "call_id": call.get("call_id", ""),
            "name": call.get("name", ""),
            "input": call.get("freeform_input", ""),
        }

    arguments = call.get("arguments") or {}
    return {
        "type": "function_call",
        "call_id": call.get("call_id", ""),
        "name": call.get("name", ""),
        "arguments": json.dumps(arguments),
    }


# Server-generated fields present on response output items that the Responses API
# rejects when those items are echoed back as input.
_OUTPUT_ONLY_KEYS = ("status",)


def _append_input_items(input_items: list[dict[str, Any]], raw_items: object) -> bool:
    if not isinstance(raw_items, list):
        return False

    appended = False
    for raw_item in raw_items:
        if isinstance(raw_item, dict):
            input_items.append(_as_input_item(cast(dict[str, Any], raw_item)))
            appended = True
    return appended


def _as_input_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key not in _OUTPUT_ONLY_KEYS}


def _function_tool_call(item: dict[str, Any]) -> ToolCall:
    arguments = item.get("arguments", "{}")
    parsed_arguments: dict[str, Any] = {}
    if isinstance(arguments, str) and arguments:
        parsed = json.loads(arguments)
        if isinstance(parsed, dict):
            parsed_arguments = parsed
    elif isinstance(arguments, dict):
        parsed_arguments = arguments

    return ToolCall(
        call_id=str(item["call_id"]),
        name=str(item["name"]),
        arguments=parsed_arguments,
        provider_metadata=item,
    )


def _custom_tool_call(item: dict[str, Any]) -> ToolCall:
    return ToolCall(
        call_id=str(item["call_id"]),
        name=str(item["name"]),
        freeform_input=str(item.get("input", "")),
        provider_metadata=item,
    )


def _extract_reasoning_summary(item: dict[str, Any]) -> str:
    summary = item.get("summary", [])
    if not isinstance(summary, list):
        return ""
    parts: list[str] = []
    for part in summary:
        if isinstance(part, dict) and part.get("type") == "summary_text":
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _extract_message_text(item: dict[str, Any]) -> str:
    content = item.get("content", [])
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "output_text":
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


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


def _model_to_dict(response: object) -> dict[str, Any]:
    if isinstance(response, dict):
        return cast(dict[str, Any], response)
    dumper = getattr(response, "model_dump", None)
    if callable(dumper):
        result = dumper()
        if isinstance(result, dict):
            return cast(dict[str, Any], result)
    raise TypeError("OpenAI response is not convertible to dict.")


def _string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
