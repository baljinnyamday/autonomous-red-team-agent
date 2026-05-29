from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from agent_redteam.llm.types import AgentMessage
from agent_redteam.llm.usage import (
    estimate_usage_cost,
    format_cost_estimate,
    format_usage_summary,
    summarize_usage,
    summarize_usage_by_model,
)

SlashHandler = Callable[["SlashCommandContext", str], None]


@dataclass(frozen=True)
class SlashCommand:
    name: str
    description: str
    handler: SlashHandler


@dataclass(frozen=True)
class SlashCommandContext:
    console: Console
    history: Sequence[AgentMessage]
    usage_events: Sequence[dict[str, Any]]
    audit_log_path: str
    provider: str | None = None
    model: str | None = None
    session_started_at: datetime | None = None


def default_slash_commands() -> dict[str, SlashCommand]:
    commands = [
        SlashCommand(
            name="analysis",
            description="Show token usage, cache hit rate, and chat-history state.",
            handler=_analysis,
        ),
        SlashCommand(
            name="help",
            description="Show available slash commands.",
            handler=_help,
        ),
    ]
    return {command.name: command for command in commands}


def handle_slash_command(
    raw_input: str,
    context: SlashCommandContext,
    commands: Mapping[str, SlashCommand],
) -> bool:
    if not raw_input.startswith("/"):
        return False

    name, argument = _parse_slash_command(raw_input)
    if name in {"", "help"}:
        _print_available_commands(context.console, commands)
        return True

    command = commands.get(name)
    if command is None:
        context.console.print(f"[yellow]Unknown slash command: /{name}[/yellow]")
        _print_available_commands(context.console, commands)
        return True

    command.handler(context, argument)
    return True


def _parse_slash_command(raw_input: str) -> tuple[str, str]:
    command = raw_input[1:].strip()
    if not command:
        return "", ""
    name, _, argument = command.partition(" ")
    return name.lower(), argument.strip()


def _analysis(context: SlashCommandContext, _argument: str) -> None:
    summary = summarize_usage(context.usage_events)
    if summary.requests:
        context.console.print(f"[dim]session usage · {format_usage_summary(summary)}[/dim]")
    else:
        context.console.print("[dim]session usage · no usage events yet[/dim]")

    _print_model_usage(context)
    _print_session_timing(context)
    _print_audit_analysis(context)

    role_counts = Counter(message.role for message in context.history)
    history_parts = [
        f"messages={len(context.history)}",
        f"system={role_counts['system']}",
        f"user={role_counts['user']}",
        f"assistant={role_counts['assistant']}",
        f"tool={role_counts['tool']}",
    ]
    context.console.print(f"[dim]chat history · {', '.join(history_parts)}[/dim]")
    context.console.print(f"[dim]audit_log={context.audit_log_path}[/dim]")


def _print_model_usage(context: SlashCommandContext) -> None:
    if not context.usage_events:
        return

    by_model = summarize_usage_by_model(
        context.usage_events,
        default_provider=context.provider,
        default_model=context.model,
    )
    for group, summary in sorted(by_model.items()):
        parts = [f"{group.provider}/{group.model}", format_usage_summary(summary)]
        estimate = estimate_usage_cost(summary, provider=group.provider, model=group.model)
        if estimate is not None:
            parts.append(format_cost_estimate(estimate))
        else:
            parts.append("cost=unknown")
        context.console.print(f"[dim]model usage · {' · '.join(parts)}[/dim]")


def _print_session_timing(context: SlashCommandContext) -> None:
    started_at = context.session_started_at
    if started_at is None:
        return

    now = datetime.now(UTC)
    elapsed = max((now - started_at).total_seconds(), 0)
    context.console.print(
        "[dim]session timing · "
        f"started={_format_timestamp(started_at)}, "
        f"now={_format_timestamp(now)}, "
        f"elapsed={_format_duration(elapsed)}[/dim]"
    )


def _print_audit_analysis(context: SlashCommandContext) -> None:
    records = _load_current_session_audit_records(context.audit_log_path)
    if not records:
        return

    event_counts = Counter(str(record.get("event_type", "unknown")) for record in records)
    tool_calls = Counter(
        str(record["tool_name"])
        for record in records
        if record.get("event_type") == "tool_call" and record.get("tool_name")
    )
    tool_result_count = event_counts["tool_result"]
    tool_successes = sum(
        1
        for record in records
        if record.get("event_type") == "tool_result" and record.get("success") is True
    )
    tool_errors = tool_result_count - tool_successes
    run_finished = [record for record in records if record.get("event_type") == "run_finished"]
    failed_runs = sum(1 for record in run_finished if record.get("success") is False)

    audit_parts = [
        f"events={len(records)}",
        f"tasks={event_counts['run_started']}",
        f"model_turns={event_counts['turn_started']}",
        f"tool_calls={event_counts['tool_call']}",
        f"tool_results={tool_result_count}",
        f"tool_success={tool_successes}",
        f"tool_errors={tool_errors}",
        f"completed_runs={len(run_finished) - failed_runs}",
        f"failed_runs={failed_runs}",
    ]
    context.console.print(f"[dim]audit events · {', '.join(audit_parts)}[/dim]")

    if tool_calls:
        tools = ", ".join(f"{name}={count}" for name, count in sorted(tool_calls.items()))
        context.console.print(f"[dim]tools · {tools}[/dim]")

    first_timestamp = _record_timestamp(records[0])
    last_timestamp = _record_timestamp(records[-1])
    if first_timestamp is not None and last_timestamp is not None:
        covered = max((last_timestamp - first_timestamp).total_seconds(), 0)
        context.console.print(
            "[dim]audit timing · "
            f"first={_format_timestamp(first_timestamp)}, "
            f"last={_format_timestamp(last_timestamp)}, "
            f"covered={_format_duration(covered)}[/dim]"
        )


def _help(context: SlashCommandContext, _argument: str) -> None:
    _print_available_commands(context.console, default_slash_commands())


def _print_available_commands(
    console: Console,
    commands: Mapping[str, SlashCommand],
) -> None:
    for command in sorted(commands.values(), key=lambda item: item.name):
        console.print(f"[dim]/{command.name}[/dim] - {command.description}")


def _load_current_session_audit_records(path: str) -> list[dict[str, Any]]:
    audit_path = Path(path)
    if not audit_path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)

    start_indexes = [
        index
        for index, record in enumerate(records)
        if record.get("event_type") == "agent_run_started"
    ]
    if not start_indexes:
        return records
    return records[start_indexes[-1] :]


def _record_timestamp(record: Mapping[str, Any]) -> datetime | None:
    timestamp = record.get("timestamp")
    if not isinstance(timestamp, str):
        return None
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _format_duration(seconds: float) -> str:
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"
