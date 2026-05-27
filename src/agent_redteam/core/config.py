from enum import StrEnum
from functools import lru_cache
from uuid import uuid4

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentProvider(StrEnum):
    OPENAI = "openai"
    CLAUDE = "claude"


def _default_engagement_id() -> str:
    return f"eng-{uuid4().hex[:12]}"


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
    engagement_id: str = Field(default_factory=_default_engagement_id)
    engagement_operator: str = "cli"
    allowed_targets: str = Field(
        default="localhost,127.0.0.1,::1",
        description="Comma-separated allowlist of hosts or URLs.",
    )
    agent_provider: AgentProvider = AgentProvider.OPENAI
    agent_target: str = "localhost"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.5"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    audit_log_path: str = ".runs/audit.jsonl"
    log_level: str = "INFO"

    def allowed_target_list(self) -> list[str]:
        return [t.strip() for t in self.allowed_targets.split(",") if t.strip()]

    @field_validator("engagement_id", mode="before")
    @classmethod
    def _default_blank_engagement_id(cls, value: object) -> object:
        if value is None or value == "":
            return _default_engagement_id()
        return value

    @field_validator("engagement_operator", mode="before")
    @classmethod
    def _default_blank_operator(cls, value: object) -> object:
        if value is None or value == "":
            return "cli"
        return value

    @field_validator("openai_api_key", "anthropic_api_key", mode="before")
    @classmethod
    def _blank_secret_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
