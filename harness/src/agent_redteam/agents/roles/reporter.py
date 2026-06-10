from typing import Any

from agent_redteam.agents.base import Agent, AgentContext


class ReporterAgent(Agent):
    role = "reporter"

    async def run(self, context: AgentContext, input_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "role": self.role,
            "engagement_id": context.engagement_id,
            "results": input_data.get("results", []),
            "notes": "Reporter stub — summarize run results for review.",
        }
