import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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
