"""Autonomous supervisor that drives the inner ReAct loop unattended.

When run without a human at the keyboard, the inner :class:`AgentLoop` ends as
soon as the model stops calling tools. To sustain an extended run, this
supervisor re-invokes the loop with a constant nudge (no new information) until
either the agent calls the ``finish`` tool or a wall-clock deadline passes.

The wall-clock budget is checked at cycle boundaries (after each inner
completion), so a single in-flight cycle may overrun slightly. This is a
deliberate trade-off over mid-cycle cancellation, which could corrupt an
in-flight tool call or audit record.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.events import LoopEvent, LoopObserver
from agent_redteam.agents.loop import AgentLoop, AgentLoopResult
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.llm.types import AgentMessage, ProviderHarness
from agent_redteam.tools.finish import FINISH_TOOL_NAME
from agent_redteam.tools.registry import ToolRegistry

CONTINUE_NUDGE = "Continue."
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600}

StopReason = Literal["finished", "duration", "error"]


@dataclass(frozen=True)
class AutonomousResult:
    result: AgentLoopResult
    stop_reason: StopReason
    cycles: int


def parse_duration(text: str) -> float:
    """Parse a duration like ``30m``, ``45s``, ``1h`` or a bare number of seconds."""
    raw = text.strip().lower()
    if not raw:
        raise ConfigurationError("Duration must not be empty.")

    unit = raw[-1]
    value, multiplier = (raw[:-1], _DURATION_UNITS[unit]) if unit in _DURATION_UNITS else (raw, 1)
    try:
        seconds = float(value) * multiplier
    except ValueError:
        raise ConfigurationError(
            f"Invalid duration: {text!r}. Use seconds or a s/m/h suffix, e.g. 30m."
        ) from None
    if seconds <= 0:
        raise ConfigurationError(f"Duration must be positive: {text!r}.")
    return seconds


def agent_called_finish(result: AgentLoopResult) -> bool:
    """True if any assistant turn in the run invoked the ``finish`` tool."""
    for message in result.messages:
        if message.role != "assistant":
            continue
        tool_calls = message.provider_metadata.get("tool_calls", [])
        if any(call.get("name") == FINISH_TOOL_NAME for call in tool_calls):
            return True
    return False


async def run_autonomous(
    *,
    context: AgentContext,
    provider: ProviderHarness,
    registry: ToolRegistry,
    observer: LoopObserver,
    objective: str,
    messages: list[AgentMessage],
    deadline: float,
    clock: Callable[[], float] = time.monotonic,
    before_cycle: Callable[[list[AgentMessage], AgentContext], None] | None = None,
) -> AutonomousResult:
    """Re-run the inner loop until the agent finishes or the deadline passes.

    ``messages`` is an explicit conversation buffer: it is seeded by the caller
    (e.g. the system prompt) and updated in place each cycle so that live
    observers can read the current history.
    """
    loop = AgentLoop(provider=provider, tool_registry=registry, observer=observer)
    messages.append(AgentMessage(role="user", content=objective))

    cycle = 0
    while True:
        cycle += 1
        if before_cycle is not None:
            before_cycle(messages, context)
        observer(LoopEvent(type="run_started", text=objective if cycle == 1 else CONTINUE_NUDGE))
        result = await loop.run(context, messages)
        messages[:] = result.messages

        if not result.success:
            return AutonomousResult(result, "error", cycle)
        if agent_called_finish(result):
            return AutonomousResult(result, "finished", cycle)
        if clock() >= deadline:
            return AutonomousResult(result, "duration", cycle)

        messages.append(AgentMessage(role="user", content=CONTINUE_NUDGE))
