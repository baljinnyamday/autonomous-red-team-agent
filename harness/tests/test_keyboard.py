from rich.console import Console

from agent_redteam.cli.expand import ExpandableHistory
from agent_redteam.cli.keyboard import (
    KeyboardEvent,
    KeyboardEventDispatcher,
    dispatch_keypress,
)
from agent_redteam.cli.shortcuts import (
    EXAMPLE_EVENT,
    PROMPT_KEY_EVENTS,
    TERMINAL_KEY_EVENTS,
    TOGGLE_HISTORY_EVENT,
    default_keyboard_handlers,
)


def test_keyboard_dispatcher_calls_registered_event_handler() -> None:
    events: list[str] = []
    dispatcher = KeyboardEventDispatcher({TOGGLE_HISTORY_EVENT: lambda: events.append("expanded")})

    handled = dispatcher.dispatch(KeyboardEvent(TOGGLE_HISTORY_EVENT))

    assert handled is True
    assert events == ["expanded"]


def test_keyboard_dispatcher_ignores_unregistered_events() -> None:
    events: list[str] = []
    dispatcher = KeyboardEventDispatcher({TOGGLE_HISTORY_EVENT: lambda: events.append("expanded")})

    handled = dispatcher.dispatch(KeyboardEvent("missing"))

    assert handled is False
    assert events == []


def test_dispatch_keypress_maps_terminal_key_to_event() -> None:
    events: list[str] = []
    dispatcher = KeyboardEventDispatcher({TOGGLE_HISTORY_EVENT: lambda: events.append("expanded")})

    handled = dispatch_keypress(b"\x0f", dispatcher, TERMINAL_KEY_EVENTS)

    assert handled is True
    assert events == ["expanded"]


def test_dispatch_keypress_ignores_unknown_terminal_keys() -> None:
    events: list[str] = []
    dispatcher = KeyboardEventDispatcher({TOGGLE_HISTORY_EVENT: lambda: events.append("expanded")})

    handled = dispatch_keypress(b"x", dispatcher, TERMINAL_KEY_EVENTS)

    assert handled is False
    assert events == []


def test_shortcut_maps_include_ctrl_o_and_ctrl_b() -> None:
    assert TERMINAL_KEY_EVENTS[b"\x0f"] == TOGGLE_HISTORY_EVENT
    assert TERMINAL_KEY_EVENTS[b"\x02"] == EXAMPLE_EVENT
    assert PROMPT_KEY_EVENTS["c-o"] == TOGGLE_HISTORY_EVENT
    assert PROMPT_KEY_EVENTS["c-b"] == EXAMPLE_EVENT


def test_default_ctrl_b_handler_prints_example_message() -> None:
    console = Console(record=True)
    handlers = default_keyboard_handlers(ExpandableHistory(console), console)

    handlers[EXAMPLE_EVENT]()

    assert "this is example function" in console.export_text()
