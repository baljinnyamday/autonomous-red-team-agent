"""NetworkX view over engagement state.

This is a *derived* analysis layer, not a store: SQLite (`EngagementStore`) stays
the source of truth. We build an `nx.DiGraph` from the same provenance edges that
`targets/graph.py` renders to Mermaid/DOT, so reachability, shortest-path, and
scoring share one edge-derivation rule. Used by `tools/find_path.py`, the figure
script, and `scoring/metrics.py`.
"""

from __future__ import annotations

import networkx as nx

from agent_redteam.targets.graph import OPERATOR_HOST_ID, derive_edges
from agent_redteam.targets.state import EngagementState


def build_digraph(state: EngagementState) -> nx.DiGraph:
    graph: nx.DiGraph = nx.DiGraph()
    for host_id, host in state.hosts.items():
        graph.add_node(
            host_id,
            is_operator=host_id == OPERATOR_HOST_ID,
            transport=host.transport.value,
            tags=",".join(host.tags),
            address=host.address or "",
            services=len(host.services),
            credentials=len(host.credentials),
        )
    for edge in derive_edges(state):
        graph.add_edge(edge.source, edge.target, kind=edge.kind)
    return graph


def reachable_from(graph: nx.DiGraph, host_id: str) -> set[str]:
    if host_id not in graph:
        return set()
    return set(nx.descendants(graph, host_id))


def shortest_path(graph: nx.DiGraph, source: str, target: str) -> list[str] | None:
    if source not in graph or target not in graph:
        return None
    try:
        return nx.shortest_path(graph, source, target)
    except nx.NetworkXNoPath:
        return None
