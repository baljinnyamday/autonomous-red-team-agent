from collections.abc import Sequence
from typing import Any

from agent_redteam.agents.base import Agent, AgentContext
from agent_redteam.agents.loop import AgentLoop
from agent_redteam.llm.types import AgentMessage


class ExecutorAgent(Agent):
    role = "executor"

    def __init__(
        self,
        agent_loop: AgentLoop | None = None,
        initial_messages: Sequence[AgentMessage] = (),
    ) -> None:
        self._agent_loop = agent_loop
        self._initial_messages = tuple(initial_messages)

    async def run(self, context: AgentContext, input_data: dict[str, Any]) -> dict[str, Any]:
        if self._agent_loop is not None:
            result = await self._agent_loop.run(context, self._initial_messages)
            return {
                "role": self.role,
                "engagement_id": context.engagement_id,
                "results": [
                    {
                        "success": result.success,
                        "final_message": result.final_message,
                        "iterations": result.iterations,
                        "error": result.error,
                    }
                ],
                "notes": "Executor ran injected agent loop.",
            }

        return {
            "role": self.role,
            "engagement_id": context.engagement_id,
            "results": [],
            "notes": "Executor stub — wire tools and in-scope actions only.",
        }
