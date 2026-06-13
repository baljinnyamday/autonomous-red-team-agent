"""Run the dashboard server in-process, alongside the autonomous agent loop.

``serve_and_run`` shares one event loop between uvicorn and the agent run: the
agent's ``LoopEvent`` stream feeds the hub in real time, while a background ticker
diffs the live topology and broadcasts node/edge deltas. The server lives exactly
as long as the run, plus a final ``engagement.status`` once it settles.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from datetime import datetime

import uvicorn

from agent_redteam.agents.autonomous import AutonomousResult, run_autonomous
from agent_redteam.agents.base import AgentContext
from agent_redteam.agents.events import LoopObserver, fan_out
from agent_redteam.api.app import create_app
from agent_redteam.api.events import status_observer
from agent_redteam.api.status_hub import StatusHub
from agent_redteam.llm.types import AgentMessage, ProviderHarness
from agent_redteam.schemas.dashboard import EngagementStatus
from agent_redteam.targets.state import EngagementState
from agent_redteam.targets.store import EngagementStore
from agent_redteam.tools.registry import ToolRegistry

_STOP_REASON_STATUS: dict[str, EngagementStatus] = {
    "finished": "completed",
    "duration": "completed",
    "error": "aborted",
}


async def serve_and_run(
    *,
    context: AgentContext,
    provider: ProviderHarness,
    registry: ToolRegistry,
    observer: LoopObserver,
    objective: str,
    messages: list[AgentMessage],
    deadline: float,
    before_cycle: Callable[[list[AgentMessage], AgentContext], None] | None,
    operator: str,
    targets: list[str],
    started_at: datetime,
    host: str,
    port: int,
    poll_interval: float,
) -> AutonomousResult:
    hub = StatusHub(
        engagement_id=context.engagement_id,
        operator=operator,
        targets=targets,
        started_at=started_at,
        live_state=_live_topology_state(context),
    )
    hub.refresh_topology()  # seed the snapshot with topology known at startup

    config = uvicorn.Config(create_app(hub), host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    differ_task = asyncio.create_task(_differ(hub, poll_interval))

    merged = fan_out([observer, status_observer(hub)])
    try:
        outcome = await run_autonomous(
            context=context,
            provider=provider,
            registry=registry,
            observer=merged,
            objective=objective,
            messages=messages,
            deadline=deadline,
            before_cycle=before_cycle,
        )
    finally:
        differ_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await differ_task

    hub.refresh_topology()  # flush any final deltas before announcing the status
    hub.set_status(_STOP_REASON_STATUS.get(outcome.stop_reason, "completed"))
    await _shutdown(server, server_task)
    return outcome


def _live_topology_state(context: AgentContext) -> Callable[[], EngagementState]:
    """Reload topology from SQLite so delegate sub-agents stay visible on the dashboard."""
    store = context.metadata.get("engagement_store")
    if isinstance(store, EngagementStore) and context.engagement_id:
        engagement_id = context.engagement_id
        return lambda: store.load_state(engagement_id)

    cached = context.metadata.get("engagement_state")
    if isinstance(cached, EngagementState):
        return lambda: cached

    msg = "engagement_store or engagement_state is missing from agent context metadata."
    raise RuntimeError(msg)


async def _differ(hub: StatusHub, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        hub.refresh_topology()


async def _shutdown(server: uvicorn.Server, server_task: asyncio.Task[None]) -> None:
    server.should_exit = True
    with contextlib.suppress(asyncio.CancelledError):
        await server_task
