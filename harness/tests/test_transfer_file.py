import asyncio
from pathlib import Path

import pytest

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import DEFAULT_TRANSFER_TIMEOUT_SECONDS, Settings
from agent_redteam.core.exceptions import ConfigurationError
from agent_redteam.execution.artifacts import resolve_artifact_path, resolve_local_name
from agent_redteam.execution.remote import run_scp_command
from agent_redteam.execution.result import CommandResult
from agent_redteam.execution.ssh import build_scp_command
from agent_redteam.execution.transfer import transfer_file_on_host
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.store import EngagementStore
from agent_redteam.targets.topology import Transport
from agent_redteam.tools.transfer_file import transfer_file_definition, transfer_file_tool
from agent_redteam.tools.types import ToolCall


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {"audit_log_path": str(Path("/tmp/agent-runs-test"))}
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _local_state() -> EngagementState:
    return EngagementState(
        engagement_id="eng-1",
        hosts={"operator": HostRuntime(transport=Transport.LOCAL)},
    )


def _remote_state() -> EngagementState:
    return EngagementState(
        engagement_id="eng-1",
        hosts={
            "web": HostRuntime(
                transport=Transport.REMOTE,
                address="10.0.0.12",
                user="ubuntu",
            ),
        },
    )


def _context(
    tmp_path: Path,
    state: EngagementState | None = None,
    settings: Settings | None = None,
) -> AgentContext:
    resolved_state = state or _local_state()
    resolved_settings = settings or _settings()
    db_path = tmp_path / "engagement-state-test.db"
    store = EngagementStore.connect(db_path)
    store.save_state(resolved_state)
    return AgentContext(
        engagement_id=resolved_state.engagement_id,
        metadata={
            "engagement_state": resolved_state,
            "settings": resolved_settings,
            "engagement_store": store,
            "engagement_db_path": str(db_path),
        },
    )


def test_resolve_local_name_rejects_path_traversal() -> None:
    with pytest.raises(ConfigurationError, match="bare filename"):
        resolve_local_name(local_name="../escape.txt", remote_path="/etc/passwd")


def test_resolve_artifact_path_is_host_scoped(tmp_path: Path) -> None:
    settings = _settings(audit_log_path=str(tmp_path / "audit.jsonl"))
    path = resolve_artifact_path(
        settings,
        "eng-1",
        "web",
        local_name="secrets.db",
        remote_path="/var/lib/app/secrets.db",
    )
    assert path == tmp_path / "engagement-eng-1" / "artifacts" / "web" / "secrets.db"


def test_build_scp_command_upload_and_download() -> None:
    upload = build_scp_command(
        local_path="/local/file.txt",
        remote_path="/remote/file.txt",
        target="ubuntu@10.0.0.12",
        via_chain=[],
        direction="upload",
    )
    download = build_scp_command(
        local_path="/local/file.txt",
        remote_path="/remote/file.txt",
        target="ubuntu@10.0.0.12",
        via_chain=[],
        direction="download",
    )
    assert upload[-2:] == ["/local/file.txt", "ubuntu@10.0.0.12:/remote/file.txt"]
    assert download[-2:] == ["ubuntu@10.0.0.12:/remote/file.txt", "/local/file.txt"]


