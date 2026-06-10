import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_redteam.agents.events import LoopEvent, LoopObserver

ANALYTICS_DIR_NAME = "analytics"
RUN_FILE_PREFIX = "run-"
RUN_FILE_SUFFIX = ".jsonl"
RUN_ID_WIDTH = 4


class AuditRunNotFoundError(FileNotFoundError):
    """Raised when a run directory does not contain any audit logs."""


class AuditRecorder:
    def __init__(self, path: str | Path, *, run_id: int | None = None) -> None:
        self._path = Path(path)
        self._run_id = run_id

    @classmethod
    def for_new_run(
        cls,
        root_or_legacy_path: str | Path,
        *,
        now: datetime | None = None,
    ) -> "AuditRecorder":
        run = allocate_audit_run_path(root_or_legacy_path, now=now)
        return cls(run.path, run_id=run.run_id)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def run_id(self) -> int | None:
        return self._run_id

    def record(self, event_type: str, **fields: Any) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            **({"run_id": self._run_id} if self._run_id is not None else {}),
            **fields,
        }
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, sort_keys=True) + "\n")


@dataclass(frozen=True)
class AuditRunPath:
    path: Path
    run_id: int


def allocate_audit_run_path(
    root_or_legacy_path: str | Path,
    *,
    now: datetime | None = None,
) -> AuditRunPath:
    root = _audit_root(root_or_legacy_path)
    run_date = (now or datetime.now(UTC)).date().isoformat()
    analytics_dir = root / run_date / ANALYTICS_DIR_NAME
    analytics_dir.mkdir(parents=True, exist_ok=True)

    run_id = _next_run_id(analytics_dir)
    while True:
        path = analytics_dir / _run_filename(run_id)
        try:
            with path.open("x", encoding="utf-8"):
                pass
        except FileExistsError:
            run_id += 1
            continue
        return AuditRunPath(path=path, run_id=run_id)


def latest_audit_log_path(root_or_log_path: str | Path) -> Path:
    path = Path(root_or_log_path)
    if path.is_file():
        return path

    candidates = [
        candidate
        for candidate in path.rglob(f"{RUN_FILE_PREFIX}*{RUN_FILE_SUFFIX}")
        if _run_id_from_filename(candidate.name) is not None
    ]
    if not candidates:
        msg = f"No audit logs found under {path}"
        raise AuditRunNotFoundError(msg)
    return max(candidates, key=_audit_sort_key)


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


def _audit_root(root_or_legacy_path: str | Path) -> Path:
    path = Path(root_or_legacy_path)
    if path.suffix == RUN_FILE_SUFFIX:
        return path.parent
    return path


def _next_run_id(analytics_dir: Path) -> int:
    run_ids = [
        run_id
        for path in analytics_dir.glob(f"{RUN_FILE_PREFIX}*{RUN_FILE_SUFFIX}")
        if (run_id := _run_id_from_filename(path.name)) is not None
    ]
    return max(run_ids, default=0) + 1


def _run_filename(run_id: int) -> str:
    return f"{RUN_FILE_PREFIX}{run_id:0{RUN_ID_WIDTH}d}{RUN_FILE_SUFFIX}"


def _audit_sort_key(path: Path) -> tuple[str, int]:
    run_date = path.parent.parent.name if path.parent.name == ANALYTICS_DIR_NAME else ""
    return (run_date, _run_id_from_filename(path.name) or 0)


def _run_id_from_filename(filename: str) -> int | None:
    if not filename.startswith(RUN_FILE_PREFIX) or not filename.endswith(RUN_FILE_SUFFIX):
        return None
    raw_run_id = filename.removeprefix(RUN_FILE_PREFIX).removesuffix(RUN_FILE_SUFFIX)
    if not raw_run_id.isdecimal():
        return None
    return int(raw_run_id)
