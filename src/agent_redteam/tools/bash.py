import asyncio
from asyncio.subprocess import PIPE

from pydantic import Field

from agent_redteam.agents.base import AgentContext
from agent_redteam.tools.schemas import ToolArgs, tool_input_schema
from agent_redteam.tools.types import ToolCall, ToolDefinition

DEFAULT_TIMEOUT_SECONDS = 10
MAX_OUTPUT_CHARS = 12_000


class BashArgs(ToolArgs):
    command: str = Field(
        description="Bash command to run in the agent process working directory.",
    )


def bash_definition() -> ToolDefinition:
    return ToolDefinition(
        name="bash",
        description=(
            "Run a bash command in the local agent runtime. Use for authorized, "
            "in-scope inspection or setup commands only."
        ),
        input_schema=tool_input_schema(BashArgs),
        input_model=BashArgs,
        parallel_safe=False,
        mutating=True,
    )


async def bash(_context: AgentContext, tool_call: ToolCall) -> str:
    arguments = BashArgs.model_validate(tool_call.arguments or {})
    command = arguments.command

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
