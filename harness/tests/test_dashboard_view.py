from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from agent_redteam.agents.base import AgentContext

from agent_redteam.api.app import create_app
from agent_redteam.api.server import _live_topology_state
from agent_redteam.api.status_hub import StatusHub
from agent_redteam.api.topology_view import diff_topology
from agent_redteam.schemas.dashboard import RedTeamNode
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.store import EngagementStore
from agent_redteam.targets.topology import CredentialFinding, Transport

_T0 = "2026-01-01T00:00:00+00:00"
_T1 = "2026-01-01T00:05:00+00:00"


def _state(*, compromised: bool = False) -> EngagementState:
    web = HostRuntime(
        transport=Transport.REMOTE,
        address="203.0.113.10",
        discovered_from="operator",
        tags=["web", "compromised"] if compromised else ["web"],
        credentials=[CredentialFinding(kind="password", username="svc")] if compromised else [],
    )
    return EngagementState(
        engagement_id="ENG-TEST",
        hosts={"operator": HostRuntime(transport=Transport.LOCAL), "web-01": web},
    )


def test_diff_discovers_new_hosts_and_edges() -> None:
    events, nodes, edges = diff_topology({}, {}, _state(), _T0)

    kinds = [e["type"] for e in events]
    assert kinds.count("node.discovered") == 2
    assert "edge.added" in kinds
    assert set(nodes) == {"operator", "web-01"}
    assert "operator->web-01" in edges
    # The "compromised" status tag must not leak into the technique list.
    assert nodes["web-01"].techniques == ["web"]


def test_diff_emits_status_change_and_pins_discovered_at() -> None:
    _, nodes, edges = diff_topology({}, {}, _state(), _T0)

    events, next_nodes, _ = diff_topology(nodes, edges, _state(compromised=True), _T1)

    status_events = [e for e in events if e["type"] == "node.status"]
    assert status_events == [
        {
            "type": "node.status",
            "nodeId": "web-01",
            "status": "compromised",
            "access": "user",
            "at": _T1,
        }
    ]
    web = next_nodes["web-01"]
    assert web.discovered_at == _T0  # first-seen time is preserved
    assert web.compromised_at == _T1


def test_diff_emits_technique_updates() -> None:
    base = _state()
    _, nodes, edges = diff_topology({}, {}, base, _T0)

    web = base.hosts["web-01"]
    web.tags = ["web", "sql-injection"]
    events, _, _ = diff_topology(nodes, edges, base, _T1)

    assert events == [
        {
            "type": "node.status",
            "nodeId": "web-01",
            "status": "discovered",
            "access": "none",
            "techniques": ["web", "sql-injection"],
            "at": _T1,
        }
    ]


def test_app_serves_engagement_contract() -> None:
    state = _state(compromised=True)
    hub = StatusHub(
        engagement_id="ENG-TEST",
        operator="bd1125",
        targets=["203.0.113.10"],
        started_at=datetime.now(UTC),
        live_state=lambda: state,
    )
    hub.refresh_topology()
    client = TestClient(create_app(hub))

    assert client.get("/api/v1/health").json()["status"] == "ok"

    listing = client.get("/api/v1/engagements").json()
    assert [e["id"] for e in listing] == ["ENG-TEST"]
    assert "createdAt" in listing[0]  # camelCase boundary for the frontend

    assert client.get("/api/v1/engagements/ENG-TEST").json()["operator"] == "bd1125"
    assert client.get("/api/v1/engagements/nope").status_code == 404


def test_snapshot_replays_current_state() -> None:
    hub = StatusHub(
        engagement_id="ENG-TEST",
        operator="bd1125",
        targets=[],
        started_at=datetime.now(UTC),
        live_state=lambda: _state(compromised=True),
    )
    hub.refresh_topology()

    events = hub.snapshot_events()

    assert events[0]["type"] == "engagement.status"
    discovered = [e["node"]["id"] for e in events if e["type"] == "node.discovered"]
    assert set(discovered) == {"operator", "web-01"}
    assert any(e["type"] == "edge.added" for e in events)


def test_redteam_node_serializes_camelcase() -> None:
    node = RedTeamNode(
        id="web-01",
        hostname="web-01",
        ip="203.0.113.10",
        status="compromised",
        access="user",
        discovered_at=_T0,
        compromised_at=_T1,
    )
    dumped = node.model_dump(by_alias=True)
    assert dumped["discoveredAt"] == _T0
    assert dumped["compromisedAt"] == _T1


def test_live_topology_state_reads_store_not_stale_metadata(tmp_path: Path) -> None:
    store = EngagementStore.connect(tmp_path / "eng.db")
    store.ensure_local_host("eng-1")
    stale_state = store.load_state("eng-1")
    store.upsert_host("eng-1", "db", address="10.0.0.99")

    context = AgentContext(
        engagement_id="eng-1",
        metadata={
            "engagement_state": stale_state,
            "engagement_store": store,
        },
    )

    assert "db" in _live_topology_state(context)().hosts
