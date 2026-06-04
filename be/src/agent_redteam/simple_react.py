import argparse
import asyncio
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from rich.console import Console

from agent_redteam.agents.autonomous import (
    AutonomousResult,
    parse_duration,
    run_autonomous,
)
from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.events import LoopEvent, LoopObserver, fan_out
from agent_redteam.agents.loop import AgentLoop, AgentLoopResult
from agent_redteam.cli.expand import ExpandableHistory
from agent_redteam.cli.keyboard import listen_for_keyboard_events
from agent_redteam.cli.live_input import live_slash_observer, start_slash_input_thread
from agent_redteam.cli.prompt import TaskReader
from agent_redteam.cli.render import console_observer
from agent_redteam.cli.shortcuts import (
    PROMPT_KEY_EVENTS,
    TERMINAL_KEY_EVENTS,
    default_keyboard_handlers,
)
from agent_redteam.cli.slash import (
    SlashCommand,
    SlashCommandContext,
    default_slash_commands,
    handle_slash_command,
)
from agent_redteam.core.audit import AuditRecorder, audit_observer
from agent_redteam.core.config import AgentProvider, Settings, get_settings
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.guardrails import require_authorized_engagement
from agent_redteam.llm.claude import ClaudeMessagesHarness
from agent_redteam.llm.openai import OpenAIResponsesHarness
from agent_redteam.llm.types import AgentMessage, ProviderHarness
from agent_redteam.targets.state import EngagementState, default_state_path, load_engagement_state
from agent_redteam.tools.exec import exec_definition, exec_tool
from agent_redteam.tools.finish import finish, finish_definition
from agent_redteam.tools.registry import ToolRegistry

SYSTEM_PROMPT_FILE = "system.md"


def main(argv: Sequence[str] | None = None) -> None:
    settings = get_settings()
    args = _parse_args(argv)

    require_authorized_engagement(settings)

    console = Console()
    provider = _build_provider(settings)
    audit = AuditRecorder(settings.audit_log_path)
    registry = _build_registry()
    usage_events: list[dict[str, Any]] = []
    session_started_at = datetime.now(UTC)
    engagement_state = load_engagement_state(settings)
    state_path = default_state_path(settings)
    system_prompt_base = _load_base_system_prompt()
    context = AgentContext(
        engagement_id=settings.engagement_id,
        metadata={
            "operator": settings.engagement_operator,
            "provider": settings.agent_provider,
            "settings": settings,
            "engagement_state": engagement_state,
            "engagement_state_path": str(state_path),
            "system_prompt_base": system_prompt_base,
        },
    )
    history_view = ExpandableHistory(console)
    observers: list[LoopObserver] = [
        console_observer(console),
        audit_observer(audit, context.engagement_id),
        _usage_observer(usage_events),
        history_view.observer(),
    ]
    audit.record(
        "agent_run_started",
        engagement_id=context.engagement_id,
        operator=settings.engagement_operator,
        provider=str(settings.agent_provider),
        model=_provider_model(settings),
    )

    model = _provider_model(settings)
    console.print(f"[dim]provider={settings.agent_provider} model={model}[/dim]")
    console.print(f"[dim]engagement_id={settings.engagement_id}[/dim]")
    console.print(f"[dim]audit_log={settings.audit_log_path}[/dim]")

    history = [
        AgentMessage(
            role="system",
            content=_system_prompt_with_topology(system_prompt_base, engagement_state),
        )
    ]
    slash_commands = default_slash_commands()

    if args.autonomous:
        _run_autonomous_mode(
            args=args,
            settings=settings,
            console=console,
            provider=provider,
            registry=registry,
            context=context,
            observers=observers,
            usage_events=usage_events,
            session_started_at=session_started_at,
            history=history,
            slash_commands=slash_commands,
            audit=audit,
        )
        return

    console.print("[dim]ctrl+o toggles the expanded history · ↑↓ history · tab completes /[/dim]")
    observer = fan_out(observers)
    keyboard_handlers = default_keyboard_handlers(history_view, console)
    reader = TaskReader(
        Path(settings.audit_log_path).parent / "repl-history",
        slash_commands.keys(),
        keyboard_handlers,
        PROMPT_KEY_EVENTS,
    )
    if args.task:
        if handle_slash_command(
            args.task,
            _slash_context(
                console=console,
                history=history,
                usage_events=usage_events,
                settings=settings,
                session_started_at=session_started_at,
            ),
            slash_commands,
        ):
            return
        with listen_for_keyboard_events(keyboard_handlers, TERMINAL_KEY_EVENTS):
            result = asyncio.run(
                _run_task(context, provider, registry, observer, args.task, history)
            )
        history = list(result.messages)

    while True:
        try:
            task = reader.read().strip()
        except EOFError:
            return
        except KeyboardInterrupt:
            continue
        if task in {"exit", "quit", ":q"}:
            return
        if not task:
            continue
        if handle_slash_command(
            task,
            _slash_context(
                console=console,
                history=history,
                usage_events=usage_events,
                settings=settings,
                session_started_at=session_started_at,
            ),
            slash_commands,
        ):
            continue
        with listen_for_keyboard_events(keyboard_handlers, TERMINAL_KEY_EVENTS):
            result = asyncio.run(_run_task(context, provider, registry, observer, task, history))
        history = list(result.messages)


