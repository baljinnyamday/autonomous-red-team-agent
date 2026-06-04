import asyncio
from asyncio.subprocess import PIPE

from agent_redteam.execution.result import CommandResult


async def run_local_command(command: str, *, timeout_seconds: float | None) -> CommandResult:
    process = await asyncio.create_subprocess_exec(
        "bash",
        "-lc",
        command,
        stdout=PIPE,
        stderr=PIPE,
    )
    if timeout_seconds is None:
        stdout, stderr = await process.communicate()
        return CommandResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
        )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        return CommandResult(
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
        )

    return CommandResult(
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
    )
