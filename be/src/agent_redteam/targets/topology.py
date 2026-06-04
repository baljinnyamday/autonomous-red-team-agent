from enum import StrEnum

from pydantic import BaseModel, Field


class Transport(StrEnum):
    LOCAL = "local"
    SSH_PENDING = "ssh_pending"
    RUNNER = "runner"


class HostSeed(BaseModel):
    id: str
    transport: Transport
    address: str | None = None
    user: str | None = None
    via: list[str] = Field(default_factory=list)
    runner_endpoint: str | None = None


class EngagementTopology(BaseModel):
    engagement_id: str | None = None
    hosts: list[HostSeed] = Field(default_factory=list)
    notes: str | None = None

    def host_by_id(self, host_id: str) -> HostSeed | None:
        for host in self.hosts:
            if host.id == host_id:
                return host
        return None
