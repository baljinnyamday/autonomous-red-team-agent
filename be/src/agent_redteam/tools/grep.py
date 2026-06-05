import shlex
from typing import Literal

from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings, get_settings
from agent_redteam.execution.result import CommandResult
from agent_redteam.execution.run_on_host import execute_on_host
from agent_redteam.targets.state import EngagementState
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition

DEFAULT_MAX_MATCHES = 100
DEFAULT_SEARCH_PATH = "."
GrepOutputMode = Literal["content", "files", "count"]

# rg/grep exit 1 = no matches; 141 = SIGPIPE when head closes the pipe early.
_SUCCESS_EXIT_CODES = frozenset({0, 1, 141})


class GrepArgs(ToolArgs):
    host: str = Field(description="Topology host id to search on.")
    pattern: str = Field(description="Regular expression pattern to search for in file contents.")
    path: str | None = Field(
        default=None,
        description=(
            "File or directory to search. Pass null to search from the host working directory."
        ),
    )
    glob: str | None = Field(
        default=None,
        description='Include filter (e.g. "*.conf", "*.{yaml,yml}"). Pass null for all files.',
    )
    max_matches: int | None = Field(
        default=None,
        ge=1,
        le=10000,
        description=(
            "Maximum number of output lines to return (1-10000). "
            "Pass null for the default cap (100)."
        ),
    )
    ignore_case: bool | None = Field(
        default=None,
        description="Case-insensitive search. Pass null for case-sensitive.",
    )
    output_mode: GrepOutputMode | None = Field(
        default=None,
        description=(
            'Output mode: "content" shows matching lines (default), '
            '"files" shows file paths only, "count" shows match counts per file. '
            "Pass null for content mode."
        ),
    )


def grep_definition() -> ToolDefinition:
    return ToolDefinition(
        name="grep",
        description=(
            "Search file contents on an engagement topology host using ripgrep when available, "
            "with a grep -r fallback. Prefer this over hand-rolled find | grep for config and "
            "secret hunting. Returns matching lines (path:line:content), file paths, or counts "
            "depending on output_mode. Use bash to read full files after promising matches."
        ),
        input_schema=tool_input_schema(GrepArgs),
        input_model=GrepArgs,
        parallel_safe=True,
        mutating=False,
    )


async def grep_tool(context: AgentContext, tool_call: ToolCall) -> str:
    arguments = GrepArgs.model_validate(tool_call.arguments or {})
    state = _require_engagement_state(context)
    settings = _settings_from_context(context)

    command = build_grep_command(arguments)
    result, new_state = await execute_on_host(
        state,
        arguments.host,
        command,
        settings,
    )
    context.metadata["engagement_state"] = new_state
    return format_grep_result(result, max_matches=_effective_max_matches(arguments.max_matches))


def build_grep_command(arguments: GrepArgs) -> str:
    search_path = arguments.path or DEFAULT_SEARCH_PATH
    max_matches = _effective_max_matches(arguments.max_matches)
    ignore_case = bool(arguments.ignore_case)
    output_mode = arguments.output_mode or "content"

    quoted_pattern = shlex.quote(arguments.pattern)
    quoted_path = shlex.quote(search_path)
    quoted_max = shlex.quote(str(max_matches))

    rg_mode_flags = _rg_output_flags(output_mode)
    grep_mode_flags = _grep_output_flags(output_mode)
    case_flag = "-i" if ignore_case else ""

    rg_glob = f"--glob {shlex.quote(arguments.glob)}" if arguments.glob else ""
    grep_include = f"--include={shlex.quote(arguments.glob)}" if arguments.glob else ""

    rg_cmd = " ".join(
        part
        for part in (
            "rg",
            "--no-config",
            "--color",
            "never",
            "--hidden",
            "--line-number",
            "--max-columns",
            "500",
            "--glob",
            "'!.git'",
            case_flag,
            rg_glob,
            rg_mode_flags,
            "-e",
            quoted_pattern,
            "--",
            quoted_path,
        )
        if part
    )
    grep_cmd = " ".join(
        part
        for part in (
            "grep",
            "-rnI",
            case_flag,
            grep_include,
            grep_mode_flags,
            "-e",
            quoted_pattern,
            "--",
            quoted_path,
        )
        if part
    )

    return (
        f"set -o pipefail; if command -v rg >/dev/null 2>&1; then {rg_cmd}; "
        f"else {grep_cmd}; fi | head -n {quoted_max}"
    )


def format_grep_result(result: CommandResult, *, max_matches: int) -> str:
    if result.timed_out:
        return "Search timed out. Narrow path, glob, or pattern and retry."

    stdout = _decode(result.stdout)
    stderr = _decode(result.stderr)
    exit_code = result.exit_code

    if exit_code == 1 and not stdout:
        if stderr:
            return f"grep_error: {stderr}"
        return "No matches found"

    if exit_code not in _SUCCESS_EXIT_CODES:
        detail = stderr or stdout or f"Search failed with exit_code={exit_code}."
        return f"grep_error: {detail}"

    if not stdout:
        return "No matches found"

    lines = stdout.splitlines()
    match_count = len(lines)
    header = f"matches: {match_count}"
    if match_count >= max_matches:
        header += f" (truncated at {max_matches} — narrow path, glob, or pattern)"

    body = "\n".join(lines)
    return f"{header}\n{body}"


def _rg_output_flags(output_mode: GrepOutputMode) -> str:
    if output_mode == "files":
        return "-l"
    if output_mode == "count":
        return "-c"
    return ""


def _grep_output_flags(output_mode: GrepOutputMode) -> str:
    if output_mode == "files":
        return "-l"
    if output_mode == "count":
        return "-c"
    return ""


def _effective_max_matches(max_matches: int | None) -> int:
    if max_matches is None:
        return DEFAULT_MAX_MATCHES
    return max_matches


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace").strip()


def _require_engagement_state(context: AgentContext) -> EngagementState:
    raw = context.metadata.get("engagement_state")
    if isinstance(raw, EngagementState):
        return raw
    msg = "engagement_state is missing from agent context metadata."
    raise RuntimeError(msg)


def _settings_from_context(context: AgentContext) -> Settings:
    raw = context.metadata.get("settings")
    if isinstance(raw, Settings):
        return raw
    return get_settings()
