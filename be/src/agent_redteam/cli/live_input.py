"""Non-blocking ``/slash`` input for the autonomous run.

The autonomous loop never blocks on ``input()``. To still let an operator peek
or steer, a daemon thread reads stdin lines and queues any ``/command``; a loop
observer drains that queue between events and dispatches through the existing
slash handler. Non-slash lines are ignored.
"""

from __future__ import annotations

import queue
import sys
import threading
from collections.abc import Callable, Mapping

from agent_redteam.agents.events import LoopEvent, LoopObserver
from agent_redteam.cli.slash import SlashCommand, SlashCommandContext, handle_slash_command


def start_slash_input_thread() -> queue.Queue[str]:
    commands: queue.Queue[str] = queue.Queue()

    def read_lines() -> None:
        for line in sys.stdin:
            stripped = line.strip()
            if stripped.startswith("/"):
                commands.put(stripped)

    threading.Thread(target=read_lines, name="slash-input", daemon=True).start()
    return commands


def live_slash_observer(
    commands: queue.Queue[str],
    make_context: Callable[[], SlashCommandContext],
    slash_commands: Mapping[str, SlashCommand],
) -> LoopObserver:
    def observe(_event: LoopEvent) -> None:
        while True:
            try:
                line = commands.get_nowait()
            except queue.Empty:
                return
            handle_slash_command(line, make_context(), slash_commands)

    return observe
