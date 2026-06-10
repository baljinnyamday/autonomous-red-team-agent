from pathlib import Path

from agent_redteam.targets.local_probe import LocalHostProbe
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.store import EngagementStore
from agent_redteam.targets.topology import (
    CredentialFinding,
    EngagementTopology,
    HostSeed,
    ServiceFinding,
    Transport,
)


def test_ensure_local_host_creates_operator(tmp_path: Path) -> None:
    store = EngagementStore.connect(tmp_path / "eng.db")
    store.ensure_local_host(
        "eng-1",
        probe=LocalHostProbe(
            hostname="devbox",
            os="Darwin 25.5.0",
            arch="arm64",
            user="artisan",
        ),
    )
    state = store.load_state("eng-1")
    operator = state.hosts["operator"]
    assert operator.transport is Transport.LOCAL
    assert operator.hostname == "devbox"
    assert operator.os == "Darwin 25.5.0"
    assert operator.arch == "arm64"
    assert operator.user == "artisan"
    assert operator.tags == ["local", "operator"]


def test_ensure_local_host_does_not_overwrite_existing_fingerprint(tmp_path: Path) -> None:
    store = EngagementStore.connect(tmp_path / "eng.db")
    store.ensure_local_host(
        "eng-1",
        probe=LocalHostProbe(hostname="first", os="Linux", arch="x86_64", user="alice"),
    )
    store.upsert_host("eng-1", "operator", os="CustomOS", hostname="pinned")
    store.ensure_local_host(
        "eng-1",
        probe=LocalHostProbe(hostname="second", os="Windows", arch="aarch64", user="bob"),
    )
    operator = store.load_state("eng-1").hosts["operator"]
    assert operator.os == "CustomOS"
    assert operator.hostname == "pinned"
    assert operator.arch == "x86_64"
    assert operator.user == "alice"


def test_seed_from_topology_inserts_missing_hosts_only(tmp_path: Path) -> None:
    store = EngagementStore.connect(tmp_path / "eng.db")
    topology = EngagementTopology(
        engagement_id="eng-1",
        hosts=[
            HostSeed(id="web", transport=Transport.REMOTE, address="10.0.0.1"),
        ],
    )
    store.seed_from_topology(topology, engagement_id="eng-1")
    store.upsert_host("eng-1", "web", os="Linux")
    store.add_tags("eng-1", "web", ["discovered"])

    store.seed_from_topology(topology, engagement_id="eng-1")
    state = store.load_state("eng-1")
    assert state.hosts["web"].os == "Linux"
    assert state.hosts["web"].tags == ["discovered"]


def test_upsert_and_findings_round_trip(tmp_path: Path) -> None:
    store = EngagementStore.connect(tmp_path / "eng.db")
    store.ensure_local_host("eng-1")
    store.upsert_host("eng-1", "db", address="10.0.0.5", user="postgres")
    store.add_tags("eng-1", "db", ["database", "database"])
    store.add_services(
        "eng-1",
        "db",
        [ServiceFinding(port=5432, protocol="tcp", product="PostgreSQL")],
    )
    store.add_credentials(
        "eng-1",
        "db",
        [CredentialFinding(username="admin", secret="s3cret", type="password", source="config")],
    )
    store.add_note("eng-1", "db", "Found open port during scan")

    state = store.load_state("eng-1")
    host = state.hosts["db"]
    assert host.address == "10.0.0.5"
    assert host.tags == ["database"]
    assert len(host.services) == 1
    assert host.services[0].port == 5432
    assert len(host.credentials) == 1
    assert host.credentials[0].secret == "s3cret"
    assert host.notes == ["Found open port during scan"]


def test_save_state_preserves_append_only_discoveries(tmp_path: Path) -> None:
    store = EngagementStore.connect(tmp_path / "eng.db")
    store.ensure_local_host("eng-1")
    store.upsert_host("eng-1", "web", transport=Transport.REMOTE, address="10.0.0.12")
    store.add_tags("eng-1", "web", ["web"])
    store.add_services("eng-1", "web", [ServiceFinding(port=443, protocol="tcp", product="nginx")])
    store.add_credentials("eng-1", "web", [CredentialFinding(username="admin", secret="pw")])
    store.add_note("eng-1", "web", "tls enabled")

    stale = EngagementState(
        engagement_id="eng-1",
        hosts={
            "web": HostRuntime(
                transport=Transport.REMOTE,
                address="10.0.0.12",
                user="ubuntu",
            )
        },
    )
    store.save_state(stale)

    web = store.load_state("eng-1").hosts["web"]
    assert web.transport is Transport.REMOTE
    assert web.user == "ubuntu"
    assert web.tags == ["web"]
    assert len(web.services) == 1
    assert web.services[0].port == 443
    assert len(web.credentials) == 1
    assert web.credentials[0].username == "admin"
    assert web.notes == ["tls enabled"]


def test_save_host_runtime_persists_connection_fields(tmp_path: Path) -> None:
    store = EngagementStore.connect(tmp_path / "eng.db")
    store.ensure_local_host("eng-1")
    store.upsert_host("eng-1", "remote", transport=Transport.REMOTE, address="10.0.0.2")

    base = store.load_state("eng-1")
    hosts = dict(base.hosts)
    hosts["remote"] = HostRuntime(
        transport=Transport.REMOTE,
        address="10.0.0.2",
        user="ubuntu",
    )
    store.save_host_runtime("eng-1", "remote", hosts["remote"])
    reloaded = store.load_state("eng-1")
    assert reloaded.hosts["remote"].transport is Transport.REMOTE
    assert reloaded.hosts["remote"].user == "ubuntu"
    assert "operator" in reloaded.hosts["operator"].tags
