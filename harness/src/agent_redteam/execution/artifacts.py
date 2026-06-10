from pathlib import Path

from agent_redteam.core.config import Settings
from agent_redteam.core.exceptions import ConfigurationError


def engagement_artifacts_root(settings: Settings, engagement_id: str) -> Path:
    audit_path = Path(settings.audit_log_path)
    audit_root = audit_path.parent if audit_path.suffix else audit_path
    return audit_root / f"engagement-{engagement_id}" / "artifacts"


def resolve_local_name(*, local_name: str | None, remote_path: str) -> str:
    name = local_name if local_name is not None else Path(remote_path).name
    if not name:
        msg = "Could not determine artifact filename from remote_path."
        raise ConfigurationError(msg)
    if name != Path(name).name or ".." in Path(name).parts:
        msg = f"Invalid artifact name {name!r}: must be a bare filename without path separators."
        raise ConfigurationError(msg)
    return name


def resolve_artifact_path(
    settings: Settings,
    engagement_id: str,
    host_id: str,
    *,
    local_name: str | None,
    remote_path: str,
) -> Path:
    if Path(host_id).name != host_id:
        msg = f"Invalid host id as path component: {host_id!r}."
        raise ConfigurationError(msg)
    filename = resolve_local_name(local_name=local_name, remote_path=remote_path)
    host_dir = engagement_artifacts_root(settings, engagement_id) / host_id
    destination = (host_dir / filename).resolve()
    host_resolved = host_dir.resolve()
    try:
        destination.relative_to(host_resolved)
    except ValueError as exc:
        msg = f"Artifact path {destination!s} escapes the host artifacts directory."
        raise ConfigurationError(msg) from exc
    return destination
