import shutil
from pathlib import Path
from typing import Literal

from agent_redteam.core.config import DEFAULT_TRANSFER_TIMEOUT_SECONDS, Settings
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.execution.remote import CommandRunner, run_scp_command
from agent_redteam.execution.result import CommandResult
from agent_redteam.execution.run_on_host import OPERATOR_HOST_ID, _resolve_via_host
from agent_redteam.targets.state import EngagementState
from agent_redteam.targets.topology import Transport

TransferDirection = Literal["download", "upload"]


async def transfer_file_on_host(
    state: EngagementState,
    host_id: str,
    *,
    direction: TransferDirection,
    remote_path: str,
    local_path: Path,
    settings: Settings,
    timeout_seconds: float | None = None,
    max_bytes: int | None = None,
    run_command: CommandRunner | None = None,
) -> tuple[int, EngagementState]:
    host = state.hosts.get(host_id)
    if host is None:
        msg = f"Host {host_id!r} is not in the engagement topology."
        raise ConfigurationError(msg)

    byte_limit = max_bytes if max_bytes is not None else settings.max_transfer_bytes
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else settings.resolved_transfer_timeout_seconds(DEFAULT_TRANSFER_TIMEOUT_SECONDS)
    )

    if host_id == OPERATOR_HOST_ID or host.transport is Transport.LOCAL:
        if direction == "upload":
            _check_upload_size(local_path, byte_limit)
        size = _transfer_local(direction, remote_path=remote_path, local_path=local_path)
        if direction == "download":
            _enforce_download_size_limit(local_path, byte_limit)
        return size, state

    if not host.address:
        msg = f"Host {host_id!r} has no address for remote file transfer."
        raise ConfigurationError(msg)

    if direction == "upload":
        if not local_path.is_file():
            msg = f"Local artifact {local_path!s} does not exist for upload."
            raise ConfigurationError(msg)
        _check_upload_size(local_path, byte_limit)
    elif direction == "download":
        local_path.parent.mkdir(parents=True, exist_ok=True)

    result = await run_scp_command(
        host,
        local_path=str(local_path),
        remote_path=remote_path,
        direction=direction,
        timeout_seconds=timeout,
        resolve_via=lambda via_id: _resolve_via_host(state, via_id),
        run_command=run_command,
    )
    _raise_on_failed_transfer(result)

    if direction == "download":
        if not local_path.is_file():
            msg = f"Download completed but local artifact {local_path!s} was not created."
            raise ConfigurationError(msg)
        size = local_path.stat().st_size
        _enforce_download_size_limit(local_path, byte_limit)
        return size, state

    return local_path.stat().st_size, state


def _transfer_local(
    direction: TransferDirection,
    *,
    remote_path: str,
    local_path: Path,
) -> int:
    if direction == "download":
        source = Path(remote_path)
        if not source.is_file():
            msg = f"Source file {remote_path!r} does not exist on the local host."
            raise ConfigurationError(msg)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, local_path)
        return local_path.stat().st_size

    if not local_path.is_file():
        msg = f"Local artifact {local_path!s} does not exist for upload."
        raise ConfigurationError(msg)
    destination = Path(remote_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local_path, destination)
    return local_path.stat().st_size


def _raise_on_failed_transfer(result: CommandResult) -> None:
    if result.timed_out:
        msg = "File transfer timed out."
        raise ConfigurationError(msg)
    if result.exit_code != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        stdout = result.stdout.decode(errors="replace").strip()
        detail = stderr or stdout or f"exit_code={result.exit_code}"
        msg = f"File transfer failed: {detail}"
        raise ConfigurationError(msg)


def _check_upload_size(path: Path, max_bytes: int) -> None:
    size = path.stat().st_size
    if size > max_bytes:
        msg = f"Upload artifact exceeds max size ({size} bytes > {max_bytes} bytes)."
        raise ConfigurationError(msg)


def _enforce_download_size_limit(path: Path, max_bytes: int) -> None:
    if not path.is_file():
        return
    size = path.stat().st_size
    if size <= max_bytes:
        return
    path.unlink(missing_ok=True)
    msg = (
        f"Downloaded file exceeds max size ({size} bytes > {max_bytes} bytes); removed local copy."
    )
    raise ConfigurationError(msg)
