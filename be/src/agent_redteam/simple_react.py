import argparse
import asyncio
from collections.abc import Sequence
from importlib.resources import files

from rich.console import Console

from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.events import LoopEvent, LoopObserver, fan_out
from agent_redteam.agents.loop import AgentLoop, AgentLoopResult
from agent_redteam.cli.render import console_observer
from agent_redteam.core.audit import AuditRecorder, audit_observer
from agent_redteam.core.config import AgentProvider, Settings, get_settings
from agent_redteam.guardrails import require_authorized_engagement
from agent_redteam.llm.claude import ClaudeMessagesHarness
from agent_redteam.llm.openai import OpenAIResponsesHarness
from agent_redteam.llm.types import AgentMessage, ProviderHarness
from agent_redteam.tools.bash import bash, bash_definition
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
    context = AgentContext(
        engagement_id=settings.engagement_id,
        metadata={
            "operator": settings.engagement_operator,
            "provider": settings.agent_provider,
        },
    )
    observer = fan_out(
        [
            console_observer(console),
            audit_observer(audit, context.engagement_id),
        ]
    )
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

    history = [AgentMessage(role="system", content=_load_system_prompt())]
    if args.task:
        asyncio.run(_run_task(context, provider, registry, observer, args.task, history))
        return

    while True:
        task = console.input("\n[bold]agent>[/bold] ").strip()
        if task in {"exit", "quit", ":q"}:
            return
        if not task:
            continue
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
        else [AgentMessage(role="system", content=_load_system_prompt())]
    )
    messages.append(AgentMessage(role="user", content=task))
    return await loop.run(
        context,
        messages,
    )


def _load_system_prompt() -> str:
    return (
        files("agent_redteam.prompts")
        .joinpath(SYSTEM_PROMPT_FILE)
        .read_text(encoding="utf-8")
        .strip()
    )


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(bash_definition(), bash)
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
    parser.add_argument("task", nargs="?", help="Optional one-shot task. Omit for REPL mode.")
    return parser.parse_args(argv)
