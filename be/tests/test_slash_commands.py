from rich.console import Console

from agent_redteam.cli.slash import (
    SlashCommand,
    SlashCommandContext,
    default_slash_commands,
    handle_slash_command,
)
from agent_redteam.llm.types import AgentMessage


def test_analysis_slash_command_reports_usage_and_history() -> None:
    console = Console(record=True, width=120)
    context = SlashCommandContext(
        console=console,
        history=[
            AgentMessage(role="system", content="system"),
            AgentMessage(role="user", content="hello"),
            AgentMessage(role="assistant", content="done"),
        ],
        usage_events=[
            {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 250},
                "output_tokens": 50,
                "total_tokens": 1050,
            }
        ],
        audit_log_path=".runs/2026-05-29/analytics/run-0001.jsonl",
    )

    handled = handle_slash_command("/analysis", context, default_slash_commands())

    output = console.export_text()
    assert handled is True
    assert "cached_input=250 (25.0%)" in output
    assert "chat history · messages=3, system=1, user=1, assistant=1, tool=0" in output
    assert "audit_log=.runs/2026-05-29/analytics/run-0001.jsonl" in output


def test_unknown_slash_command_is_handled_without_model_dispatch() -> None:
    console = Console(record=True, width=120)
    context = SlashCommandContext(
        console=console,
        history=[],
        usage_events=[],
        audit_log_path=".runs/2026-05-29/analytics/run-0001.jsonl",
    )

    handled = handle_slash_command("/missing", context, default_slash_commands())

    output = console.export_text()
    assert handled is True
    assert "Unknown slash command: /missing" in output
    assert "/analysis" in output


def test_help_slash_command_uses_passed_command_registry() -> None:
    console = Console(record=True, width=120)
    context = SlashCommandContext(
        console=console,
        history=[],
        usage_events=[],
        audit_log_path=".runs/2026-05-29/analytics/run-0001.jsonl",
    )
    commands = {
        "custom": SlashCommand(
            name="custom",
            description="Custom future command.",
            handler=lambda _context, _argument: None,
        )
    }

    handled = handle_slash_command("/help", context, commands)

    output = console.export_text()
    assert handled is True
    assert "/custom - Custom future command." in output
    assert "/analysis" not in output
