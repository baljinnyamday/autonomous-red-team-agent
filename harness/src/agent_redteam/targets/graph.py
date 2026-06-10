"""Derive a topology graph from engagement state and render it (Mermaid / DOT).

The graph is derived, never stored: nodes are hosts, and each non-operator host gets
one parent edge from its provenance (`discovered_from`), falling back to the last jump
hop (`via`), else the operator root. This mirrors how incalmo derives attack paths
rather than persisting an edge table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent_redteam.targets.state import EngagementState, HostRuntime

OPERATOR_HOST_ID = "operator"

_UNSAFE_MERMAID_ID = re.compile(r"[^A-Za-z0-9_]")
_MERMAID_ARROWS = {"discovered": "-->", "pivot": "-.->", "root": "-.->"}
_DOT_STYLES = {"discovered": "solid", "pivot": "dashed", "root": "dotted"}


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: str  # discovered | pivot | root


def derive_edges(state: EngagementState) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    for host_id, host in sorted(state.hosts.items()):
        if host_id == OPERATOR_HOST_ID:
            continue
        source, kind = _parent_of(host)
        if source in state.hosts:
            edges.append(GraphEdge(source=source, target=host_id, kind=kind))
    return edges


def to_mermaid(state: EngagementState) -> str:
    alias = {host_id: _mermaid_id(host_id) for host_id in state.hosts}
    lines = ["flowchart LR"]
    for host_id in sorted(state.hosts):
        label = _label(host_id, state.hosts[host_id])
        if host_id == OPERATOR_HOST_ID:
            lines.append(f'    {alias[host_id]}(["{label}"])')
        else:
            lines.append(f'    {alias[host_id]}["{label}"]')
    for edge in derive_edges(state):
        arrow = _MERMAID_ARROWS[edge.kind]
        lines.append(f"    {alias[edge.source]} {arrow}|{edge.kind}| {alias[edge.target]}")
    return "\n".join(lines)


def to_dot(state: EngagementState) -> str:
    lines = ["digraph topology {", "    rankdir=LR;", "    node [shape=box];"]
    for host_id in sorted(state.hosts):
        label = _label(host_id, state.hosts[host_id])
        shape = "doublecircle" if host_id == OPERATOR_HOST_ID else "box"
        lines.append(f'    "{host_id}" [label="{label}", shape={shape}];')
    for edge in derive_edges(state):
        style = _DOT_STYLES[edge.kind]
        lines.append(
            f'    "{edge.source}" -> "{edge.target}" [label="{edge.kind}", style={style}];'
        )
    lines.append("}")
    return "\n".join(lines)


def _parent_of(host: HostRuntime) -> tuple[str, str]:
    if host.discovered_from:
        return host.discovered_from, "discovered"
    if host.via:
        return host.via[-1], "pivot"
    return OPERATOR_HOST_ID, "root"


def _label(host_id: str, host: HostRuntime) -> str:
    return host_id if not host.address else f"{host_id} ({host.address})"


def _mermaid_id(host_id: str) -> str:
    return "n_" + _UNSAFE_MERMAID_ID.sub("_", host_id)
