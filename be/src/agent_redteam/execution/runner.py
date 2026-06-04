import asyncio
import json
import shlex
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable

from agent_redteam.execution.result import CommandResult
from agent_redteam.execution.ssh import build_ssh_command, build_ssh_target
from agent_redteam.targets.state import HostRuntime

HTTP_CLIENT_BUFFER_SECONDS = 30.0
CommandRunner = Callable[[list[str]], Awaitable[int]]


async def post_runner_exec(
    *,
    endpoint: str,
    command: str,
    token: str,
    timeout_seconds: float | None,
    host: HostRuntime | None = None,
    resolve_via: Callable[[str], HostRuntime] | None = None,
    run_command: CommandRunner | None = None,
) -> CommandResult:
    if host is not None and host.address:
        return await _post_runner_exec_via_ssh(
            host=host,
            command=command,
            token=token,
            timeout_seconds=timeout_seconds,
            resolve_via=resolve_via,
            run_command=run_command,
        )

    return _post_runner_exec_http(
        endpoint=endpoint,
        command=command,
        token=token,
        timeout_seconds=timeout_seconds,
    )


def _post_runner_exec_http(
    *,
    endpoint: str,
    command: str,
    token: str,
    timeout_seconds: float | None,
) -> CommandResult:
    url = f"{endpoint.rstrip('/')}/exec"
    body = _exec_request_body(command, timeout_seconds)
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    client_timeout = _http_client_timeout(timeout_seconds)
    with urllib.request.urlopen(request, timeout=client_timeout) as response:
        payload = json.loads(response.read().decode())

    return CommandResult(
        exit_code=payload.get("exit_code"),
        stdout=str(payload.get("stdout", "")).encode(),
        stderr=str(payload.get("stderr", "")).encode(),
        timed_out=bool(payload.get("timed_out", False)),
    )


async def _post_runner_exec_via_ssh(
    *,
    host: HostRuntime,
    command: str,
    token: str,
    timeout_seconds: float | None,
    resolve_via: Callable[[str], HostRuntime] | None,
    run_command: CommandRunner | None,
) -> CommandResult:
    if resolve_via is None or run_command is None:
        msg = "SSH runner exec requires resolve_via and run_command."
        raise RuntimeError(msg)

    via_chain = [resolve_via(via_id) for via_id in host.via]
    target = build_ssh_target(host)
    port = _port_from_endpoint(host.runner_endpoint)
    remote_curl = _remote_curl_exec_command(
        command=command,
        token=token,
        port=port,
        timeout_seconds=timeout_seconds,
    )
    ssh_command = build_ssh_command(
        target=target,
        remote_command=remote_curl,
        via_chain=via_chain,
    )
    client_timeout = _http_client_timeout(timeout_seconds)
    try:
        return await _run_ssh_curl_capture(ssh_command, timeout_seconds=client_timeout)
    except TimeoutError:
        return CommandResult(
            exit_code=None,
            stdout=b"",
            stderr=b"SSH runner exec timed out waiting for curl response.",
            timed_out=True,
        )


async def _run_ssh_curl_capture(
    ssh_command: list[str],
    *,
    timeout_seconds: float | None,
) -> CommandResult:
    process = await asyncio.create_subprocess_exec(
        *ssh_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise

    if process.returncode != 0:
        return CommandResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
        )

    try:
        payload = json.loads(stdout.decode())
    except json.JSONDecodeError:
        return CommandResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr or b"Runner returned non-JSON output from curl.",
            timed_out=False,
        )

    return CommandResult(
        exit_code=payload.get("exit_code"),
        stdout=str(payload.get("stdout", "")).encode(),
        stderr=str(payload.get("stderr", "")).encode(),
        timed_out=bool(payload.get("timed_out", False)),
    )


def runner_health_ok(endpoint: str, *, timeout_seconds: float = 5.0) -> bool:
    url = f"{endpoint.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            return response.status == 200
    except (TimeoutError, urllib.error.URLError, ValueError):
        return False


async def runner_health_ok_via_ssh(
    *,
    host: HostRuntime,
    port: int,
    resolve_via: Callable[[str], HostRuntime],
    run_command: CommandRunner,
) -> bool:
    via_chain = [resolve_via(via_id) for via_id in host.via]
    target = build_ssh_target(host)
    remote_command = f"curl -sfS http://127.0.0.1:{port}/health >/dev/null"
    ssh_command = build_ssh_command(
        target=target,
        remote_command=remote_command,
        via_chain=via_chain,
    )
    try:
        exit_code = await run_command(ssh_command)
    except Exception:
        return False
    return exit_code == 0


def _remote_curl_exec_command(
    *,
    command: str,
    token: str,
    port: int,
    timeout_seconds: float | None,
) -> str:
    body = _exec_request_body(command, timeout_seconds)
    payload = body.decode()
    auth_header = shlex.quote(f"Authorization: Bearer {token}")
    return (
        f"curl -sfS -X POST -H {auth_header} -H 'Content-Type: application/json' "
        f"-d {shlex.quote(payload)} http://127.0.0.1:{port}/exec"
    )


def _exec_request_body(command: str, timeout_seconds: float | None) -> bytes:
    payload: dict[str, object] = {"command": command}
    if timeout_seconds is not None:
        payload["timeout_seconds"] = timeout_seconds
    return json.dumps(payload).encode()


def _http_client_timeout(timeout_seconds: float | None) -> float | None:
    if timeout_seconds is None:
        return None
    return timeout_seconds + HTTP_CLIENT_BUFFER_SECONDS


def _port_from_endpoint(endpoint: str | None) -> int:
    if not endpoint:
        return 8765
    if ":" in endpoint:
        try:
            return int(endpoint.rsplit(":", 1)[-1])
        except ValueError:
            return 8765
    return 8765
