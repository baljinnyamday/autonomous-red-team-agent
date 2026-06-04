from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from agent_redteam.core.config import Settings
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.targets.scope import TargetScope
from agent_redteam.targets.topology import EngagementTopology, Transport

_SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


class HostRuntime(BaseModel):
    transport: Transport
    address: str | None = None
    user: str | None = None
    via: list[str] = Field(default_factory=list)
    runner_endpoint: str | None = None
    runner_ready_announced: bool = False


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
                runner_endpoint=seed.runner_endpoint,
            )
            for seed in topology.hosts
        }
        return cls(
            engagement_id=engagement_id,
            hosts=hosts,
            notes=topology.notes,
        )

    @classmethod
    def load(cls, path: Path) -> EngagementState:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def merge_runtime(self, other: EngagementState) -> EngagementState:
        if other.engagement_id != self.engagement_id:
            return self

        merged_hosts = dict(self.hosts)
        for host_id, persisted in other.hosts.items():
            if host_id not in merged_hosts:
                continue
            merged_hosts[host_id] = _merge_host_runtime(merged_hosts[host_id], persisted)
        return self.model_copy(update={"hosts": merged_hosts})

    def persist(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def set_runner(self, host_id: str, endpoint: str) -> EngagementState:
        host = self._require_host(host_id)
        updated = host.model_copy(
            update={
                "transport": Transport.RUNNER,
                "runner_endpoint": endpoint.rstrip("/"),
            }
        )
        hosts = dict(self.hosts)
        hosts[host_id] = updated
        return self.model_copy(update={"hosts": hosts})

    def mark_runner_announced(self, host_id: str) -> EngagementState:
        host = self._require_host(host_id)
        hosts = dict(self.hosts)
        hosts[host_id] = host.model_copy(update={"runner_ready_announced": True})
        return self.model_copy(update={"hosts": hosts})

    def validate_host_in_scope(self, host_id: str, scope: TargetScope | None) -> None:
        self._require_host(host_id)
        if scope is not None and scope.hosts and host_id not in scope.hosts:
            msg = f"Host {host_id!r} is not in the authorized target scope."
            raise ConfigurationError(msg)

    def topology_prompt_block(self) -> str:
        lines = [f"engagement_id: {self.engagement_id}"]
        if self.notes:
            lines.append(f"notes: {self.notes}")
        lines.append("hosts:")
        for host_id, host in sorted(self.hosts.items()):
            endpoint = (
                host.runner_endpoint
                if host.transport is Transport.RUNNER
                else host.address or "(local)"
            )
            via = f" via={','.join(host.via)}" if host.via else ""
            lines.append(
                f"  - {host_id}: transport={host.transport.value} endpoint={endpoint}{via}"
            )
        return "\n".join(lines)

    def _require_host(self, host_id: str) -> HostRuntime:
        host = self.hosts.get(host_id)
        if host is None:
            msg = f"Unknown host {host_id!r}. Use a host id from the engagement topology."
            raise ConfigurationError(msg)
        return host


def _merge_host_runtime(seed: HostRuntime, persisted: HostRuntime) -> HostRuntime:
    if persisted.transport is Transport.RUNNER and persisted.runner_endpoint:
        return seed.model_copy(
            update={
                "transport": Transport.RUNNER,
                "runner_endpoint": persisted.runner_endpoint,
                "runner_ready_announced": persisted.runner_ready_announced,
            }
        )
    return seed


def load_topology_yaml(path: Path) -> EngagementTopology:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"Invalid topology YAML at {path}: expected a mapping."
        raise ConfigurationError(msg)
    return EngagementTopology.model_validate(raw)


def default_state_path(settings: Settings) -> Path:
    if settings.engagement_state_path:
        return Path(settings.engagement_state_path)
    audit_parent = Path(settings.audit_log_path).parent
    safe_id = settings.engagement_id
    if _SAFE_ID_PATTERN.fullmatch(safe_id):
        return audit_parent / f"engagement-state-{safe_id}.json"
    return audit_parent / "engagement-state.json"


def load_engagement_state(settings: Settings) -> EngagementState:
    engagement_id = settings.engagement_id
    if settings.engagement_topology_path:
        topology_path = Path(settings.engagement_topology_path)
        topology = load_topology_yaml(topology_path)
        seed_id = topology.engagement_id or engagement_id
        state = EngagementState.from_topology(topology, engagement_id=seed_id)
        state_path = default_state_path(settings)
        if state_path.exists():
            persisted = EngagementState.load(state_path)
            if persisted.engagement_id == seed_id:
                state = state.merge_runtime(persisted)
            state = state.model_copy(
                update={"engagement_id": seed_id, "notes": topology.notes or state.notes}
            )
        state.persist(state_path)
        return state

    state_path = default_state_path(settings)
    if state_path.exists():
        persisted = EngagementState.load(state_path)
        if persisted.engagement_id == engagement_id:
            return persisted

    state = EngagementState(
        engagement_id=engagement_id,
        hosts={
            "operator": HostRuntime(transport=Transport.LOCAL),
        },
    )
    state.persist(state_path)
    return state
