import argparse
import asyncio
from collections.abc import Sequence

from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.loop import AgentLoop
from agent_redteam.core.audit import AuditRecorder
from agent_redteam.core.config import AgentProvider, Settings, get_settings
from agent_redteam.guardrails import assert_target_in_scope, require_authorized_engagement
from agent_redteam.llm.claude import ClaudeMessagesHarness
from agent_redteam.llm.openai import OpenAIResponsesHarness
from agent_redteam.llm.types import AgentMessage, ProviderHarness
from agent_redteam.tools.bash import bash, bash_definition
from agent_redteam.tools.registry import ToolRegistry
from agent_redteam.tools.types import ToolCall

SYSTEM_PROMPT = """You are an authorized local operator assistant.
Use tools only for the explicitly requested, in-scope target.
Do not print private keys, raw credentials, tokens, or secrets. Report paths,
fingerprints, configuration facts, and next steps instead."""


def main(argv: Sequence[str] | None = None) -> None:
    settings = get_settings()
    args = _parse_args(argv, settings)

    require_authorized_engagement(settings)
    assert_target_in_scope(args.target, settings)

    provider = _build_provider(settings)
    audit = AuditRecorder(settings.audit_log_path)
    registry = _build_registry(audit)
    context = AgentContext(
        engagement_id=settings.engagement_id,
        target=args.target,
        metadata={
            "operator": settings.engagement_operator,
            "provider": settings.agent_provider,
        },
    )
    audit.record(
        "agent_run_started",
        engagement_id=context.engagement_id,
        target=context.target,
        operator=settings.engagement_operator,
        provider=str(settings.agent_provider),
        model=_provider_model(settings),
    )

    print(f"provider={settings.agent_provider} model={_provider_model(settings)}")
    print(f"engagement_id={settings.engagement_id} target={args.target}")
    print(f"audit_log={settings.audit_log_path}")

    if args.task:
        asyncio.run(_run_task(context, provider, registry, args.task))
        return

    while True:
        task = input("\nagent> ").strip()
        if task in {"exit", "quit", ":q"}:
            return
        if not task:
            continue
        asyncio.run(_run_task(context, provider, registry, task))


async def _run_task(
    context: AgentContext,
    provider: ProviderHarness,
    registry: ToolRegistry,
    task: str,
) -> None:
    loop = AgentLoop(provider=provider, tool_registry=registry)
    result = await loop.run(
        context,
        [
            AgentMessage(role="system", content=SYSTEM_PROMPT),
            AgentMessage(role="user", content=f"Target: {context.target}\nTask: {task}"),
        ],
    )

    if result.success:
        print(result.final_message or "")
        return

    print(f"error: {result.error}")


def _build_registry(audit: AuditRecorder) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(bash_definition(), _audited_bash(audit))
    return registry


def _build_provider(settings: Settings) -> ProviderHarness:
    if settings.agent_provider is AgentProvider.OPENAI:
        api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        return OpenAIResponsesHarness(model=settings.openai_model, api_key=api_key)
    if settings.agent_provider is AgentProvider.CLAUDE:
        api_key = (
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        )
        return ClaudeMessagesHarness(model=settings.anthropic_model, api_key=api_key)

    msg = f"Unsupported provider: {settings.agent_provider}"
    raise ValueError(msg)


def _provider_model(settings: Settings) -> str:
    if settings.agent_provider is AgentProvider.CLAUDE:
        return settings.anthropic_model
    return settings.openai_model


def _audited_bash(audit: AuditRecorder):
    async def run(context: AgentContext, tool_call: ToolCall) -> str:
        command = (tool_call.arguments or {}).get("command")
        audit.record(
            "tool_call_started",
            engagement_id=context.engagement_id,
            target=context.target,
            tool_name=tool_call.name,
            call_id=tool_call.call_id,
            command=command,
        )
        output = await bash(context, tool_call)
        audit.record(
            "tool_call_finished",
            engagement_id=context.engagement_id,
            target=context.target,
            tool_name=tool_call.name,
            call_id=tool_call.call_id,
        )
        return output

    return run


def _parse_args(argv: Sequence[str] | None, settings: Settings) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple authorized ReAct loop.")
    parser.add_argument("task", nargs="?", help="Optional one-shot task. Omit for REPL mode.")
    parser.add_argument("--target", default=settings.agent_target, help="In-scope target.")
    return parser.parse_args(argv)
