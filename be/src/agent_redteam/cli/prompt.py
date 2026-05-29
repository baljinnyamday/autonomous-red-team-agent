"""Interactive task prompt built on prompt_toolkit.

Gives the REPL real line editing: persistent history (↑/↓, Ctrl+R), tab
completion of ``/slash`` commands, and keyboard event bindings from the prompt
itself. Falls back to plain
``input()`` when stdin is not an interactive terminal (pipes, tests, CI).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings

from agent_redteam.cli.keyboard import (
    KeyboardEvent,
    KeyboardEventDispatcher,
    KeyboardHandler,
)

_PROMPT = HTML("\n<b>agent&gt;</b> ")
_PLAIN_PROMPT = "\nagent> "


class SlashCompleter(Completer):
    """Completes ``/command`` names once the line starts with a slash."""

    def __init__(self, names: Iterable[str]) -> None:
        self._names = sorted(names)

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterator[Completion]:
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        prefix = text[1:]
        for name in self._names:
            if name.startswith(prefix):
                yield Completion(f"/{name}", start_position=-len(text))


class TaskReader:
    """Reads task lines, with full line editing on a TTY and a plain fallback."""

    def __init__(
        self,
        history_path: Path,
        slash_names: Iterable[str],
        keyboard_handlers: Mapping[str, KeyboardHandler],
        prompt_key_events: Mapping[str, str],
    ) -> None:
        if not sys.stdin.isatty():
            self._session: PromptSession[str] | None = None
            return

        history_path.parent.mkdir(parents=True, exist_ok=True)
        self._session = PromptSession(
            history=FileHistory(str(history_path)),
            completer=SlashCompleter(slash_names),
            complete_while_typing=True,
            key_bindings=_key_bindings(
                KeyboardEventDispatcher(keyboard_handlers),
                prompt_key_events,
            ),
        )

    def read(self) -> str:
        if self._session is None:
            return input(_PLAIN_PROMPT)
        return self._session.prompt(_PROMPT)


def _key_bindings(
    dispatcher: KeyboardEventDispatcher,
    prompt_key_events: Mapping[str, str],
) -> KeyBindings:
    bindings = KeyBindings()

    def add_binding(prompt_key: str, event_name: str) -> None:
        @bindings.add(prompt_key)
        def _dispatch(_event: object) -> None:
            run_in_terminal(lambda: dispatcher.dispatch(KeyboardEvent(event_name)))

    for prompt_key, event_name in prompt_key_events.items():
        add_binding(prompt_key, event_name)
    return bindings
