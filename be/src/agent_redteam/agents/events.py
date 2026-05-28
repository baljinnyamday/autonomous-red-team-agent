from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

LoopEventType = Literal[
    "run_started",
    "turn_started",
    "thinking",
    "assistant_message",
    "tool_call",
    "tool_result",
    "usage",
    "run_finished",
]


@dataclass(frozen=True)
class LoopEvent:
    """A single observable moment in an agent run.

    One envelope covers every step so observers (live console, audit log) can
    switch on ``type`` and read only the fields that apply.
    """

    type: LoopEventType
    iteration: int = 0
    text: str | None = None
    tool_name: str | None = None
    call_id: str | None = None
    arguments: dict[str, Any] | None = None
    freeform_input: str | None = None
    success: bool | None = None
    output: str | None = None
    error: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


LoopObserver = Callable[[LoopEvent], None]


def fan_out(observers: list[LoopObserver]) -> LoopObserver:
    """Combine observers so the loop only has to call one."""

    def emit(event: LoopEvent) -> None:
        for observer in observers:
            observer(event)

    return emit
