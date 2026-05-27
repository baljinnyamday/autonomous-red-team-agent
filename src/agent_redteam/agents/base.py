from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentContext:
    engagement_id: str
    target: str
    metadata: dict[str, Any]


class Agent(ABC):
    """Base contract for a single red team agent role."""

    role: str

    @abstractmethod
    async def run(self, context: AgentContext, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute one agent step and return structured output."""
