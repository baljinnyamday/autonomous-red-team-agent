from rich.console import Console

from agent_redteam.agents.events import LoopEvent
from agent_redteam.cli.expand import ExpandableHistory


def _record_long_run(history: ExpandableHistory) -> list[str]:
    record = history.observer()
    lines = [f"line {n}" for n in range(20)]
    record(LoopEvent(type="run_started", text="grab the file"))
    record(LoopEvent(type="tool_call", tool_name="bash", arguments={"command": "ls ~"}))
    record(LoopEvent(type="tool_result", success=True, output="\n".join(lines)))
    return lines


def test_first_toggle_reprints_full_history_uncollapsed() -> None:
    console = Console(record=True, width=100)
    history = ExpandableHistory(console)
    lines = _record_long_run(history)

    history.toggle()
    output = console.export_text()

    assert "expanded history" in output
    assert "command: ls ~" in output
    assert lines[-1] in output
    assert "more lines" not in output


def test_second_toggle_recollapses_history() -> None:
    console = Console(record=True, width=100)
    history = ExpandableHistory(console)
    lines = _record_long_run(history)

    history.toggle()  # expand
    console.export_text()  # drain
    history.toggle()  # collapse again
    output = console.export_text()

    assert "collapsed history" in output
    assert "more lines" in output
    assert lines[-1] not in output


def test_toggle_is_noop_without_events() -> None:
    console = Console(record=True, width=100)
    ExpandableHistory(console).toggle()
    assert console.export_text().strip() == ""