async def _run_task(
    context: AgentContext,
    provider: ProviderHarness,
    registry: ToolRegistry,
    observer: LoopObserver,
    task: str,
    history: Sequence[AgentMessage] | None = None,
) -> AgentLoopResult:
    observer(LoopEvent(type="run_started", text=task))
    loop = AgentLoop(provider=provider, tool_registry=registry, observer=observer)
    messages = (
        list(history)
        if history is not None
        else [
            AgentMessage(
                role="system",
                content=_system_prompt_with_topology(
                    context.metadata["system_prompt_base"],
                    context.metadata["engagement_state"],
                ),
            )
        ]
    )
    messages.append(AgentMessage(role="user", content=task))
    return await loop.run(
        context,
        messages,
    )


def _run_autonomous_mode(
    *,
    args: argparse.Namespace,
    settings: Settings,
    console: Console,
    provider: ProviderHarness,
    registry: ToolRegistry,
    context: AgentContext,
    observers: list[LoopObserver],
    usage_events: list[dict[str, Any]],
    session_started_at: datetime,
    history: Sequence[AgentMessage],
    slash_commands: dict[str, SlashCommand],
    audit: AuditRecorder,
) -> None:
    objective = args.task
    if not objective:
        raise ConfigurationError("--autonomous requires a task/objective argument.")
    budget_seconds = parse_duration(args.duration)

    # Shared conversation buffer: run_autonomous updates it in place so the live
    # slash observer can read the current history mid-run.
    messages = list(history)

    def make_context() -> SlashCommandContext:
        return _slash_context(
            console=console,
            history=messages,
            usage_events=usage_events,
            settings=settings,
            session_started_at=session_started_at,
        )

    commands = start_slash_input_thread()
    observer = fan_out([*observers, live_slash_observer(commands, make_context, slash_commands)])

    audit.record(
        "autonomous_run_started",
        engagement_id=context.engagement_id,
        objective=objective,
        duration_seconds=budget_seconds,
    )
    console.print(
        f"[dim]autonomous mode · duration={args.duration} · type /command to inspect[/dim]"
    )

    deadline = time.monotonic() + budget_seconds
    outcome = asyncio.run(
        run_autonomous(
            context=context,
            provider=provider,
            registry=registry,
            observer=observer,
            objective=objective,
            messages=messages,
            deadline=deadline,
            before_cycle=_refresh_topology_system_message,
        )
    )
    audit.record(
        "autonomous_run_finished",
        engagement_id=context.engagement_id,
        stop_reason=outcome.stop_reason,
        cycles=outcome.cycles,
    )
    _print_autonomous_summary(console, outcome)


def _print_autonomous_summary(console: Console, outcome: AutonomousResult) -> None:
    reasons = {
        "finished": "objective marked complete",
        "duration": "duration budget reached",
        "error": outcome.result.error or "inner loop error",
    }
    summary = f"{outcome.cycles} cycles · {reasons[outcome.stop_reason]}"
    console.print(f"[dim]autonomous run ended · {summary}[/dim]")


def _usage_observer(usage_events: list[dict[str, Any]]) -> LoopObserver:
    def observe(event: LoopEvent) -> None:
        if event.type == "usage":
            usage_events.append(event.usage)

    return observe


def _slash_context(
    *,
    console: Console,
    history: Sequence[AgentMessage],
    usage_events: Sequence[dict[str, Any]],
    settings: Settings,
    session_started_at: datetime,
) -> SlashCommandContext:
    return SlashCommandContext(
        console=console,
        history=history,
        usage_events=usage_events,
        audit_log_path=settings.audit_log_path,
        provider=str(settings.agent_provider),
        model=_provider_model(settings),
        session_started_at=session_started_at,
    )


def _load_base_system_prompt() -> str:
    return (
        files("agent_redteam.prompts")
        .joinpath(SYSTEM_PROMPT_FILE)
        .read_text(encoding="utf-8")
        .strip()
    )


def _system_prompt_with_topology(base: str, state: EngagementState) -> str:
    return f"{base}\n\n## Current topology\n\n{state.topology_prompt_block()}"


def _refresh_topology_system_message(
    messages: list[AgentMessage],
    context: AgentContext,
) -> None:
    base = context.metadata["system_prompt_base"]
    state = context.metadata["engagement_state"]
    if not isinstance(state, EngagementState):
        return
    content = _system_prompt_with_topology(base, state)
    for index, message in enumerate(messages):
        if message.role == "system":
            messages[index] = AgentMessage(
                role="system",
                content=content,
                provider_metadata=message.provider_metadata,
            )
            return


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(exec_definition(), exec_tool)
    registry.register(finish_definition(), finish)
    return registry


def _build_provider(settings: Settings) -> ProviderHarness:
    if settings.agent_provider is AgentProvider.OPENAI:
        return OpenAIResponsesHarness(
            model=settings.openai_model,
            api_key=settings.require_openai_api_key(),
            prompt_cache_key=settings.openai_prompt_cache_key or settings.engagement_id,
        )
    if settings.agent_provider is AgentProvider.CLAUDE:
        return ClaudeMessagesHarness(
            model=settings.anthropic_model,
            api_key=settings.require_anthropic_api_key(),
        )

    msg = f"Unsupported provider: {settings.agent_provider}"
    raise ValueError(msg)


def _provider_model(settings: Settings) -> str:
    if settings.agent_provider is AgentProvider.CLAUDE:
        return settings.anthropic_model
    return settings.openai_model


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple authorized ReAct loop.")
    parser.add_argument("task", nargs="?", help="Optional starting task.")
    parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Run unattended until the agent calls finish or the duration elapses.",
    )
    parser.add_argument(
        "--duration",
        default="30m",
        help="Wall-clock budget for autonomous mode (e.g. 30m, 45s, 1h). Default 30m.",
    )
    return parser.parse_args(argv)
