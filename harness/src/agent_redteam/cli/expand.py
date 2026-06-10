"""Expandable run history rendering for the interactive CLI."""

from __future__ import annotations

import threading
from typing import Any

from rich.console import Console

from agent_redteam.agents.events import LoopEvent, LoopObserver
from agent_redteam.cli.render import event_fields, render_event


class ExpandableHistory:
    """Records run events so the full history can be re-rendered uncollapsed."""

    def __init__(self, console: Console) -> None:
        self._console = console
        self._events: list[tuple[str, dict[str, Any]]] = []
        self._expanded = False
        self._lock = threading.Lock()

    def observer(self) -> LoopObserver:
        def record(event: LoopEvent) -> None:
            with self._lock:
                self._events.append((event.type, event_fields(event)))

        return record

    def toggle(self) -> None:
        """Re-print the whole history, flipping between expanded and collapsed."""
        with self._lock:
            events = list(self._events)
            self._expanded = not self._expanded
            expanded = self._expanded
        self._render(events, expanded)

    def render_expanded(self) -> None:
        """Re-print the whole history with every block expanded."""
        with self._lock:
            events = list(self._events)
            self._expanded = True
        self._render(events, expanded=True)

    def _render(self, events: list[tuple[str, dict[str, Any]]], expanded: bool) -> None:
        if not events:
            return
        label = "expanded" if expanded else "collapsed"
        self._console.rule(f"[bold cyan]{label} history (ctrl+o)[/bold cyan]")
        for event_type, fields in events:
            render_event(self._console, event_type, fields, collapse=not expanded)
