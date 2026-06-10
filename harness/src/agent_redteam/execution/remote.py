import asyncio
from asyncio.subprocess import PIPE
from collections.abc import Callable
from typing import Protocol

from agent_redteam.execution.result import CommandResult
from agent_redteam.execution.ssh import (
    TransferDirection,
    build_remote_bash_command,
    build_scp_command,
    build_ssh_command,
    build_ssh_target,
    ssh_identity_file,
)
from agent_redteam.targets.state import HostRuntime


class CommandRunner(Protocol):
    async def __call__(
        self,
        command: list[str],
        *,
        timeout_seconds: float | None,
    ) -> CommandResult: ...


async def run_ssh_command(
    host: HostRuntime,
    command: str,
    *,
    timeout_seconds: float | None,
    resolve_via: Callable[[str], HostRuntime],
    run_command: CommandRunner | None = None,
) -> CommandResult:
    via_chain = [resolve_via(via_id) for via_id in host.via]
    target = build_ssh_target(host)
    remote_command = build_remote_bash_command(command)
    ssh_command = build_ssh_command(
        target=target,
        remote_command=remote_command,
        via_chain=via_chain,
        identity_file=ssh_identity_file(host),
    )
    runner = run_command or _default_run_command
    return await runner(ssh_command, timeout_seconds=timeout_seconds)


async def run_scp_command(
    host: HostRuntime,
    *,
    local_path: str,
    remote_path: str,
    direction: TransferDirection,
    timeout_seconds: float | None,
    resolve_via: Callable[[str], HostRuntime],
    run_command: CommandRunner | None = None,
) -> CommandResult:
    via_chain = [resolve_via(via_id) for via_id in host.via]
    target = build_ssh_target(host)
    scp_command = build_scp_command(
        local_path=local_path,
        remote_path=remote_path,
        target=target,
        via_chain=via_chain,
        identity_file=ssh_identity_file(host),
        direction=direction,
    )
    runner = run_command or _default_run_command
    return await runner(scp_command, timeout_seconds=timeout_seconds)


async def _default_run_command(
    command: list[str],
    *,
    timeout_seconds: float | None,
) -> CommandResult:
    process = await asyncio.create_subprocess_exec(
        *command,
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
