"""Anthropic Claude Messages API harness.

Follows the official Anthropic Messages API contract:

- ``client.messages.create(model, max_tokens, messages=[...], system=..., tools=[...])``
- ``messages`` alternates ``user``/``assistant``. Assistant messages that
  triggered tools must be replayed verbatim with their ``tool_use`` blocks,
  and the matching ``tool_result`` blocks go inside the next ``user`` message.
- ``system`` is a top-level parameter, not a message.
- Tool specs are strictly ``{name, description, input_schema}``; extra keys
  (e.g. ``metadata``) cause 400s, so internal hints are kept out of the wire
  payload and surfaced only in our own ``provider_metadata``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any, cast

from agent_redteam.llm.types import AgentMessage, ModelEvent, ModelRequest
from agent_redteam.tools.patch import APPLY_PATCH_TOOL_NAME, PATCH_TEXT_SCHEMA
from agent_redteam.tools.types import ToolCall, ToolDefinition, ToolResult

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

DEFAULT_MAX_TOKENS = 4096


class ClaudeMessagesHarness:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: AsyncAnthropic | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self._client = client

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        client = self._resolve_client()
        system, messages = self._build_messages(request.messages)
        tools = self.render_tools(request.tools)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        message = await client.messages.create(**kwargs)
        message_dict = _model_to_dict(message)
        for event in self.normalize_message(message_dict):
            yield event

    def render_tools(self, tools: Sequence[ToolDefinition]) -> list[dict[str, Any]]:
        return [self._render_tool(tool) for tool in tools]

    def format_tool_results(self, results: Sequence[ToolResult]) -> list[AgentMessage]:
        content_blocks = [
            {
                "type": "tool_result",
                "tool_use_id": result.call_id,
                "content": result.output,
                "is_error": not result.success,
            }
            for result in results
        ]
        return [
            AgentMessage(
                role="tool",
                content="\n".join(result.output for result in results),
                provider_metadata={"role": "user", "content": content_blocks},
            )
        ]

    def normalize_message(self, message: dict[str, Any]) -> list[ModelEvent]:
        content = message.get("content", [])
        if not isinstance(content, list):
            return [
                ModelEvent(
                    event_type="error",
                    error="Claude message content must be a list.",
                    provider_metadata=message,
                )
            ]

        events: list[ModelEvent] = []
        text_parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            elif block.get("type") == "tool_use":
                events.append(ModelEvent(event_type="tool_call", tool_call=_tool_use_call(block)))

        if text_parts:
            events.insert(
                0,
                ModelEvent(
                    event_type="message_done",
                    content="".join(text_parts),
                    provider_metadata=message,
                ),
            )

        usage = message.get("usage")
        if isinstance(usage, dict):
            events.append(ModelEvent(event_type="usage", usage=usage))

        events.append(ModelEvent(event_type="completed", provider_metadata=message))
        return events

    def _build_messages(
        self, messages: Sequence[AgentMessage]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        wire_messages: list[dict[str, Any]] = []

        for message in messages:
            if message.role == "system":
                if message.content:
                    system_parts.append(message.content)
                continue

            if message.role == "user":
                _append_user_block(wire_messages, {"type": "text", "text": message.content or ""})
                continue

            if message.role == "assistant":
                blocks: list[dict[str, Any]] = []
                if message.content:
                    blocks.append({"type": "text", "text": message.content})
                for call in message.provider_metadata.get("tool_calls", []):
                    blocks.append(_assistant_tool_use_block(call))
                if blocks:
                    wire_messages.append({"role": "assistant", "content": blocks})
                continue

            if message.role == "tool":
                tool_blocks = message.provider_metadata.get("content")
                if isinstance(tool_blocks, list):
                    for block in tool_blocks:
                        if isinstance(block, dict):
                            _append_user_block(wire_messages, block)

        system = "\n\n".join(part for part in system_parts if part) or None
        return system, wire_messages

    def _render_tool(self, tool: ToolDefinition) -> dict[str, Any]:
        input_schema = tool.input_schema
        if tool.input_mode == "freeform":
            input_schema = _freeform_schema(tool)

        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": input_schema,
        }

    def _resolve_client(self) -> AsyncAnthropic:
        if self._client is not None:
            return self._client
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client


def _append_user_block(messages: list[dict[str, Any]], block: dict[str, Any]) -> None:
    if messages and messages[-1].get("role") == "user":
        existing = messages[-1].get("content")
        if isinstance(existing, list):
            existing.append(block)
            return
    messages.append({"role": "user", "content": [block]})


def _assistant_tool_use_block(call: dict[str, Any]) -> dict[str, Any]:
    provider_metadata = call.get("provider_metadata")
    if isinstance(provider_metadata, dict) and provider_metadata.get("type") == "tool_use":
        return cast(dict[str, Any], provider_metadata)

    return {
        "type": "tool_use",
        "id": call.get("call_id", ""),
        "name": call.get("name", ""),
        "input": call.get("arguments") or {},
    }


def _tool_use_call(block: dict[str, Any]) -> ToolCall:
    arguments = block.get("input", {})
    if not isinstance(arguments, dict):
        arguments = {}
    return ToolCall(
        call_id=str(block["id"]),
        name=str(block["name"]),
        arguments=arguments,
        provider_metadata=block,
    )


def _freeform_schema(tool: ToolDefinition) -> dict[str, Any]:
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


def _model_to_dict(message: object) -> dict[str, Any]:
    if isinstance(message, dict):
        return cast(dict[str, Any], message)
    dumper = getattr(message, "model_dump", None)
    if callable(dumper):
        result = dumper()
        if isinstance(result, dict):
            return cast(dict[str, Any], result)
    raise TypeError("Anthropic message is not convertible to dict.")
