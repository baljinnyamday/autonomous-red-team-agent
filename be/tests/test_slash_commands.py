import json
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from agent_redteam.cli.slash import (
    SlashCommand,
    SlashCommandContext,
    default_slash_commands,
    handle_slash_command,
)
from agent_redteam.llm.types import AgentMessage


def test_analysis_slash_command_reports_usage_history_cost_and_audit(tmp_path: Path) -> None:
    console = Console(record=True, width=240)
    audit_log_path = tmp_path / "audit.jsonl"
    audit_records = [
        {
            "timestamp": "2026-05-29T12:00:00+00:00",
            "event_type": "agent_run_started",
            "engagement_id": "eng-1",
            "provider": "openai",
            "model": "gpt-5.5",
        },
        {
            "timestamp": "2026-05-29T12:00:01+00:00",
            "event_type": "run_started",
            "text": "hello",
        },
        {"timestamp": "2026-05-29T12:00:02+00:00", "event_type": "turn_started"},
        {
            "timestamp": "2026-05-29T12:00:02+00:00",
            "event_type": "tool_call",
            "tool_name": "bash",
        },
        {
            "timestamp": "2026-05-29T12:00:03+00:00",
            "event_type": "tool_result",
            "tool_name": "bash",
            "success": True,
        },
        {
            "timestamp": "2026-05-29T12:00:03+00:00",
            "event_type": "run_finished",
            "success": True,
        },
    ]
    audit_log_path.write_text(
        "\n".join(json.dumps(record) for record in audit_records),
        encoding="utf-8",
    )
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
                "provider": "openai",
                "model": "gpt-5.5",
            }
        ],
        audit_log_path=str(audit_log_path),
        provider="openai",
        model="gpt-5.5",
        session_started_at=datetime(2026, 5, 29, 12, 0, tzinfo=UTC),
    )

    handled = handle_slash_command("/analysis", context, default_slash_commands())

    output = console.export_text()
    assert handled is True
    assert "cached_input=250 (25.0%)" in output
    assert "model usage · openai/gpt-5.5" in output
    assert "cost≈" in output
    assert "session timing · started=2026-05-29T12:00:00+00:00" in output
    assert (
        "audit events · events=6, tasks=1, model_turns=1, tool_calls=1, tool_results=1, "
        "tool_success=1, tool_errors=0, completed_runs=1, failed_runs=0"
    ) in output
    assert "tools · bash=1" in output
    assert "audit timing · first=2026-05-29T12:00:00+00:00" in output
    assert "chat history · messages=3, system=1, user=1, assistant=1, tool=0" in output
    assert f"audit_log={audit_log_path}" in output


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
