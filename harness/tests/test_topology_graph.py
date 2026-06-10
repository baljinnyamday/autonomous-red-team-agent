from agent_redteam.targets.graph import GraphEdge, derive_edges, to_dot, to_mermaid
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.topology import Transport


def _chain_state() -> EngagementState:
    return EngagementState(
        engagement_id="eng-1",
        hosts={
            "operator": HostRuntime(transport=Transport.LOCAL),
            "host_0": HostRuntime(
                transport=Transport.REMOTE, address="10.0.0.10", discovered_from="operator"
            ),
            "host_1": HostRuntime(
                transport=Transport.REMOTE, address="10.0.0.11", discovered_from="host_0"
            ),
            # via fallback when discovered_from is unset
            "host_2": HostRuntime(
                transport=Transport.REMOTE, address="10.0.0.12", via=["host_0", "host_1"]
            ),
        },
    )


def test_derive_edges_follows_provenance_then_via() -> None:
    edges = derive_edges(_chain_state())
    assert edges == [
        GraphEdge(source="operator", target="host_0", kind="discovered"),
        GraphEdge(source="host_0", target="host_1", kind="discovered"),
        GraphEdge(source="host_1", target="host_2", kind="pivot"),
    ]


def test_root_fallback_points_at_operator() -> None:
    state = EngagementState(
        engagement_id="eng-1",
        hosts={
            "operator": HostRuntime(transport=Transport.LOCAL),
            "lone": HostRuntime(transport=Transport.REMOTE, address="10.0.0.9"),
        },
    )
    assert derive_edges(state) == [GraphEdge(source="operator", target="lone", kind="root")]


def test_renderers_emit_chain_edges() -> None:
    state = _chain_state()
    mermaid = to_mermaid(state)
    assert mermaid.startswith("flowchart LR")
    assert "n_operator -->|discovered| n_host_0" in mermaid
    assert "n_host_1 -.->|pivot| n_host_2" in mermaid

    dot = to_dot(state)
    assert dot.startswith("digraph topology {")
    assert '"operator" -> "host_0" [label="discovered", style=solid];' in dot
    assert '"host_1" -> "host_2" [label="pivot", style=dashed];' in dot
