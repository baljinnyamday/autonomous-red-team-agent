from collections.abc import Awaitable, Callable

from agent_redteam.core.config import Settings
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.execution.bootstrap import bootstrap_runner
from agent_redteam.execution.local import run_local_command
from agent_redteam.execution.policy import (
    RM_COMMAND_WARNING,
    SSH_COMMAND_WARNING,
    contains_rm_command,
    contains_ssh_command,
)
from agent_redteam.execution.result import format_command_result, policy_denied
from agent_redteam.execution.runner import post_runner_exec
from agent_redteam.targets.scope import TargetScope
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.topology import Transport

BootstrapRunnerFn = Callable[..., Awaitable[tuple[str, EngagementState]]]
CommandRunner = Callable[[list[str]], Awaitable[int]]


async def run_on_host(
    state: EngagementState,
    host_id: str,
    command: str,
    settings: Settings,
    *,
    scope: TargetScope | None = None,
    bootstrap_runner_fn: BootstrapRunnerFn | None = None,
    run_command: CommandRunner | None = None,
) -> tuple[str, EngagementState]:
    state.validate_host_in_scope(host_id, scope)

    if contains_rm_command(command):
        return format_command_result(policy_denied(RM_COMMAND_WARNING)), state
    if contains_ssh_command(command):
        return format_command_result(policy_denied(SSH_COMMAND_WARNING)), state

    host = state.hosts[host_id]
    timeout = settings.effective_exec_timeout_seconds()

    if host.transport is Transport.LOCAL:
        result = await run_local_command(command, timeout_seconds=timeout)
        return format_command_result(result), state

    if host.transport is Transport.SSH_PENDING:
        bootstrap = bootstrap_runner_fn or bootstrap_runner
        endpoint, state = await bootstrap(
            host_id=host_id,
            host=host,
            state=state,
            settings=settings,
            resolve_via=lambda via_id: state.hosts[via_id],
            run_command=run_command,
        )
        host = state.hosts[host_id]
        prefix, state = _runner_ready_notice(host_id, endpoint, state)
        output, state = await _run_via_runner(
            host=host,
            command=command,
            settings=settings,
            timeout=timeout,
            state=state,
            host_id=host_id,
            resolve_via=lambda via_id: state.hosts[via_id],
            run_command=run_command,
        )
        return prefix + output, state

    if host.transport is Transport.RUNNER:
        endpoint = host.runner_endpoint or ""
        prefix, state = _runner_ready_notice(host_id, endpoint, state)
        output, state = await _run_via_runner(
            host=host,
            command=command,
            settings=settings,
            timeout=timeout,
            state=state,
            host_id=host_id,
            resolve_via=lambda via_id: state.hosts[via_id],
            run_command=run_command,
        )
        return prefix + output, state

    msg = f"Unsupported transport for host {host_id!r}: {host.transport}"
    raise ConfigurationError(msg)


async def _run_via_runner(
    *,
    host: HostRuntime,
    command: str,
    settings: Settings,
    timeout: float | None,
    state: EngagementState,
    host_id: str,
    resolve_via: Callable[[str], HostRuntime],
    run_command: CommandRunner | None,
) -> tuple[str, EngagementState]:
    endpoint = host.runner_endpoint
    if not endpoint:
        msg = f"Host {host_id!r} has no runner endpoint."
        raise ConfigurationError(msg)

    token = settings.require_runner_token()
    result = await post_runner_exec(
        endpoint=endpoint,
        command=command,
        token=token,
        timeout_seconds=timeout,
        host=host,
        resolve_via=resolve_via,
        run_command=run_command,
    )
    return format_command_result(result), state


def _runner_ready_notice(
    host_id: str,
    endpoint: str,
    state: EngagementState,
) -> tuple[str, EngagementState]:
    host = state.hosts[host_id]
    if host.runner_ready_announced:
        return "", state
    updated = state.mark_runner_announced(host_id)
    return f"runner_ready: {host_id} ({endpoint})\n", updated
