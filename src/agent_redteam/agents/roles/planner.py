from typing import Any

from agent_redteam.agents.base import Agent, AgentContext


class PlannerAgent(Agent):
    role = "planner"

    async def run(self, context: AgentContext, input_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "role": self.role,
            "engagement_id": context.engagement_id,
            "plan": [],
            "notes": "Planner stub — implement technique selection and step graph.",
        }
