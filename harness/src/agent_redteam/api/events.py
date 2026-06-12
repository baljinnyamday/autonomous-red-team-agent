"""Translate the agent's ``LoopEvent`` stream into dashboard ``agent.step`` events.

This is the "latest news" channel: every model turn and tool call becomes one
human-readable activity line. Topology deltas come from the differ, not here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from agent_redteam.agents.events import LoopEvent, LoopObserver
from agent_redteam.api.status_hub import StatusHub

_ROLE = "executor"
_MAX_ACTION = 160


def status_observer(hub: StatusHub) -> LoopObserver:
    def observe(event: LoopEvent) -> None:
        action = _action_for(event)
        if action is None:
            return
        hub.publish(
            {
                "type": "agent.step",
                "role": _ROLE,
                "action": action,
                "at": datetime.now(UTC).isoformat(),
            }
        )

    return observe


def _action_for(event: LoopEvent) -> str | None:
    if event.type in {"run_started", "assistant_message", "thinking"}:
        return _truncate(event.text)
    if event.type == "tool_call":
        return _tool_action(event.tool_name, event.arguments)
    return None


def _tool_action(tool_name: str | None, arguments: dict[str, Any] | None) -> str | None:
    if not tool_name:
        return None
    args = arguments or {}
    host = args.get("host")
    detail = args.get("command") or args.get("query") or args.get("objective") or args.get("path")
    label = f"{tool_name} on {host}" if host else tool_name
    return _truncate(f"{label}: {detail}" if detail else label)


def _truncate(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= _MAX_ACTION else cleaned[: _MAX_ACTION - 1] + "…"
