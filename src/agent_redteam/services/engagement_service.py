from agent_redteam.guardrails import assert_target_in_scope, require_authorized_engagement
from agent_redteam.orchestration.workflow import EngagementWorkflow


class EngagementService:
    """Runs a scoped target through guardrails and the default agent workflow."""

    def __init__(self, workflow: EngagementWorkflow | None = None) -> None:
        self._workflow = workflow or EngagementWorkflow()

    async def run(self, engagement_id: str, target: str) -> dict[str, object]:
        require_authorized_engagement()
        assert_target_in_scope(target)
        return await self._workflow.run(engagement_id, target)
