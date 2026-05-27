from agent_redteam.core.config import Settings, get_settings
from agent_redteam.core.exceptions import AuthorizationError


def require_authorized_engagement(settings: Settings | None = None) -> None:
    """Block execution unless the deployment is explicitly marked authorized."""
    cfg = settings or get_settings()
    if not cfg.authorized_engagement:
        msg = (
            "AUTHORIZED_ENGAGEMENT is not enabled. "
            "Set AUTHORIZED_ENGAGEMENT=true in .env only for written, in-scope engagements."
        )
        raise AuthorizationError(msg)
    if not cfg.engagement_id:
        raise AuthorizationError("ENGAGEMENT_ID is required for auditability.")
