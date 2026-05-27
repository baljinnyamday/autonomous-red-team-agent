from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    authorized_engagement: bool = Field(
        default=False,
        description="Must be true before any red team operation runs.",
    )
    engagement_id: str | None = None
    engagement_operator: str | None = None
    allowed_targets: str = Field(
        default="",
        description="Comma-separated allowlist of hosts or URLs.",
    )
    log_level: str = "INFO"

    def allowed_target_list(self) -> list[str]:
        return [t.strip() for t in self.allowed_targets.split(",") if t.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
