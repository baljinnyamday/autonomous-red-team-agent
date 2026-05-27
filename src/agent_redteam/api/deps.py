from agent_redteam.core.config import Settings, get_settings
from agent_redteam.guardrails import require_authorized_engagement


def get_app_settings() -> Settings:
    return get_settings()


def ensure_authorized() -> None:
    require_authorized_engagement()