def test_local_download_copies_file(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("secret-data", encoding="utf-8")
    artifact = tmp_path / "artifacts" / "operator" / "source.txt"
    settings = _settings(audit_log_path=str(tmp_path / "audit.jsonl"))

    size, _state = asyncio.run(
        transfer_file_on_host(
            _local_state(),
            "operator",
            direction="download",
            remote_path=str(source),
            local_path=artifact,
            settings=settings,
        )
    )

    assert size == len("secret-data")
    assert artifact.read_text(encoding="utf-8") == "secret-data"


def test_local_upload_copies_file(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "operator" / "payload.sh"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("#!/bin/sh", encoding="utf-8")
    destination = tmp_path / "uploaded" / "payload.sh"
    settings = _settings(audit_log_path=str(tmp_path / "audit.jsonl"))

    size, _state = asyncio.run(
        transfer_file_on_host(
            _local_state(),
            "operator",
            direction="upload",
            remote_path=str(destination),
            local_path=artifact,
            settings=settings,
        )
    )

    assert size == len("#!/bin/sh")
    assert destination.read_text(encoding="utf-8") == "#!/bin/sh"


def test_remote_download_uses_scp_argv(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    async def fake_run(
        command: list[str],
        *,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        captured.append(command)
        Path(command[-1]).write_bytes(b"remote-bytes")
        return CommandResult(exit_code=0, stdout=b"", stderr=b"", timed_out=False)

    artifact = tmp_path / "artifact.bin"
    settings = _settings(audit_log_path=str(tmp_path / "audit.jsonl"))

    size, _state = asyncio.run(
        transfer_file_on_host(
            _remote_state(),
            "web",
            direction="download",
            remote_path="/remote/artifact.bin",
            local_path=artifact,
            settings=settings,
            run_command=fake_run,
        )
    )

    assert size == len(b"remote-bytes")
    assert captured[0][0] == "scp"
    assert captured[0][-2:] == ["ubuntu@10.0.0.12:/remote/artifact.bin", str(artifact)]


def test_remote_upload_uses_scp_argv(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    async def fake_run(
        command: list[str],
        *,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        captured.append(command)
        return CommandResult(exit_code=0, stdout=b"", stderr=b"", timed_out=False)

    artifact = tmp_path / "payload.bin"
    artifact.write_bytes(b"payload")
    settings = _settings(audit_log_path=str(tmp_path / "audit.jsonl"))

    size, _state = asyncio.run(
        transfer_file_on_host(
            _remote_state(),
            "web",
            direction="upload",
            remote_path="/remote/payload.bin",
            local_path=artifact,
            settings=settings,
            run_command=fake_run,
        )
    )

    assert size == len(b"payload")
    assert captured[0][-2:] == [str(artifact), "ubuntu@10.0.0.12:/remote/payload.bin"]


def test_download_rejects_oversized_file(tmp_path: Path) -> None:
    source = tmp_path / "huge.bin"
    source.write_bytes(b"x" * 32)
    artifact = tmp_path / "artifacts" / "operator" / "huge.bin"
    settings = _settings(audit_log_path=str(tmp_path / "audit.jsonl"))

    with pytest.raises(ConfigurationError, match="exceeds max size"):
        asyncio.run(
            transfer_file_on_host(
                _local_state(),
                "operator",
                direction="download",
                remote_path=str(source),
                local_path=artifact,
                settings=settings,
                max_bytes=16,
            )
        )

    assert not artifact.exists()


def test_upload_rejects_oversized_file_and_preserves_source(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "operator" / "huge.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"x" * 32)
    settings = _settings(audit_log_path=str(tmp_path / "audit.jsonl"))

    with pytest.raises(ConfigurationError, match="exceeds max size"):
        asyncio.run(
            transfer_file_on_host(
                _local_state(),
                "operator",
                direction="upload",
                remote_path=str(tmp_path / "dest" / "huge.bin"),
                local_path=artifact,
                settings=settings,
                max_bytes=16,
            )
        )

    assert artifact.exists(), "source artifact must not be deleted on failed upload size check"


def test_transfer_file_tool_downloads_to_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "proof.txt"
    source.write_text("proof", encoding="utf-8")
    settings = _settings(audit_log_path=str(tmp_path / "audit.jsonl"))
    context = _context(tmp_path, settings=settings)

    output = asyncio.run(
        transfer_file_tool(
            context,
            ToolCall(
                call_id="1",
                name="transfer_file",
                arguments={
                    "host": "operator",
                    "direction": "download",
                    "remote_path": str(source),
                },
            ),
        )
    )

    artifact = tmp_path / "engagement-eng-1" / "artifacts" / "operator" / "proof.txt"
    assert artifact.read_text(encoding="utf-8") == "proof"
    assert "Transferred 5 bytes" in output
    assert str(artifact) in output


def test_transfer_file_schema_exports_field_defaults() -> None:
    schema = transfer_file_definition().input_schema
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(properties.keys())
    assert properties["timeout_seconds"]["default"] == DEFAULT_TRANSFER_TIMEOUT_SECONDS
    assert properties["local_name"]["default"] is None
    assert "default" not in properties["host"]
    assert "default" not in properties["remote_path"]


def test_transfer_file_definition_is_mutating() -> None:
    definition = transfer_file_definition()
    assert definition.mutating is True
    assert definition.name == "transfer_file"


def test_run_scp_command_builds_identity_and_proxy() -> None:
    captured: list[list[str]] = []

    async def fake_run(
        command: list[str],
        *,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        captured.append(command)
        return CommandResult(exit_code=0, stdout=b"", stderr=b"", timed_out=False)

    jump = HostRuntime(
        transport=Transport.REMOTE,
        address="bastion.lab",
        user="ubuntu",
    )
    target = HostRuntime(
        transport=Transport.REMOTE,
        address="10.0.0.12",
        user="ubuntu",
        via=["jump"],
    )
    state = EngagementState(
        engagement_id="eng-1",
        hosts={"jump": jump, "web": target},
    )

    asyncio.run(
        run_scp_command(
            target,
            local_path="/local/x",
            remote_path="/remote/x",
            direction="upload",
            timeout_seconds=30.0,
            resolve_via=lambda via_id: state.hosts[via_id],
            run_command=fake_run,
        )
    )

    command = captured[0]
    assert "-i" not in command
    assert any("ProxyCommand=" in arg for arg in command)
    assert command[-2:] == ["/local/x", "ubuntu@10.0.0.12:/remote/x"]
