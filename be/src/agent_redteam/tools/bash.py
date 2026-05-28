import asyncio
import shlex
from asyncio.subprocess import PIPE

from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition

DEFAULT_TIMEOUT_SECONDS = 10
MAX_OUTPUT_CHARS = 12_000
POLICY_DENIED_EXIT_CODE = 126
RM_COMMAND_WARNING = "Command blocked: the 'rm' command is not allowed through the bash tool."
SHELL_SEPARATORS = {";", "&&", "||", "|", "(", ")"}
SHELL_COMMAND_WRAPPERS = {"command", "exec", "nohup", "time"}
SHELLS_WITH_COMMAND_ARG = {"bash", "sh", "zsh"}


class BashArgs(ToolArgs):
    command: str = Field(
        description="Bash command to run in the agent process working directory.",
    )


def bash_definition() -> ToolDefinition:
    return ToolDefinition(
        name="bash",
        description=(
            "Run a bash command in the local agent runtime. Use for authorized, "
            "in-scope inspection or setup commands only. The rm command is not allowed."
        ),
        input_schema=tool_input_schema(BashArgs),
        input_model=BashArgs,
        parallel_safe=False,
        mutating=True,
    )


async def bash(_context: AgentContext, tool_call: ToolCall) -> str:
    arguments = BashArgs.model_validate(tool_call.arguments or {})
    command = arguments.command
    if _contains_rm_command(command):
        return _format_result(
            exit_code=POLICY_DENIED_EXIT_CODE,
            stdout=b"",
            stderr=RM_COMMAND_WARNING.encode(),
            timed_out=False,
        )

    process = await asyncio.create_subprocess_exec(
        "bash",
        "-lc",
        command,
        stdout=PIPE,
        stderr=PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        return _format_result(
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
        )

    return _format_result(
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
    )


def _contains_rm_command(command: str) -> bool:
    tokens = _shell_tokens(command)
    index = 0
    expect_command = True

    while index < len(tokens):
        token = tokens[index]
        if token in SHELL_SEPARATORS:
            expect_command = True
            index += 1
            continue

        if token in {"-exec", "-execdir"} and _next_token_is_rm(tokens, index):
            return True

        if not expect_command:
            index += 1
            continue

        if _is_assignment(token):
            index += 1
            continue

        command_name = _command_name(token)
        if command_name == "rm":
            return True

        wrapper_index = _wrapped_command_index(tokens, index, command_name)
        if wrapper_index != index:
            index = wrapper_index
            continue

        nested_command = _nested_shell_command(tokens, index, command_name)
        if nested_command is not None and _contains_rm_command(nested_command):
            return True

        expect_command = False
        index += 1

    return False


def _shell_tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return command.split()


def _next_token_is_rm(tokens: list[str], index: int) -> bool:
    return index + 1 < len(tokens) and _command_name(tokens[index + 1]) == "rm"


def _command_name(token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _is_assignment(token: str) -> bool:
    name, separator, _ = token.partition("=")
    return (
        bool(separator) and bool(name) and name.replace("_", "").isalnum() and not name[0].isdigit()
    )


def _wrapped_command_index(tokens: list[str], index: int, command_name: str) -> int:
    if command_name in SHELL_COMMAND_WRAPPERS:
        return index + 1
    if command_name == "sudo":
        return _skip_sudo_options(tokens, index + 1)
    if command_name == "env":
        return _skip_env_prefix(tokens, index + 1)
    return index


def _skip_sudo_options(tokens: list[str], index: int) -> int:
    options_with_value = {"-C", "-g", "-h", "-p", "-T", "-t", "-U", "-u"}
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if not token.startswith("-"):
            return index
        index += 2 if token in options_with_value else 1
    return index


def _skip_env_prefix(tokens: list[str], index: int) -> int:
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if token.startswith("-") or _is_assignment(token):
            index += 1
            continue
        return index
    return index


def _nested_shell_command(tokens: list[str], index: int, command_name: str) -> str | None:
    if command_name not in SHELLS_WITH_COMMAND_ARG:
        return None

    for token_index in range(index + 1, len(tokens) - 1):
        token = tokens[token_index]
        if token in SHELL_SEPARATORS:
            return None
        if token.startswith("-") and "c" in token:
            return tokens[token_index + 1]
    return None


def _format_result(
    *,
    exit_code: int | None,
    stdout: bytes,
    stderr: bytes,
    timed_out: bool,
) -> str:
    output = "\n".join(
        [
            f"exit_code={exit_code}",
            f"timed_out={str(timed_out).lower()}",
            "stdout:",
            _decode(stdout),
            "stderr:",
            _decode(stderr),
        ]
    )
    if len(output) <= MAX_OUTPUT_CHARS:
        return output
    return output[:MAX_OUTPUT_CHARS] + "\n...[truncated]"


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace").strip()
