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
    return Settings(
        _env_file=None,
        bash_timeout_seconds=None,
        **overrides,
    )


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
    assert "grep -rnI" in command
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
            glob=None,
            max_matches=None,
            ignore_case=None,
            output_mode=None,
        )
    )

    assert "'/tmp/my dir'" in command
    assert "it's a $secret" in command or "it'" in command


def test_build_grep_command_files_and_count_modes() -> None:
    files_cmd = build_grep_command(
        GrepArgs(
            host="operator",
            pattern="password",
            path=None,
            glob=None,
            max_matches=None,
            ignore_case=None,
            output_mode="files",
        )
    )
    count_cmd = build_grep_command(
        GrepArgs(
            host="operator",
            pattern="password",
            path=None,
            glob=None,
            max_matches=None,
            ignore_case=None,
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
                    "glob": None,
                    "max_matches": None,
                    "ignore_case": None,
                    "output_mode": None,
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
                    "glob": None,
                    "max_matches": None,
                    "ignore_case": None,
                    "output_mode": None,
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
                    "max_matches": None,
                    "ignore_case": None,
                    "output_mode": None,
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
                    "glob": None,
                    "max_matches": None,
                    "ignore_case": None,
                    "output_mode": "files",
                },
            ),
        )
    )

    assert output.startswith("matches:")
    assert "one.conf" in output
    assert "two.conf" in output
    assert "secret=1" not in output


def test_grep_args_rejects_zero_max_matches() -> None:
    with pytest.raises(ValidationError):
        GrepArgs(
            host="operator",
            pattern="secret",
            path=None,
            glob=None,
            max_matches=0,
            ignore_case=None,
            output_mode=None,
        )


def test_grep_schema_is_strict_openai_compatible() -> None:
    schema = grep_definition().input_schema
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(properties.keys())
    for prop_schema in properties.values():
        assert "default" not in prop_schema
