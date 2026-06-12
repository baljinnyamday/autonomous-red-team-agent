"""Map the live ``EngagementState`` onto the dashboard's node/edge model.

Pure functions: no I/O, no shared state. ``diff_topology`` compares the previous
snapshot against the current state and returns the ``ActivityEvent`` deltas the
SSE stream needs (``node.discovered`` / ``node.status`` / ``edge.added``), plus the
rebuilt node/edge maps to carry forward. The caller owns timestamps so a node's
``discoveredAt`` stays fixed once assigned.
"""

from __future__ import annotations

from typing import Any

from agent_redteam.schemas.dashboard import AccessLevel, AttackEdge, NodeStatus, RedTeamNode
from agent_redteam.targets.graph import derive_edges
from agent_redteam.targets.state import EngagementState, HostRuntime

_COMPROMISED_TAGS = frozenset({"compromised", "owned", "foothold"})
_PRIVILEGED_TAGS = frozenset({"root", "admin", "administrator", "privileged", "system"})
_ROOT_USERS = frozenset({"root", "administrator", "system"})
# Tags that encode node status/access rather than an applied technique.
_STATUS_TAGS = _COMPROMISED_TAGS | _PRIVILEGED_TAGS


def host_techniques(host: HostRuntime) -> list[str]:
    return [tag for tag in host.tags if tag.lower() not in _STATUS_TAGS]


def derive_status(host: HostRuntime) -> NodeStatus:
    tags = {tag.lower() for tag in host.tags}
    if tags & _COMPROMISED_TAGS or host.credentials:
        return "compromised"
    return "discovered"


def derive_access(host: HostRuntime) -> AccessLevel:
    tags = {tag.lower() for tag in host.tags}
    if tags & _PRIVILEGED_TAGS or (host.user and host.user.lower() in _ROOT_USERS):
        return "root"
    if tags & _COMPROMISED_TAGS or host.credentials:
        return "user"
    return "none"


def host_node(
    host_id: str,
    host: HostRuntime,
    *,
    discovered_at: str,
    compromised_at: str | None,
) -> RedTeamNode:
    return RedTeamNode(
        id=host_id,
        hostname=host.hostname or host_id,
        ip=host.address or "",
        os=host.os,
        status=derive_status(host),
        access=derive_access(host),
        techniques=host_techniques(host),
        discovered_at=discovered_at,
        compromised_at=compromised_at,
    )


def state_edges(state: EngagementState) -> dict[str, AttackEdge]:
    edges: dict[str, AttackEdge] = {}
    for edge in derive_edges(state):
        edge_id = f"{edge.source}->{edge.target}"
        edges[edge_id] = AttackEdge(
            id=edge_id, source=edge.source, target=edge.target, technique=edge.kind
        )
    return edges


def diff_topology(
    prev_nodes: dict[str, RedTeamNode],
    prev_edges: dict[str, AttackEdge],
    state: EngagementState,
    now: str,
) -> tuple[list[dict[str, Any]], dict[str, RedTeamNode], dict[str, AttackEdge]]:
    """Return (events, next_nodes, next_edges) for the transition to ``state``."""
    events: list[dict[str, Any]] = []
    next_nodes: dict[str, RedTeamNode] = {}

    for host_id, host in state.hosts.items():
        prev = prev_nodes.get(host_id)
        status = derive_status(host)
        if prev is None:
            node = host_node(
                host_id,
                host,
                discovered_at=now,
                compromised_at=now if status == "compromised" else None,
            )
            next_nodes[host_id] = node
            events.append({"type": "node.discovered", "node": _dump(node), "at": now})
            continue

        compromised_at = prev.compromised_at
        if status == "compromised" and compromised_at is None:
            compromised_at = now
        node = host_node(
            host_id, host, discovered_at=prev.discovered_at, compromised_at=compromised_at
        )
        next_nodes[host_id] = node
        if _node_changed(prev, node):
            event: dict[str, Any] = {
                "type": "node.status",
                "nodeId": host_id,
                "status": node.status,
                "access": node.access,
                "at": now,
            }
            if prev.techniques != node.techniques:
                event["techniques"] = node.techniques
            events.append(event)

    next_edges = state_edges(state)
    for edge_id, edge in next_edges.items():
        if edge_id not in prev_edges:
            events.append({"type": "edge.added", "edge": _dump(edge), "at": now})

    return events, next_nodes, next_edges


def _node_changed(prev: RedTeamNode, curr: RedTeamNode) -> bool:
    return (
        prev.status != curr.status
        or prev.access != curr.access
        or prev.techniques != curr.techniques
    )


def _dump(model: RedTeamNode | AttackEdge) -> dict[str, Any]:
    return model.model_dump(by_alias=True)
