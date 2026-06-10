from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.roles.executor import ExecutorAgent
from agent_redteam.agents.roles.planner import PlannerAgent
from agent_redteam.agents.roles.reporter import ReporterAgent


class EngagementWorkflow:
    """Coordinates planner → executor → reporter for one engagement."""

    def __init__(self) -> None:
        self._planner = PlannerAgent()
        self._executor = ExecutorAgent()
        self._reporter = ReporterAgent()

    async def run(self, engagement_id: str) -> dict[str, object]:
        context = AgentContext(engagement_id=engagement_id, metadata={})
        plan = await self._planner.run(context, {})
        results = await self._executor.run(context, {"plan": plan})
        report = await self._reporter.run(context, {"results": results.get("results", [])})
        return {"plan": plan, "results": results, "report": report}
