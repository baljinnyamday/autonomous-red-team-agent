"""Pretty terminal rendering for agent runs.

The same formatters drive two surfaces:

- a live :data:`LoopObserver` that prints each step as it happens, with long
  blocks collapsed to a short preview, and
- the ``replay`` command, which re-renders a raw audit log in full.

Each block is a labeled, color-bordered panel so thinking, tool calls, tool
results and assistant messages are easy to tell apart at a glance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from agent_redteam.agents.events import LoopEvent, LoopObserver
from agent_redteam.core.audit import latest_audit_log_path
from agent_redteam.llm.usage import UsageSummary, format_usage_summary, summarize_usage

# Live view collapses any block taller than this to a preview; replay shows all.
COLLAPSED_PREVIEW_LINES = 6
# Hard ceiling so a single enormous line cannot flood the terminal in any view.
MAX_BLOCK_CHARS = 8000

_EXPAND_HINT = "ctrl+o to expand"


def console_observer(console: Console | None = None) -> LoopObserver:
    """A loop observer that prints each event live, collapsing long blocks.

    Per-turn usage is accumulated silently and reported once when the agent
    hands control back, instead of after every model turn.
    """
    target = console or Console()
    usages: list[dict[str, Any]] = []

    def observe(event: LoopEvent) -> None:
        if event.type == "usage":
            usages.append(event.usage)
            return
        render_event(target, event.type, event_fields(event), collapse=True)
        if event.type == "run_finished":
            print_usage_summary(target, summarize_usage(usages))
            usages.clear()

    return observe


def render_audit(records: list[dict[str, Any]], console: Console | None = None) -> None:
    """Render a recorded run in full (nothing collapsed)."""
    target = console or Console()
    usages: list[dict[str, Any]] = []
    for record in records:
        event_type = str(record.get("event_type", ""))
        if event_type == "usage":
            usage = record.get("usage")
            if isinstance(usage, dict):
                usages.append(usage)
            continue
        render_event(target, event_type, record, collapse=False)
    print_usage_summary(target, summarize_usage(usages))


def usage_summary_from_audit(records: list[dict[str, Any]]) -> UsageSummary:
    return summarize_usage(
        record["usage"]
        for record in records
        if record.get("event_type") == "usage" and isinstance(record.get("usage"), dict)
    )


def print_usage_summary(console: Console, summary: UsageSummary) -> None:
    if summary.requests == 0:
        return
    console.print(f"[dim]session usage · {format_usage_summary(summary)}[/dim]")


def load_audit(path: str | Path) -> list[dict[str, Any]]:
    text = latest_audit_log_path(path).read_text(encoding="utf-8")
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            records.append(json.loads(stripped))
    return records


def render_event(
    console: Console,
    event_type: str,
    fields: dict[str, Any],
    *,
    collapse: bool,
) -> None:
    if event_type == "agent_run_started":
        provider = fields.get("provider", "?")
        model = fields.get("model", "?")
        console.rule(f"[bold]engagement {fields.get('engagement_id', '?')}[/bold]")
        console.print(f"[dim]{provider} · {model}[/dim]")
    elif event_type == "run_finished":
        if fields.get("success"):
            console.rule("[bold green]✓ done[/bold green]")
        else:
            console.rule("[bold red]✗ failed[/bold red]")
            console.print(f"[red]{_text(fields) or fields.get('error', 'failed')}[/red]")
        return

    block = block_content(event_type, fields)
    if block is not None:
        title, style, body = block
        console.print(_block(title, style, body, collapse))


def block_content(event_type: str, fields: dict[str, Any]) -> tuple[str, str, str] | None:
    """Return ``(title, border_style, body)`` for a block event, else ``None``.

    Single source of truth for block labels/styles so the live Rich stream and
    the interactive TUI render the same thing.
    """
    if event_type == "run_started":
        return ("📋 task", "yellow", _text(fields))
    if event_type == "thinking":
        return ("💭 thinking", "magenta", _text(fields))
    if event_type == "tool_call":
        name = fields.get("tool_name") or "tool"
        return (f"🔧 {name}", "cyan", _tool_call_body(fields))
    if event_type == "tool_result":
        ok = bool(fields.get("success"))
        title = "📤 result · ok" if ok else "📤 result · error"
        return (title, "green" if ok else "red", _result_body(fields))
    if event_type == "assistant_message":
        return ("💬 assistant", "green", _text(fields))
    return None


def _block(title: str, style: str, body: str, collapse: bool) -> Panel:
    preview, hidden = _collapse(body, collapse)
    renderables: list[RenderableType] = [Text(preview or "(empty)")]
    if hidden:
        renderables.append(Text(f"… +{hidden} more lines · {_EXPAND_HINT}", style="dim italic"))
    return Panel(
        Group(*renderables),
        title=title,
        title_align="left",
        border_style=style,
        padding=(0, 1),
    )


def _collapse(text: str, collapse: bool) -> tuple[str, int]:
    """Return a body preview and the number of hidden lines."""
    body = text if len(text) <= MAX_BLOCK_CHARS else text[:MAX_BLOCK_CHARS] + " …"
    lines = body.splitlines() or [""]
    if not collapse or len(lines) <= COLLAPSED_PREVIEW_LINES:
        return body, 0
    return "\n".join(lines[:COLLAPSED_PREVIEW_LINES]), len(lines) - COLLAPSED_PREVIEW_LINES


def _tool_call_body(fields: dict[str, Any]) -> str:
    freeform = fields.get("freeform_input")
    if freeform:
        return str(freeform)
    arguments = fields.get("arguments")
    if not isinstance(arguments, dict) or not arguments:
        return "(no arguments)"
    return "\n".join(f"{key}: {_value_repr(value)}" for key, value in arguments.items())


def _result_body(fields: dict[str, Any]) -> str:
    output = str(fields.get("output", ""))
    error = fields.get("error")
    if error and not fields.get("success"):
        return f"[{error}] {output}" if output else str(error)
    return output


def _value_repr(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _text(fields: dict[str, Any]) -> str:
    text = fields.get("text")
    return text if isinstance(text, str) else ""


def event_fields(event: LoopEvent) -> dict[str, Any]:
    return {
        "iteration": event.iteration,
        "text": event.text,
        "tool_name": event.tool_name,
        "call_id": event.call_id,
        "arguments": event.arguments,
        "freeform_input": event.freeform_input,
        "success": event.success,
        "output": event.output,
        "error": event.error,
        "usage": event.usage,
    }
