from pathlib import Path

from agent_redteam.core.config import Settings
from agent_redteam.targets.state import default_db_path, load_engagement_state
from agent_redteam.targets.topology import Transport


def test_load_engagement_state_ensures_local_operator(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        engagement_id="eng-local",
        audit_log_path=str(tmp_path / "audit.jsonl"),
        engagement_db_path=str(tmp_path / "eng.db"),
    )
    state, _store = load_engagement_state(settings)
    operator = state.hosts["operator"]
    assert operator.transport is Transport.LOCAL
    assert operator.hostname
    assert operator.os
    assert operator.arch
    assert operator.user
    assert "operator" in operator.tags


def test_default_db_path_uses_engagement_id(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        engagement_id="eng-abc",
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    assert default_db_path(settings) == tmp_path / "engagement-eng-abc.db"


def test_default_db_path_lands_in_run_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / ".runs"
    settings = Settings(
        _env_file=None,
        engagement_id="eng-abc",
        audit_log_path=str(run_dir),
    )
    assert default_db_path(settings) == run_dir / "engagement-eng-abc.db"


def test_pinned_topology_id_is_the_effective_runtime_id(tmp_path: Path) -> None:
    topology_path = tmp_path / "topology.yaml"
    topology_path.write_text(
        "engagement_id: lab-pinned\n"
        "hosts:\n"
        "  - id: web\n"
        "    transport: ssh_pending\n"
        "    address: 10.0.0.12\n",
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        engagement_id="eng-autogen",
        audit_log_path=str(tmp_path / "audit.jsonl"),
        engagement_db_path=str(tmp_path / "eng.db"),
        engagement_topology_path=str(topology_path),
    )
    state, store = load_engagement_state(settings)
    # simple_react binds context.engagement_id to the loaded state id; tools must
    # therefore read/write the same SQLite partition the topology was seeded into.
    assert state.engagement_id == "lab-pinned"
    assert "web" in state.hosts
    assert store.host_exists("lab-pinned", "web")
    assert not store.host_exists("eng-autogen", "web")
