"""Keyboard event dispatch for interactive terminal shortcuts."""

from __future__ import annotations

import os
import select
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

POLL_SECONDS = 0.2

KeyboardHandler = Callable[[], None]


@dataclass(frozen=True)
class KeyboardEvent:
    name: str


class KeyboardEventDispatcher:
    def __init__(self, handlers: Mapping[str, KeyboardHandler]) -> None:
        self._handlers = dict(handlers)

    def dispatch(self, event: KeyboardEvent) -> bool:
        handler = self._handlers.get(event.name)
        if handler is None:
            return False
        handler()
        return True


def dispatch_keypress(
    key: bytes,
    dispatcher: KeyboardEventDispatcher,
    key_events: Mapping[bytes, str],
) -> bool:
    event_name = key_events.get(key)
    if event_name is None:
        return False
    return dispatcher.dispatch(KeyboardEvent(event_name))


@contextmanager
def listen_for_keyboard_events(
    handlers: Mapping[str, KeyboardHandler],
    key_events: Mapping[bytes, str],
) -> Iterator[None]:
    """Dispatch configured keyboard events while the body runs.

    A no-op when stdin is not an interactive terminal (pipes, tests, CI).
    """
    if not handlers or not sys.stdin.isatty():
        yield
        return

    import termios

    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    raw = termios.tcgetattr(fd)
    raw[3] &= ~(termios.ICANON | termios.ECHO | termios.IEXTEN)  # lflags
    if hasattr(termios, "VDISCARD"):
        raw[6][termios.VDISCARD] = 0  # stop Ctrl+O from being eaten as "discard output"

    dispatcher = KeyboardEventDispatcher(handlers)
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            ready, _, _ = select.select([fd], [], [], POLL_SECONDS)
            if ready:
                dispatch_keypress(os.read(fd, 1), dispatcher, key_events)

    termios.tcsetattr(fd, termios.TCSANOW, raw)
    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1.0)
        termios.tcsetattr(fd, termios.TCSADRAIN, original)
