"""In-memory pub/sub and run state for the live dashboard.

One ``StatusHub`` exists per autonomous run. The ``status_observer`` and the
topology differ push ``ActivityEvent`` dicts through ``publish``; each connected
SSE client drains its own bounded queue. ``snapshot_events`` lets a late-joining
client fold straight to the current state before it starts receiving live deltas.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agent_redteam.api.topology_view import diff_topology
from agent_redteam.schemas.dashboard import AttackEdge, Engagement, EngagementStatus, RedTeamNode
from agent_redteam.targets.state import EngagementState

_QUEUE_MAXSIZE = 256


def _now() -> str:
    return datetime.now(UTC).isoformat()


class StatusHub:
    def __init__(
        self,
        *,
        engagement_id: str,
        operator: str,
        targets: list[str],
        started_at: datetime,
        live_state: Callable[[], EngagementState],
    ) -> None:
        self._engagement_id = engagement_id
        self._operator = operator
        self._targets = targets
        self._started_at = started_at
        self._live_state = live_state
        self._status: EngagementStatus = "running"
        self._nodes: dict[str, RedTeamNode] = {}
        self._edges: dict[str, AttackEdge] = {}
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    @property
    def engagement_id(self) -> str:
        return self._engagement_id

    def engagement(self) -> Engagement:
        return Engagement(
            id=self._engagement_id,
            operator=self._operator,
            targets=self._targets,
            status=self._status,
            created_at=self._started_at.isoformat(),
        )

    def set_status(self, status: EngagementStatus) -> None:
        self._status = status
        self.publish({"type": "engagement.status", "status": status, "at": _now()})

    def refresh_topology(self) -> None:
        """Diff the live state and broadcast any node/edge deltas."""
        events, self._nodes, self._edges = diff_topology(
            self._nodes, self._edges, self._live_state(), _now()
        )
        for event in events:
            self.publish(event)

    def snapshot_events(self) -> list[dict[str, Any]]:
        """Full current state as a replay burst for a freshly connected client."""
        events: list[dict[str, Any]] = [
            {"type": "engagement.status", "status": self._status, "at": _now()}
        ]
        events.extend(
            {"type": "node.discovered", "node": node.model_dump(by_alias=True), "at": _now()}
            for node in self._nodes.values()
        )
        events.extend(
            {"type": "edge.added", "edge": edge.model_dump(by_alias=True), "at": _now()}
            for edge in self._edges.values()
        )
        return events

    def publish(self, event: dict[str, Any]) -> None:
        for queue in self._subscribers:
            if queue.full():
                queue.get_nowait()  # drop oldest; a slow client must not stall the run
            queue.put_nowait(event)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)
