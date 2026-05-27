from typing import Any

from agent_redteam.agents.base import Agent, AgentContext


class ExecutorAgent(Agent):
    role = "executor"

    async def run(self, context: AgentContext, input_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "role": self.role,
            "engagement_id": context.engagement_id,
            "results": [],
            "notes": "Executor stub — wire tools and in-scope actions only.",
        }
