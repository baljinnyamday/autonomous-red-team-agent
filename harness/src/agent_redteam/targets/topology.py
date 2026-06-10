from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

_LEGACY_REMOTE_TRANSPORTS = frozenset({"ssh_pending", "runner"})


class Transport(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"


def normalize_transport_value(value: str) -> str:
    if value in _LEGACY_REMOTE_TRANSPORTS:
        return Transport.REMOTE.value
    return value


class ServiceFinding(BaseModel):
    port: int | None = None
    protocol: str | None = None
    product: str | None = None
    url: str | None = None
    notes: str | None = None


class CredentialFinding(BaseModel):
    username: str | None = None
    secret: str | None = None
    type: str | None = Field(
        default=None,
        description=(
            "Credential type. For SSH private key files, use ssh_key_file or identity-file "
            "with secret set to the key path."
        ),
    )
    source: str | None = None
    notes: str | None = None


class HostSeed(BaseModel):
    id: str
    transport: Transport
    address: str | None = None
    user: str | None = None
    via: list[str] = Field(default_factory=list)
    discovered_from: str | None = None
    os: str | None = None
    hostname: str | None = None
    arch: str | None = None
    tags: list[str] = Field(default_factory=list)
    services: list[ServiceFinding] = Field(default_factory=list)
    credentials: list[CredentialFinding] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("transport", mode="before")
    @classmethod
    def _normalize_legacy_transport(cls, value: object) -> object:
        if isinstance(value, str) and value in _LEGACY_REMOTE_TRANSPORTS:
            return Transport.REMOTE
        return value


class EngagementTopology(BaseModel):
    engagement_id: str | None = None
    hosts: list[HostSeed] = Field(default_factory=list)
    notes: str | None = None

    def host_by_id(self, host_id: str) -> HostSeed | None:
        for host in self.hosts:
            if host.id == host_id:
                return host
        return None
