"""FastAPI app serving the live dashboard contract.

Routes match what the frontend pins in `fe/src/types/domain.ts`:

    GET /api/v1/health
    GET /api/v1/engagements
    GET /api/v1/engagements/{id}
    GET /api/v1/engagements/{id}/events   (Server-Sent Events)

A single live engagement is served per run. The SSE stream replays the current
state on connect, then forwards live deltas from the hub.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from agent_redteam import __version__
from agent_redteam.api.status_hub import StatusHub
from agent_redteam.schemas.common import HealthResponse
from agent_redteam.schemas.dashboard import Engagement

_SSE_PING_SECONDS = 15.0


def create_app(hub: StatusHub) -> FastAPI:
    app = FastAPI(title="agent-redteam dashboard", version=__version__)

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(version=__version__)

    @app.get("/api/v1/engagements", response_model=list[Engagement])
    def list_engagements() -> list[Engagement]:
        return [hub.engagement()]

    @app.get("/api/v1/engagements/{engagement_id}", response_model=Engagement)
    def get_engagement(engagement_id: str) -> Engagement:
        if engagement_id != hub.engagement_id:
            raise HTTPException(status_code=404, detail="unknown engagement")
        return hub.engagement()

    @app.get("/api/v1/engagements/{engagement_id}/events")
    def stream_events(engagement_id: str) -> StreamingResponse:
        if engagement_id != hub.engagement_id:
            raise HTTPException(status_code=404, detail="unknown engagement")
        return StreamingResponse(_event_source(hub), media_type="text/event-stream")

    return app


async def _event_source(hub: StatusHub) -> AsyncIterator[str]:
    queue = hub.subscribe()
    try:
        for event in hub.snapshot_events():
            yield _frame(event)
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_SSE_PING_SECONDS)
            except TimeoutError:
                yield ": keep-alive\n\n"  # hold the connection open through idle gaps
                continue
            yield _frame(event)
    finally:
        hub.unsubscribe(queue)


def _frame(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"
