import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings
from agent_redteam.execution.result import CommandResult
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.store import EngagementStore
from agent_redteam.targets.topology import Transport
from agent_redteam.tools.grep import (
    GrepArgs,
    build_grep_command,
    format_grep_result,
    grep_definition,
    grep_tool,
)
from agent_redteam.tools.types import ToolCall


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def _local_state() -> EngagementState:
    return EngagementState(
        engagement_id="eng-1",
        hosts={"operator": HostRuntime(transport=Transport.LOCAL)},
    )


def _context(
    tmp_path: Path,
    state: EngagementState | None = None,
    settings: Settings | None = None,
) -> AgentContext:
    resolved_state = state or _local_state()
    resolved_settings = settings or _settings()
    db_path = tmp_path / "engagement-state-test.db"
    store = EngagementStore.connect(db_path)
    store.save_state(resolved_state)
    return AgentContext(
        engagement_id="eng-1",
        metadata={
            "engagement_state": resolved_state,
            "settings": resolved_settings,
            "engagement_store": store,
            "engagement_db_path": str(db_path),
        },
    )


def test_build_grep_command_includes_rg_fallback_and_head() -> None:
    command = build_grep_command(
        GrepArgs(
            host="operator",
            pattern="secret",
            path="/etc",
            glob="*.conf",
            max_matches=50,
            ignore_case=True,
            output_mode="content",
        )
    )

    assert "command -v rg" in command
    assert command.startswith("set -o pipefail; ")
    assert "rg --no-config" in command
    assert "grep -rnIE" in command
    assert "head -n 50" in command
    assert "-i" in command
    assert "--glob '*.conf'" in command
    assert "-- /etc" in command
    assert "-e secret" in command


def test_build_grep_command_quotes_special_characters() -> None:
    command = build_grep_command(
        GrepArgs(
            host="operator",
            pattern="it's a $secret",
            path="/tmp/my dir",
        )
    )

    assert "'/tmp/my dir'" in command
    assert "it's a $secret" in command or "it'" in command


def test_build_grep_command_uses_extended_regex_fallback() -> None:
    command = build_grep_command(
        GrepArgs(
            host="operator",
            pattern=r"flag\{|FLAG\{|secret|token",
            path="/home/azureuser",
            glob=None,
            max_matches=200,
            ignore_case=True,
            output_mode="content",
        )
    )

    assert "grep -rnIE -i" in command


def test_build_grep_command_files_and_count_modes() -> None:
    files_cmd = build_grep_command(
        GrepArgs(
            host="operator",
            pattern="password",
            output_mode="files",
        )
    )
    count_cmd = build_grep_command(
        GrepArgs(
            host="operator",
            pattern="password",
            output_mode="count",
        )
    )

    assert " -l " in files_cmd or " -l -e" in files_cmd
    assert " -c " in count_cmd or " -c -e" in count_cmd


def test_format_grep_result_no_matches() -> None:
    result = CommandResult(exit_code=1, stdout=b"", stderr=b"", timed_out=False)
    assert format_grep_result(result, max_matches=100) == "No matches found"


def test_format_grep_result_exit_one_with_stderr_surfaces_error() -> None:
    result = CommandResult(
        exit_code=1,
        stdout=b"",
        stderr=b"grep warning",
        timed_out=False,
    )
    assert format_grep_result(result, max_matches=100) == "grep_error: grep warning"


def test_format_grep_result_success_with_truncation_note() -> None:
    lines = "\n".join(f"/etc/app.conf:{index}:secret={index}" for index in range(1, 101))
    result = CommandResult(exit_code=0, stdout=lines.encode(), stderr=b"", timed_out=False)
    output = format_grep_result(result, max_matches=100)

    assert output.startswith("matches: 100")
    assert "truncated at 100" in output
    assert "secret=1" in output


def test_format_grep_result_treats_sigpipe_as_success() -> None:
    result = CommandResult(
        exit_code=141,
        stdout=b"/etc/app.conf:1:secret=token\n",
        stderr=b"",
        timed_out=False,
    )
    output = format_grep_result(result, max_matches=100)

    assert output.startswith("matches: 1")
    assert "secret=token" in output


def test_format_grep_result_surfaces_failure() -> None:
    result = CommandResult(
        exit_code=2,
        stdout=b"",
        stderr=b"invalid regex",
        timed_out=False,
    )
    assert format_grep_result(result, max_matches=100) == "grep_error: invalid regex"


def test_local_grep_finds_planted_secret(tmp_path: Path) -> None:
    search_dir = tmp_path / "search-root"
    search_dir.mkdir()
    (search_dir / "app.conf").write_text("db_password=hunter2\n", encoding="utf-8")
    (search_dir / "readme.txt").write_text("nothing here\n", encoding="utf-8")

    output = asyncio.run(
        grep_tool(
            _context(tmp_path),
            ToolCall(
                call_id="g1",
                name="grep",
                arguments={
                    "host": "operator",
                    "pattern": "hunter2",
                    "path": str(search_dir),
                },
            ),
        )
    )

    assert output.startswith("matches: 1")
    assert "hunter2" in output
    assert "app.conf" in output


def test_local_grep_invalid_regex_surfaces_error(tmp_path: Path) -> None:
    search_dir = tmp_path / "invalid-regex-root"
    search_dir.mkdir()
    (search_dir / "app.conf").write_text("secret=1\n", encoding="utf-8")

    output = asyncio.run(
        grep_tool(
            _context(tmp_path),
            ToolCall(
                call_id="g-invalid",
                name="grep",
                arguments={
                    "host": "operator",
                    "pattern": "[",
                    "path": str(search_dir),
                },
            ),
        )
    )

    assert output.startswith("grep_error:")


