import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_redteam.agents.events import LoopEvent, LoopObserver


class AuditRecorder:
    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def record(self, event_type: str, **fields: Any) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            **fields,
        }
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, sort_keys=True) + "\n")


def audit_observer(recorder: AuditRecorder, engagement_id: str) -> LoopObserver:
    """Persist every loop event to the raw audit log."""

    def observe(event: LoopEvent) -> None:
        recorder.record(
            event.type,
            engagement_id=engagement_id,
            **_event_fields(event),
        )

    return observe


def _event_fields(event: LoopEvent) -> dict[str, Any]:
    fields: dict[str, Any] = {"iteration": event.iteration}
    optional = {
        "text": event.text,
        "tool_name": event.tool_name,
        "call_id": event.call_id,
        "arguments": event.arguments,
        "freeform_input": event.freeform_input,
        "success": event.success,
        "output": event.output,
        "error": event.error,
    }
    fields.update({key: value for key, value in optional.items() if value is not None})
    if event.usage:
        fields["usage"] = event.usage
    return fields
