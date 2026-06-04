import asyncio
import shlex
from collections.abc import Awaitable, Callable
from pathlib import Path

from agent_redteam.core.config import Settings
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.execution.runner import runner_health_ok_via_ssh
from agent_redteam.execution.ssh import build_scp_command, build_ssh_command, build_ssh_target
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.topology import Transport

RunnerArtifactResolver = Callable[[], Path]
CommandRunner = Callable[[list[str]], Awaitable[int]]


def default_runner_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "runner"


def default_runner_artifact_path() -> Path:
    return default_runner_dir() / "server.py"


def loopback_runner_endpoint(port: int) -> str:
    return f"http://127.0.0.1:{port}"


async def bootstrap_runner(
    *,
    host_id: str,
    host: HostRuntime,
    state: EngagementState,
    settings: Settings,
    resolve_via: Callable[[str], HostRuntime],
    run_command: CommandRunner | None = None,
    artifact_path: Path | None = None,
) -> tuple[str, EngagementState]:
    if host.transport is not Transport.SSH_PENDING:
        msg = f"Host {host_id!r} is not ssh_pending."
        raise ConfigurationError(msg)

    runner_dir = artifact_path.parent if artifact_path else default_runner_dir()
    server_file = artifact_path or default_runner_artifact_path()
    policy_file = runner_dir / "policy.py"
    if not server_file.exists() or not policy_file.exists():
        msg = f"Runner artifacts not found under {runner_dir}"
        raise ConfigurationError(msg)

    via_chain = [resolve_via(via_id) for via_id in host.via]
    target = build_ssh_target(host)
    remote_dir = f"/tmp/agent-runner-{host_id}"
    remote_script = f"{remote_dir}/server.py"
    remote_policy = f"{remote_dir}/policy.py"
    remote_log = f"{remote_dir}/runner.log"
    remote_token_file = f"{remote_dir}/.runner_token"
    port = settings.runner_port

    commands = [
        build_ssh_command(
            target=target,
            remote_command=f"mkdir -p {shlex.quote(remote_dir)}",
            via_chain=via_chain,
        ),
        build_scp_command(
            local_path=str(server_file),
            remote_path=remote_script,
            target=target,
            via_chain=via_chain,
        ),
        build_scp_command(
            local_path=str(policy_file),
            remote_path=remote_policy,
            target=target,
            via_chain=via_chain,
        ),
        build_ssh_command(
            target=target,
            remote_command=_remote_write_token_command(
                token_path=remote_token_file,
                settings=settings,
            ),
            via_chain=via_chain,
        ),
        build_ssh_command(
            target=target,
            remote_command=_remote_start_command(
                remote_dir=remote_dir,
                remote_script=remote_script,
                remote_log=remote_log,
                token_file=remote_token_file,
                port=port,
            ),
            via_chain=via_chain,
        ),
    ]

    runner = run_command or _default_run_command
    for command in commands:
        exit_code = await _await_command(runner, command)
        if exit_code != 0:
            msg = f"Bootstrap failed for {host_id!r} (exit {exit_code})."
            raise ConfigurationError(msg)

    endpoint = loopback_runner_endpoint(port)
    if not await runner_health_ok_via_ssh(
        host=host,
        port=port,
        resolve_via=resolve_via,
        run_command=runner,
    ):
        msg = (
            f"Runner health check failed for {host_id!r} on loopback port {port}. "
            "Check SSH reachability and jump configuration."
        )
        raise ConfigurationError(msg)

    return endpoint, state.set_runner(host_id, endpoint)


def _remote_write_token_command(*, token_path: str, settings: Settings) -> str:
    token = settings.require_runner_token()
    quoted_path = shlex.quote(token_path)
    return (
        f"umask 077 && printf '%s' {shlex.quote(token)} > {quoted_path} "
        f"&& chmod 600 {quoted_path}"
    )


def _remote_start_command(
    *,
    remote_dir: str,
    remote_script: str,
    remote_log: str,
    token_file: str,
    port: int,
) -> str:
    env = (
        f"RUNNER_TOKEN_FILE={shlex.quote(token_file)} "
        f"RUNNER_PORT={port} "
        f"RUNNER_BIND=127.0.0.1"
    )
    return (
        f"nohup env {env} sh -c 'cd {shlex.quote(remote_dir)} && "
        f"python3 {shlex.quote(Path(remote_script).name)}' "
        f"> {shlex.quote(remote_log)} 2>&1 </dev/null &"
    )


async def _default_run_command(command: list[str]) -> int:
    process = await asyncio.create_subprocess_exec(*command)
    return await process.wait()


async def _await_command(runner: CommandRunner, command: list[str]) -> int:
    return await runner(command)
