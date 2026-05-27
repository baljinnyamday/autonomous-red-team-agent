from urllib.parse import urlparse

from agent_redteam.core.config import Settings, get_settings
from agent_redteam.core.exceptions import OutOfScopeError


def _normalize_target(target: str) -> str:
    if "://" in target:
        parsed = urlparse(target)
        return (parsed.hostname or target).lower()
    return target.split("/")[0].lower()


def assert_target_in_scope(target: str, settings: Settings | None = None) -> None:
    """Ensure the target is on the engagement allowlist."""
    cfg = settings or get_settings()
    allowlist = {_normalize_target(t) for t in cfg.allowed_target_list()}
    if not allowlist:
        raise OutOfScopeError("ALLOWED_TARGETS is empty; define scope before testing.")
    normalized = _normalize_target(target)
    if normalized not in allowlist:
        raise OutOfScopeError(f"Target {target!r} is not in ALLOWED_TARGETS.")
