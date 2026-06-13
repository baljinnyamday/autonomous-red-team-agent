"""Response models for the live dashboard API.

These mirror the frontend domain types in `fe/src/types/domain.ts` and serialize
to camelCase (`createdAt`, `discoveredAt`, `nodeId`) so the React client folds them
straight into its reducer. Keep the two files in sync — this is the FE↔BE boundary.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

EngagementStatus = Literal["draft", "running", "completed", "aborted"]
NodeStatus = Literal["discovered", "scanning", "exploiting", "compromised", "failed"]
AccessLevel = Literal["none", "user", "root"]
AgentRole = Literal["planner", "executor", "reporter"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Engagement(CamelModel):
    id: str
    operator: str
    targets: list[str]
    status: EngagementStatus
    created_at: str  # ISO 8601; the client derives uptime from this


class RedTeamNode(CamelModel):
    id: str
    hostname: str
    ip: str
    os: str | None = None
    status: NodeStatus
    access: AccessLevel
    techniques: list[str] = []
    discovered_at: str
    compromised_at: str | None = None


class AttackEdge(CamelModel):
    id: str
    source: str
    target: str
    technique: str
