from pathlib import Path

import pytest

from agent_redteam.core.config import AgentProvider, Settings
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.llm.openai import OpenAIResponsesHarness
from agent_redteam.simple_react import _build_provider, _build_registry, _parse_args


def test_settings_loads_env_file_and_defaults_to_openai(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_name in ("AUTHORIZED_ENGAGEMENT", "AGENT_PROVIDER", "OPENAI_API_KEY"):
        monkeypatch.delenv(env_name, raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "AUTHORIZED_ENGAGEMENT=true\nOPENAI_API_KEY=sk-from-env-file\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.authorized_engagement is True
    assert settings.agent_provider is AgentProvider.OPENAI
    assert settings.require_openai_api_key() == "sk-from-env-file"


def test_build_provider_uses_openai_key_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        agent_provider=AgentProvider.OPENAI,
        openai_api_key="sk-from-settings",
    )

    provider = _build_provider(settings)

    assert isinstance(provider, OpenAIResponsesHarness)
    assert provider.model == settings.openai_model
    assert provider.api_key == "sk-from-settings"
    assert provider.prompt_cache_key == settings.engagement_id


def test_build_provider_requires_selected_provider_key() -> None:
    settings = Settings(
        _env_file=None,
        agent_provider=AgentProvider.OPENAI,
        openai_api_key=None,
    )

    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
        _build_provider(settings)


def test_main_args_parses_optional_task() -> None:
    args = _parse_args(["scan internal segment"])

    assert args.task == "scan internal segment"


def test_default_agent_registry_contains_exec_and_finish() -> None:
    registry = _build_registry()

    assert [tool.name for tool in registry.definitions()] == ["exec", "finish"]
