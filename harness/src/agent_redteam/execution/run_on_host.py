from agent_redteam.core.config import Settings
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.execution.local import run_local_command
from agent_redteam.execution.remote import CommandRunner, run_ssh_command
from agent_redteam.execution.result import CommandResult, format_command_result
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.topology import Transport

OPERATOR_HOST_ID = "operator"


async def execute_on_host(
    state: EngagementState,
    host_id: str,
    command: str,
    settings: Settings,
    *,
    timeout_seconds: float | None = None,
    run_command: CommandRunner | None = None,
) -> tuple[CommandResult, EngagementState]:
    host = state.hosts.get(host_id)
    if host is None:
        msg = f"Host {host_id!r} is not in the engagement topology."
        raise ConfigurationError(msg)

    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else settings.effective_exec_timeout_seconds()
    )

    if host_id == OPERATOR_HOST_ID or host.transport is Transport.LOCAL:
        result = await run_local_command(command, timeout_seconds=timeout)
        return result, state

    if not host.address:
        msg = f"Host {host_id!r} has no address for remote SSH execution."
        raise ConfigurationError(msg)

    result = await run_ssh_command(
        host,
        command,
        timeout_seconds=timeout,
        resolve_via=lambda via_id: _resolve_via_host(state, via_id),
        run_command=run_command,
    )
    return result, state


async def run_on_host(
    state: EngagementState,
    host_id: str,
    command: str,
    settings: Settings,
    *,
    timeout_seconds: float | None = None,
    run_command: CommandRunner | None = None,
) -> tuple[str, EngagementState]:
    result, state = await execute_on_host(
        state,
        host_id,
        command,
        settings,
        timeout_seconds=timeout_seconds,
        run_command=run_command,
    )
    return format_command_result(result), state


def _resolve_via_host(state: EngagementState, via_id: str) -> HostRuntime:
    host = state.hosts.get(via_id)
    if host is None:
        msg = f"Jump host {via_id!r} is not in the engagement topology."
        raise ConfigurationError(msg)
    return host
