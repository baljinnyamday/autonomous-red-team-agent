import shlex
from pathlib import Path

from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.targets.state import HostRuntime

SSH_IDENTITY_FILE_TYPES = frozenset(
    {
        "identity-file",
        "ssh_identity_file_path",
        "ssh_key_file",
    }
)


def build_ssh_target(host: HostRuntime) -> str:
    if not host.address:
        msg = "Remote host is missing address."
        raise ConfigurationError(msg)
    user = host.user or "root"
    return f"{user}@{host.address}"


def ssh_identity_file(host: HostRuntime) -> str | None:
    candidates: list[str] = []
    for credential in host.credentials:
        if not credential.secret or credential.type not in SSH_IDENTITY_FILE_TYPES:
            continue
        candidates.append(str(Path(credential.secret).expanduser()))
    if not candidates:
        return None
    absolute = [path for path in candidates if path.startswith("/")]
    return absolute[-1] if absolute else candidates[-1]


def build_ssh_command(
    *,
    target: str,
    remote_command: str,
    via_chain: list[HostRuntime],
    identity_file: str | None = None,
) -> list[str]:
    ssh_args = ["ssh", "-o", "BatchMode=yes"]
    if identity_file:
        ssh_args.extend(["-i", identity_file])
    if via_chain:
        proxy = _proxy_command_for_chain(via_chain)
        ssh_args.extend(["-o", f"ProxyCommand={proxy}"])
    ssh_args.extend([target, remote_command])
    return ssh_args


def build_remote_bash_command(command: str) -> str:
    return f"bash -lc {shlex.quote(command)}"


def build_scp_command(
    *,
    local_path: str,
    remote_path: str,
    target: str,
    via_chain: list[HostRuntime],
    identity_file: str | None = None,
) -> list[str]:
    scp_args = ["scp", "-o", "BatchMode=yes"]
    if identity_file:
        scp_args.extend(["-i", identity_file])
    if via_chain:
        proxy = _proxy_command_for_chain(via_chain)
        scp_args.extend(["-o", f"ProxyCommand={proxy}"])
    scp_args.extend([local_path, f"{target}:{remote_path}"])
    return scp_args


def _proxy_command_for_chain(via_chain: list[HostRuntime]) -> str:
    if len(via_chain) != 1:
        msg = "SSH proxy supports a single jump host in via."
        raise ConfigurationError(msg)
    jump = via_chain[0]
    jump_target = build_ssh_target(jump)
    jump_identity = ssh_identity_file(jump)
    identity_arg = f"-i {shlex.quote(jump_identity)} " if jump_identity else ""
    return f"ssh -o BatchMode=yes {identity_arg}-W %h:%p {shlex.quote(jump_target)}"
