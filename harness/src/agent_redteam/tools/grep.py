import shlex
from typing import Literal

from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import DEFAULT_GREP_TIMEOUT_SECONDS, Settings, get_settings
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
    pattern: str = Field(
        description='Regular expression pattern (ripgrep/grep -E syntax, e.g. "password|token").',
    )
    path: str | None = Field(
        default=None,
        description="File or directory to search (maps to rg PATH).",
    )
    glob: str | None = Field(
        default=None,
        description='Include filter (e.g. "*.conf", "*.{yaml,yml}"). Maps to rg --glob.',
    )
    max_matches: int = Field(
        default=DEFAULT_MAX_MATCHES,
        ge=1,
        le=10000,
        description="Maximum output lines to return (1-10000).",
    )
    ignore_case: bool = Field(
        default=False,
        description="Case-insensitive search (-i).",
    )
    output_mode: GrepOutputMode = Field(
        default="content",
        description='"content" | "files" | "count".',
    )
    timeout_seconds: float = Field(
        default=DEFAULT_GREP_TIMEOUT_SECONDS,
        ge=1,
        le=3600,
        description="Wall-clock limit in seconds (1-3600).",
    )


def grep_definition() -> ToolDefinition:
    return ToolDefinition(
        name="grep",
        description=(
            "Search file contents on an engagement topology host. Uses ripgrep when "
            "available, otherwise grep -rE.\n\n"
            "Usage:\n"
            "- ALWAYS use grep for regex content search. NEVER invoke grep or rg via bash.\n"
            '- Supports full regex syntax (e.g. "secret|password", "flag\\\\{[^}]+\\\\}").\n'
            '- Filter files with glob (e.g. "*.conf", "*.{yaml,yml}").\n'
            "- output_mode content returns path:line:match; files returns paths only; "
            "count returns per-file totals.\n"
            "- Use bash to read full files after promising matches.\n"
            "- Narrow path and glob before searching large trees (e.g. entire $HOME)."
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
    timeout = settings.resolved_grep_timeout_seconds(arguments.timeout_seconds)
    result, new_state = await execute_on_host(
        state,
        arguments.host,
        command,
        settings,
        timeout_seconds=timeout,
    )
    context.metadata["engagement_state"] = new_state
    return format_grep_result(result, max_matches=arguments.max_matches)


def build_grep_command(arguments: GrepArgs) -> str:
    search_path = arguments.path or DEFAULT_SEARCH_PATH
    ignore_case = arguments.ignore_case
    output_mode = arguments.output_mode

    quoted_pattern = shlex.quote(arguments.pattern)
    quoted_path = shlex.quote(search_path)
    quoted_max = shlex.quote(str(arguments.max_matches))

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
            "-rnIE",
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
        return (
            "Search timed out. Narrow path, glob, or pattern and retry, "
            "or increase timeout_seconds if the scope is intentional."
        )

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
