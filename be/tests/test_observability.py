import asyncio
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.events import LoopEvent
from agent_redteam.agents.loop import AgentLoop
from agent_redteam.cli.render import (
    COLLAPSED_PREVIEW_LINES,
    load_audit,
    render_audit,
    render_event,
    usage_summary_from_audit,
)
from agent_redteam.core.audit import AuditRecorder, audit_observer
from agent_redteam.llm.fake import FakeProviderHarness
from agent_redteam.llm.types import AgentMessage, ModelEvent
from agent_redteam.tools.fake import build_test_tool_registry
from agent_redteam.tools.types import ToolCall


def _context() -> AgentContext:
    return AgentContext(engagement_id="engagement-1", metadata={})


def test_loop_emits_observable_events_in_order() -> None:
    provider = FakeProviderHarness(
        [
            [
                ModelEvent(event_type="thinking", content="let me echo"),
                ModelEvent(
                    event_type="tool_call",
                    tool_call=ToolCall(
                        call_id="call_1", name="echo_json", arguments={"value": "ok"}
                    ),
                ),
            ],
            [ModelEvent(event_type="message_done", content="done")],
        ]
    )
    events: list[LoopEvent] = []
    loop = AgentLoop(
        provider=provider,
        tool_registry=build_test_tool_registry(),
        observer=events.append,
    )

    asyncio.run(loop.run(_context(), [AgentMessage(role="user", content="echo")]))

    types = [event.type for event in events]
    assert types == [
        "turn_started",
        "thinking",
        "tool_call",
        "tool_result",
        "turn_started",
        "assistant_message",
        "run_finished",
    ]
    tool_call = next(event for event in events if event.type == "tool_call")
    assert tool_call.tool_name == "echo_json"
    assert tool_call.arguments == {"value": "ok"}
    tool_result = next(event for event in events if event.type == "tool_result")
    assert tool_result.success is True
    assert tool_result.output == '{"value": "ok"}'
    assert events[-1].success is True


def test_audit_observer_round_trips_through_load_audit(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    observe = audit_observer(AuditRecorder(str(path)), "engagement-1")

    observe(LoopEvent(type="thinking", iteration=1, text="planning"))
    observe(
        LoopEvent(
            type="tool_call",
            iteration=1,
            tool_name="exec",
            call_id="call_1",
            arguments={"command": "ls"},
        )
    )

    records = load_audit(path)
    assert [record["event_type"] for record in records] == ["thinking", "tool_call"]
    assert records[0]["engagement_id"] == "engagement-1"
    assert records[1]["arguments"] == {"command": "ls"}
    # Absent optional fields are not persisted as nulls.
    assert "output" not in records[1]


def test_audit_recorder_creates_dated_incrementing_analytics_logs(tmp_path: Path) -> None:
    now = datetime(2026, 5, 29, tzinfo=UTC)
    root = tmp_path / "runs"

    first = AuditRecorder.for_new_run(root, now=now)
    second = AuditRecorder.for_new_run(root, now=now)

    assert first.run_id == 1
    assert first.path == root / "2026-05-29" / "analytics" / "run-0001.jsonl"
    assert second.run_id == 2
    assert second.path == root / "2026-05-29" / "analytics" / "run-0002.jsonl"

    first.record("agent_run_started", engagement_id="engagement-1")
    records = load_audit(first.path)
    assert records[0]["run_id"] == 1


def test_legacy_audit_jsonl_path_allocates_under_parent_directory(tmp_path: Path) -> None:
    legacy_path = tmp_path / "audit.jsonl"

    recorder = AuditRecorder.for_new_run(
        legacy_path,
        now=datetime(2026, 5, 29, tzinfo=UTC),
    )

    assert not legacy_path.exists()
    assert recorder.path == tmp_path / "2026-05-29" / "analytics" / "run-0001.jsonl"


def test_load_audit_from_run_root_uses_latest_incrementing_run(tmp_path: Path) -> None:
    now = datetime(2026, 5, 29, tzinfo=UTC)
    root = tmp_path / "runs"
    first = AuditRecorder.for_new_run(root, now=now)
    first.record("thinking", text="first")
    second = AuditRecorder.for_new_run(root, now=now)
    second.record("thinking", text="second")

    records = load_audit(root)

    assert [record["text"] for record in records] == ["second"]


def test_usage_summary_from_audit_counts_cache_hits() -> None:
    records = [
        {
            "event_type": "usage",
            "usage": {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 250},
                "output_tokens": 50,
                "total_tokens": 1050,
            },
        },
        {
            "event_type": "usage",
            "usage": {
                "input_tokens": 200,
                "input_tokens_details": {"cached_tokens": 50},
                "output_tokens": 25,
                "total_tokens": 225,
            },
        },
    ]

    summary = usage_summary_from_audit(records)

    assert summary.requests == 2
    assert summary.input_tokens == 1200
    assert summary.cached_input_tokens == 300
    assert summary.cache_hit_rate == 0.25


def test_render_audit_pretty_prints_recorded_run() -> None:
    records = [
        {"event_type": "thinking", "text": "I will list the directory"},
        {
            "event_type": "tool_call",
            "tool_name": "bash",
            "arguments": {"host": "operator", "command": "ls ~"},
        },
        {"event_type": "tool_result", "success": True, "output": "report.txt"},
        {
            "event_type": "usage",
            "usage": {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 250},
                "output_tokens": 50,
                "total_tokens": 1050,
            },
        },
        {"event_type": "assistant_message", "text": "Here is the file."},
        {"event_type": "run_finished", "success": True},
    ]
    console = Console(record=True, width=100)

    render_audit(records, console)

    output = console.export_text()
    assert "thinking" in output
    assert "bash" in output
    assert "command: ls ~" in output
    assert "report.txt" in output
    assert "cached_input=250" in output
    assert "(25.0%)" in output
    assert "Here is the file." in output


def test_live_view_collapses_long_blocks_but_replay_shows_all() -> None:
    lines = [f"line {n}" for n in range(COLLAPSED_PREVIEW_LINES + 5)]
    fields = {"success": True, "output": "\n".join(lines)}

    live = Console(record=True, width=100)
    render_event(live, "tool_result", fields, collapse=True)
    live_text = live.export_text()
    assert "more lines" in live_text
    assert "ctrl+o" in live_text
    assert lines[-1] not in live_text

    full = Console(record=True, width=100)
    render_event(full, "tool_result", fields, collapse=False)
    full_text = full.export_text()
    assert "more lines" not in full_text
    assert lines[-1] in full_text
