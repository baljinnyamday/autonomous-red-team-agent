from agent_redteam.targets.nx_graph import build_digraph, reachable_from, shortest_path
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.topology import ServiceFinding, Transport


def _chain_state() -> EngagementState:
    return EngagementState(
        engagement_id="eng-1",
        hosts={
            "operator": HostRuntime(transport=Transport.LOCAL),
            "host_0": HostRuntime(
                transport=Transport.REMOTE,
                address="10.0.0.10",
                discovered_from="operator",
                services=[ServiceFinding(port=22, protocol="tcp", product="ssh")],
            ),
            "host_1": HostRuntime(
                transport=Transport.REMOTE, address="10.0.0.11", discovered_from="host_0"
            ),
        },
    )


def test_build_digraph_nodes_and_edges() -> None:
    graph = build_digraph(_chain_state())
    assert set(graph.nodes) == {"operator", "host_0", "host_1"}
    assert graph.nodes["operator"]["is_operator"] is True
    assert graph.nodes["host_0"]["services"] == 1
    assert graph.edges["operator", "host_0"]["kind"] == "discovered"


def test_reachable_from_operator_reaches_whole_chain() -> None:
    graph = build_digraph(_chain_state())
    assert reachable_from(graph, "operator") == {"host_0", "host_1"}
    assert reachable_from(graph, "host_1") == set()


def test_shortest_path_follows_provenance() -> None:
    graph = build_digraph(_chain_state())
    assert shortest_path(graph, "operator", "host_1") == ["operator", "host_0", "host_1"]
    assert shortest_path(graph, "host_1", "operator") is None
    assert shortest_path(graph, "operator", "ghost") is None
