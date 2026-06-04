from enum import StrEnum
from functools import lru_cache
from uuid import uuid4

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent_redteam.core.exceptions import ConfigurationError


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
    agent_provider: AgentProvider = AgentProvider.OPENAI
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.5"
    openai_prompt_cache_key: str | None = None
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    audit_log_path: str = ".runs"
    log_level: str = "INFO"
    engagement_topology_path: str | None = None
    engagement_state_path: str | None = None
    engagement_runner_token: SecretStr | None = None
    bash_timeout_seconds: float | None = None
    runner_port: int = 8765
    default_exec_timeout_seconds: float = 3600.0

    def effective_exec_timeout_seconds(self) -> float | None:
        if self.bash_timeout_seconds is not None:
            return self.bash_timeout_seconds
        return self.default_exec_timeout_seconds

    def require_openai_api_key(self) -> str:
        return _required_secret_value(self.openai_api_key, "OPENAI_API_KEY")

    def require_anthropic_api_key(self) -> str:
        return _required_secret_value(self.anthropic_api_key, "ANTHROPIC_API_KEY")

    def require_runner_token(self) -> str:
        return _required_secret_value(
            self.engagement_runner_token,
            "ENGAGEMENT_RUNNER_TOKEN",
        )

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

    @field_validator(
        "openai_api_key",
        "anthropic_api_key",
        "openai_prompt_cache_key",
        "engagement_topology_path",
        "engagement_state_path",
        "engagement_runner_token",
        mode="before",
    )
    @classmethod
    def _blank_optional_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("bash_timeout_seconds", mode="before")
    @classmethod
    def _blank_timeout_to_none(cls, value: object) -> object:
        if value == "" or value is None:
            return None
        return value


def _required_secret_value(secret: SecretStr | None, env_name: str) -> str:
    if secret is None:
        msg = f"{env_name} is required for the selected agent provider. Set it in .env."
        raise ConfigurationError(msg)
    return secret.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