def test_local_grep_respects_glob(tmp_path: Path) -> None:
    search_dir = tmp_path / "glob-root"
    search_dir.mkdir()
    (search_dir / "app.conf").write_text("token=abc\n", encoding="utf-8")
    (search_dir / "notes.txt").write_text("token=abc\n", encoding="utf-8")

    output = asyncio.run(
        grep_tool(
            _context(tmp_path),
            ToolCall(
                call_id="g2",
                name="grep",
                arguments={
                    "host": "operator",
                    "pattern": "token=",
                    "path": str(search_dir),
                    "glob": "*.conf",
                },
            ),
        )
    )

    assert "app.conf" in output
    assert "notes.txt" not in output


def test_local_grep_files_mode(tmp_path: Path) -> None:
    search_dir = tmp_path / "files-root"
    search_dir.mkdir()
    (search_dir / "one.conf").write_text("secret=1\n", encoding="utf-8")
    (search_dir / "two.conf").write_text("secret=2\n", encoding="utf-8")

    output = asyncio.run(
        grep_tool(
            _context(tmp_path),
            ToolCall(
                call_id="g3",
                name="grep",
                arguments={
                    "host": "operator",
                    "pattern": "secret=",
                    "path": str(search_dir),
                    "output_mode": "files",
                },
            ),
        )
    )

    assert output.startswith("matches:")
    assert "one.conf" in output
    assert "two.conf" in output
    assert "secret=1" not in output


def test_grep_tool_passes_agent_timeout_override(tmp_path: Path) -> None:
    captured: list[float | None] = []

    async def fake_execute_on_host(
        state: EngagementState,
        host_id: str,
        command: str,
        settings: Settings,
        *,
        timeout_seconds: float | None = None,
        run_command=None,
    ) -> tuple[CommandResult, EngagementState]:
        captured.append(timeout_seconds)
        return CommandResult(exit_code=1, stdout=b"", stderr=b"", timed_out=False), state

    import agent_redteam.tools.grep as grep_module

    original = grep_module.execute_on_host
    grep_module.execute_on_host = fake_execute_on_host
    try:
        asyncio.run(
            grep_tool(
                _context(tmp_path, settings=_settings(grep_timeout_seconds=120.0)),
                ToolCall(
                    call_id="g-timeout",
                    name="grep",
                    arguments={
                        "host": "operator",
                        "pattern": "secret",
                        "path": "/tmp",
                        "timeout_seconds": 30.0,
                    },
                ),
            )
        )
    finally:
        grep_module.execute_on_host = original

    assert captured == [30.0]


def test_grep_tool_uses_settings_default_timeout_when_unset(tmp_path: Path) -> None:
    """Omit defaulted fields; env grep_timeout_seconds applies when timeout is still 120."""
    captured: list[float | None] = []

    async def fake_execute_on_host(
        state: EngagementState,
        host_id: str,
        command: str,
        settings: Settings,
        *,
        timeout_seconds: float | None = None,
        run_command=None,
    ) -> tuple[CommandResult, EngagementState]:
        captured.append(timeout_seconds)
        return CommandResult(exit_code=1, stdout=b"", stderr=b"", timed_out=False), state

    import agent_redteam.tools.grep as grep_module

    original = grep_module.execute_on_host
    grep_module.execute_on_host = fake_execute_on_host
    try:
        asyncio.run(
            grep_tool(
                _context(tmp_path, settings=_settings(grep_timeout_seconds=90.0)),
                ToolCall(
                    call_id="g-default-timeout",
                    name="grep",
                    arguments={
                        "host": "operator",
                        "pattern": "secret",
                        "path": "/tmp",
                    },
                ),
            )
        )
    finally:
        grep_module.execute_on_host = original

    assert captured == [90.0]


def test_format_grep_result_timeout_message_mentions_retry_and_override() -> None:
    result = CommandResult(exit_code=None, stdout=b"", stderr=b"", timed_out=True)
    output = format_grep_result(result, max_matches=100)

    assert "timed out" in output.lower()
    assert "timeout_seconds" in output


def test_grep_args_rejects_null_on_non_nullable_fields() -> None:
    with pytest.raises(ValidationError):
        GrepArgs.model_validate(
            {
                "host": "operator",
                "pattern": "secret",
                "path": None,
                "glob": None,
                "max_matches": None,
                "ignore_case": None,
                "output_mode": None,
                "timeout_seconds": None,
            }
        )


def test_grep_args_rejects_zero_max_matches() -> None:
    with pytest.raises(ValidationError):
        GrepArgs(
            host="operator",
            pattern="secret",
            max_matches=0,
        )


def test_grep_args_rejects_invalid_timeout() -> None:
    with pytest.raises(ValidationError):
        GrepArgs(
            host="operator",
            pattern="secret",
            timeout_seconds=0,
        )


def test_grep_schema_is_strict_openai_compatible() -> None:
    from agent_redteam.core.config import DEFAULT_GREP_TIMEOUT_SECONDS
    from agent_redteam.tools.grep import DEFAULT_MAX_MATCHES

    schema = grep_definition().input_schema
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(properties.keys())
    assert properties["timeout_seconds"]["default"] == DEFAULT_GREP_TIMEOUT_SECONDS
    assert properties["max_matches"]["default"] == DEFAULT_MAX_MATCHES
    assert properties["ignore_case"]["default"] is False
    assert properties["output_mode"]["default"] == "content"
    assert properties["path"]["default"] is None
    assert "default" not in properties["host"]
    assert "default" not in properties["pattern"]


def test_grep_tool_description_has_usage_without_defaults_section() -> None:
    description = grep_definition().description
    assert "Usage:" in description
    assert "Defaults:" not in description
