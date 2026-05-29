from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from rich.console import Console

from agent_redteam.llm.types import AgentMessage
from agent_redteam.llm.usage import format_usage_summary, summarize_usage

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


def _help(context: SlashCommandContext, _argument: str) -> None:
    _print_available_commands(context.console, default_slash_commands())


def _print_available_commands(
    console: Console,
    commands: Mapping[str, SlashCommand],
) -> None:
    for command in sorted(commands.values(), key=lambda item: item.name):
        console.print(f"[dim]/{command.name}[/dim] - {command.description}")
