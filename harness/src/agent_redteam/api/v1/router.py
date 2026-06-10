"""Aggregate v1 routers — wire into FastAPI app when added."""

ROUTE_MODULES = (
    "agent_redteam.api.v1.routes.health",
    "agent_redteam.api.v1.routes.engagements",
)
