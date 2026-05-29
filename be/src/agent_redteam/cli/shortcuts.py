"""Default keyboard shortcut mappings for the interactive CLI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from rich.console import Console

from agent_redteam.cli.expand import ExpandableHistory
from agent_redteam.cli.keyboard import KeyboardHandler

TOGGLE_HISTORY_EVENT = "toggle_history"
EXAMPLE_EVENT = "example"


@dataclass(frozen=True)
class KeyboardShortcut:
    event_name: str
    terminal_key: bytes
    prompt_key: str
    label: str


SHORTCUTS = (
    KeyboardShortcut(
        event_name=TOGGLE_HISTORY_EVENT,
        terminal_key=b"\x0f",
        prompt_key="c-o",
        label="ctrl+o toggles expanded history",
    ),
    KeyboardShortcut(
        event_name=EXAMPLE_EVENT,
        terminal_key=b"\x02",
        prompt_key="c-b",
        label="ctrl+b prints an example message",
    ),
)

TERMINAL_KEY_EVENTS: Mapping[bytes, str] = {
    shortcut.terminal_key: shortcut.event_name for shortcut in SHORTCUTS
}
PROMPT_KEY_EVENTS: Mapping[str, str] = {
    shortcut.prompt_key: shortcut.event_name for shortcut in SHORTCUTS
}


def default_keyboard_handlers(
    history_view: ExpandableHistory,
    console: Console,
) -> dict[str, KeyboardHandler]:
    return {
        TOGGLE_HISTORY_EVENT: history_view.toggle,
        EXAMPLE_EVENT: lambda: console.print("[dim]this is example function[/dim]"),
    }
