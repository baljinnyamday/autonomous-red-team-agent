from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel, Field

from agent_redteam.core.config import Settings
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.targets.topology import (
    CredentialFinding,
    EngagementTopology,
    ServiceFinding,
    Transport,
)

if TYPE_CHECKING:
    from agent_redteam.targets.store import EngagementStore

_SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


class HostRuntime(BaseModel):
    transport: Transport
    address: str | None = None
    user: str | None = None
    via: list[str] = Field(default_factory=list)
    os: str | None = None
    hostname: str | None = None
    arch: str | None = None
    tags: list[str] = Field(default_factory=list)
    services: list[ServiceFinding] = Field(default_factory=list)
    credentials: list[CredentialFinding] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class EngagementState(BaseModel):
    engagement_id: str
    hosts: dict[str, HostRuntime] = Field(default_factory=dict)
    notes: str | None = None

    @classmethod
    def from_topology(cls, topology: EngagementTopology, *, engagement_id: str) -> EngagementState:
        hosts = {
            seed.id: HostRuntime(
                transport=seed.transport,
                address=seed.address,
                user=seed.user,
                via=list(seed.via),
                os=seed.os,
                hostname=seed.hostname,
                arch=seed.arch,
                tags=list(seed.tags),
                services=list(seed.services),
                credentials=list(seed.credentials),
                notes=list(seed.notes),
            )
            for seed in topology.hosts
        }
        return cls(
            engagement_id=engagement_id,
            hosts=hosts,
            notes=topology.notes,
        )

    def topology_prompt_block(self) -> str:
        lines = [f"engagement_id: {self.engagement_id}"]
        if self.notes:
            lines.append(f"notes: {self.notes}")
        lines.append("hosts:")
        for host_id, host in sorted(self.hosts.items()):
            endpoint = host.address or "(local)"
            via = f" via={','.join(host.via)}" if host.via else ""
            extras: list[str] = []
            if host.tags:
                extras.append(f"tags={','.join(host.tags)}")
            if host.services:
                extras.append(f"services={len(host.services)}")
            if host.credentials:
                extras.append(f"creds={len(host.credentials)}")
            if host.os:
                extras.append(f"os={host.os}")
            extra = f" {' '.join(extras)}" if extras else ""
            lines.append(
                f"  - {host_id}: transport={host.transport.value} endpoint={endpoint}{via}{extra}"
            )
        return "\n".join(lines)

    def topology_report(self, *, host_id: str | None = None) -> str:
        host_ids = [host_id] if host_id else sorted(self.hosts)
        if host_id and host_id not in self.hosts:
            msg = f"Unknown host {host_id!r}. Use a host id from the engagement topology."
            raise ConfigurationError(msg)

        lines = [f"engagement_id: {self.engagement_id}"]
        if self.notes:
            lines.append(f"notes: {self.notes}")
        lines.append("hosts:")
        for current_id in host_ids:
            host = self.hosts[current_id]
            endpoint = host.address or "(local)"
            lines.append(f"  {current_id}:")
            lines.append(f"    transport: {host.transport.value}")
            lines.append(f"    endpoint: {endpoint}")
            if host.user:
                lines.append(f"    user: {host.user}")
            if host.via:
                lines.append(f"    via: {','.join(host.via)}")
            if host.os:
                lines.append(f"    os: {host.os}")
            if host.hostname:
                lines.append(f"    hostname: {host.hostname}")
            if host.arch:
                lines.append(f"    arch: {host.arch}")
            if host.tags:
                lines.append(f"    tags: {', '.join(host.tags)}")
            for service in host.services:
                parts = [
                    part
                    for part in (
                        f"port={service.port}" if service.port is not None else None,
                        f"protocol={service.protocol}" if service.protocol else None,
                        f"product={service.product}" if service.product else None,
                        f"url={service.url}" if service.url else None,
                        f"notes={service.notes}" if service.notes else None,
                    )
                    if part
                ]
                lines.append(f"    service: {' '.join(parts)}")
            for credential in host.credentials:
                parts = [
                    part
                    for part in (
                        f"username={credential.username}" if credential.username else None,
                        f"secret={credential.secret}" if credential.secret else None,
                        f"type={credential.type}" if credential.type else None,
                        f"source={credential.source}" if credential.source else None,
                        f"notes={credential.notes}" if credential.notes else None,
                    )
                    if part
                ]
                lines.append(f"    credential: {' '.join(parts)}")
            for note in host.notes:
                lines.append(f"    note: {note}")
        return "\n".join(lines)

    def _require_host(self, host_id: str) -> HostRuntime:
        host = self.hosts.get(host_id)
        if host is None:
            msg = f"Unknown host {host_id!r}. Use a host id from the engagement topology."
            raise ConfigurationError(msg)
        return host


def load_topology_yaml(path: Path) -> EngagementTopology:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"Invalid topology YAML at {path}: expected a mapping."
        raise ConfigurationError(msg)
    return EngagementTopology.model_validate(raw)


def default_db_path(settings: Settings) -> Path:
    if settings.engagement_db_path:
        return Path(settings.engagement_db_path)
    audit_path = Path(settings.audit_log_path)
    audit_root = audit_path.parent if audit_path.suffix else audit_path
    safe_id = settings.engagement_id
    if _SAFE_ID_PATTERN.fullmatch(safe_id):
        return audit_root / f"engagement-{safe_id}.db"
    return audit_root / "engagement.db"


def load_engagement_state(settings: Settings) -> tuple[EngagementState, EngagementStore]:
    from agent_redteam.targets.store import EngagementStore

    engagement_id = settings.engagement_id
    store = EngagementStore.connect(default_db_path(settings))
    effective_id = engagement_id
    topology_notes: str | None = None

    if settings.engagement_topology_path:
        topology = load_topology_yaml(Path(settings.engagement_topology_path))
        effective_id = topology.engagement_id or engagement_id
        topology_notes = topology.notes
        store.seed_from_topology(topology, engagement_id=effective_id)

    store.ensure_local_host(effective_id)
    state = store.load_state(effective_id)
    if topology_notes:
        state = state.model_copy(update={"notes": topology_notes or state.notes})
    return state, store
