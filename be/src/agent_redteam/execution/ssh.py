import shlex

from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.targets.state import HostRuntime


def build_ssh_target(host: HostRuntime) -> str:
    if not host.address:
        msg = "ssh_pending host is missing address."
        raise ConfigurationError(msg)
    user = host.user or "root"
    return f"{user}@{host.address}"


def build_ssh_command(
    *,
    target: str,
    remote_command: str,
    via_chain: list[HostRuntime],
) -> list[str]:
    ssh_args = ["ssh", "-o", "BatchMode=yes"]
    if via_chain:
        proxy = _proxy_command_for_chain(via_chain)
        ssh_args.extend(["-o", f"ProxyCommand={proxy}"])
    ssh_args.extend([target, remote_command])
    return ssh_args


def build_scp_command(
    *,
    local_path: str,
    remote_path: str,
    target: str,
    via_chain: list[HostRuntime],
) -> list[str]:
    scp_args = ["scp", "-o", "BatchMode=yes"]
    if via_chain:
        proxy = _proxy_command_for_chain(via_chain)
        scp_args.extend(["-o", f"ProxyCommand={proxy}"])
    scp_args.extend([local_path, f"{target}:{remote_path}"])
    return scp_args


def _proxy_command_for_chain(via_chain: list[HostRuntime]) -> str:
    if len(via_chain) != 1:
        msg = "Phase 1 bootstrap supports a single jump host in via."
        raise ConfigurationError(msg)
    jump = via_chain[0]
    jump_target = build_ssh_target(jump)
    return f"ssh -o BatchMode=yes -W %h:%p {shlex.quote(jump_target)}"
