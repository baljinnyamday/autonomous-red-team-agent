from __future__ import annotations

import getpass
import platform
import socket
from dataclasses import dataclass


@dataclass(frozen=True)
class LocalHostProbe:
    hostname: str
    os: str
    arch: str
    user: str


def probe_local_host() -> LocalHostProbe:
    system = platform.system()
    release = platform.release()
    os_name = f"{system} {release}".strip() if release else system
    return LocalHostProbe(
        hostname=socket.gethostname(),
        os=os_name,
        arch=platform.machine(),
        user=getpass.getuser(),
    )
