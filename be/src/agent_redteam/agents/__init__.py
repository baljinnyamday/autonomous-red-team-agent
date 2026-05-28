"""Agent roles and runtime adapters for LLM-driven red team steps."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_redteam.agents.loop import AgentLoop, AgentLoopLimits, AgentLoopResult

__all__ = ["AgentLoop", "AgentLoopLimits", "AgentLoopResult"]


def __getattr__(name: str) -> object:
    if name == "AgentLoop":
        from agent_redteam.agents.loop import AgentLoop

        return AgentLoop
    if name == "AgentLoopLimits":
        from agent_redteam.agents.loop import AgentLoopLimits

        return AgentLoopLimits
    if name == "AgentLoopResult":
        from agent_redteam.agents.loop import AgentLoopResult

        return AgentLoopResult
    raise AttributeError(name)
