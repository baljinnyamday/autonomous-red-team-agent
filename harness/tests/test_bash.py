import asyncio
from pathlib import Path

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings
from agent_redteam.execution.result import CommandResult
from agent_redteam.execution.run_on_host import run_on_host
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.store import EngagementStore
from agent_redteam.targets.topology import CredentialFinding, Transport
from agent_redteam.tools.bash import bash_tool
from agent_redteam.tools.types import ToolCall


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def _local_state() -> EngagementState:
    return EngagementState(
        engagement_id="eng-1",
        hosts={"operator": HostRuntime(transport=Transport.LOCAL)},
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
        engagement_id="eng-1",
        metadata={
            "engagement_state": resolved_state,
            "settings": resolved_settings,
            "engagement_store": store,
            "engagement_db_path": str(db_path),
        },
    )


def test_local_bash_runs_command() -> None:
    output, _state = asyncio.run(
        run_on_host(
            _local_state(),
            "operator",
            "printf hello",
            _settings(),
        )
    )
    assert "exit_code=0" in output
    assert "hello" in output


def test_local_bash_allows_rm(tmp_path: Path) -> None:
    target = tmp_path / "remove-me.txt"
    target.write_text("gone", encoding="utf-8")

    output, _state = asyncio.run(
        run_on_host(
            _local_state(),
            "operator",
            f"rm {target}",
            _settings(),
        )
    )

    assert not target.exists()
    assert "exit_code=0" in output


def test_bash_tool_allows_ssh_on_operator(tmp_path: Path) -> None:
    output = asyncio.run(
        bash_tool(
            _context(tmp_path),
            ToolCall(
                call_id="c1",
                name="bash",
                arguments={"host": "operator", "command": "printf ssh-ok"},
            ),
        )
    )
    assert "exit_code=0" in output
    assert "ssh-ok" in output


def test_bash_tool_passes_agent_timeout_override(tmp_path: Path) -> None:
    captured: list[float | None] = []

    async def fake_run_on_host(
        state: EngagementState,
        host_id: str,
        command: str,
        settings: Settings,
        *,
        timeout_seconds: float | None = None,
        run_command=None,
    ) -> tuple[str, EngagementState]:
        captured.append(timeout_seconds)
        return "exit_code=0\ntimed_out=false\nstdout:\nok\nstderr:\n", state

    import agent_redteam.tools.bash as bash_module

    original = bash_module.run_on_host
    bash_module.run_on_host = fake_run_on_host
    try:
        asyncio.run(
            bash_tool(
                _context(tmp_path, settings=_settings(default_exec_timeout_seconds=3600.0)),
                ToolCall(
                    call_id="c-timeout",
                    name="bash",
                    arguments={
                        "host": "operator",
                        "command": "printf ok",
                        "timeout_seconds": 45.0,
                    },
                ),
            )
        )
    finally:
        bash_module.run_on_host = original

    assert captured == [45.0]


def test_bash_tool_uses_settings_default_timeout_when_unset(tmp_path: Path) -> None:
    captured: list[float | None] = []

    async def fake_run_on_host(
        state: EngagementState,
        host_id: str,
        command: str,
        settings: Settings,
        *,
        timeout_seconds: float | None = None,
        run_command=None,
    ) -> tuple[str, EngagementState]:
        captured.append(timeout_seconds)
        return "exit_code=0\ntimed_out=false\nstdout:\nok\nstderr:\n", state

    import agent_redteam.tools.bash as bash_module

    original = bash_module.run_on_host
    bash_module.run_on_host = fake_run_on_host
    try:
        asyncio.run(
            bash_tool(
                _context(
                    tmp_path,
                    settings=_settings(
                        bash_timeout_seconds=1800.0,
                        default_exec_timeout_seconds=3600.0,
                    ),
                ),
                ToolCall(
                    call_id="c-default-timeout",
                    name="bash",
                    arguments={
                        "host": "operator",
                        "command": "printf ok",
                    },
                ),
            )
        )
    finally:
        bash_module.run_on_host = original

    assert captured == [1800.0]


def test_bash_schema_exports_field_defaults() -> None:
    from agent_redteam.core.config import DEFAULT_BASH_TIMEOUT_SECONDS
    from agent_redteam.tools.bash import bash_definition

    schema = bash_definition().input_schema
    properties = schema["properties"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == list(properties.keys())
    assert properties["timeout_seconds"]["default"] == DEFAULT_BASH_TIMEOUT_SECONDS
    assert "default" not in properties["host"]
    assert "default" not in properties["command"]


def test_bash_tool_description_has_usage_without_defaults_section() -> None:
    from agent_redteam.tools.bash import bash_definition

    description = bash_definition().description
    assert "Usage:" in description
    assert "Defaults:" not in description


def test_run_on_host_passes_explicit_timeout_to_runner() -> None:
    captured: list[float | None] = []

    async def fake_run(
        command: list[str],
        *,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        captured.append(timeout_seconds)
        return CommandResult(exit_code=0, stdout=b"ok", stderr=b"", timed_out=False)

    asyncio.run(
        run_on_host(
            EngagementState(
                engagement_id="eng-1",
                hosts={
                    "web": HostRuntime(
                        transport=Transport.REMOTE,
                        address="10.0.0.8",
                        user="ubuntu",
                    )
                },
            ),
            "web",
            "hostname",
            _settings(default_exec_timeout_seconds=3600.0),
            timeout_seconds=120.0,
            run_command=fake_run,
        )
    )

    assert captured == [120.0]


def test_remote_bash_builds_ssh_with_identity_and_jump() -> None:
    state = EngagementState(
        engagement_id="eng-1",
        hosts={
            "jump": HostRuntime(
                transport=Transport.REMOTE,
                address="jump.lab",
                user="ubuntu",
                credentials=[
                    CredentialFinding(
                        secret="~/jump.pem",
                        type="ssh_identity_file_path",
                    )
                ],
            ),
            "web": HostRuntime(
                transport=Transport.REMOTE,
                address="10.0.0.8",
                user="ubuntu",
                via=["jump"],
                credentials=[
                    CredentialFinding(
                        secret="~/web.pem",
                        type="ssh_identity_file_path",
                    )
                ],
            ),
        },
    )
    calls: list[list[str]] = []

    async def fake_run(
        command: list[str],
        *,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        calls.append(command)
        return CommandResult(exit_code=0, stdout=b"remote-ok", stderr=b"", timed_out=False)

    output, new_state = asyncio.run(
        run_on_host(
            state,
            "web",
            "hostname",
            _settings(),
            run_command=fake_run,
        )
    )

    assert new_state is state
    assert "remote-ok" in output
    assert len(calls) == 1
    joined = " ".join(calls[0])
    assert "ssh" in joined
    assert "-i" in joined
    assert "ubuntu@10.0.0.8" in joined
    assert "bash -lc" in joined
    assert "ProxyCommand" in joined


def test_remote_bash_uses_ssh_key_file_credential_type() -> None:
    state = EngagementState(
        engagement_id="eng-1",
        hosts={
            "mithron": HostRuntime(
                transport=Transport.REMOTE,
                address="4.223.132.56",
                user="azureuser",
                credentials=[
                    CredentialFinding(
                        secret="/Users/artisan/mithron-dev-vm_key.pem",
                        type="ssh_key_file",
                    )
                ],
            )
        },
    )
    calls: list[list[str]] = []

    async def fake_run(
        command: list[str],
        *,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        calls.append(command)
        return CommandResult(exit_code=0, stdout=b"ok", stderr=b"", timed_out=False)

    asyncio.run(
        run_on_host(
            state,
            "mithron",
            "hostname",
            _settings(),
            run_command=fake_run,
        )
    )

    joined = " ".join(calls[0])
    assert "-i" in joined
    assert "/Users/artisan/mithron-dev-vm_key.pem" in joined
    assert "azureuser@4.223.132.56" in joined


def test_remote_bash_uses_identity_file_credential_type() -> None:
    state = EngagementState(
        engagement_id="eng-1",
        hosts={
            "mithron": HostRuntime(
                transport=Transport.REMOTE,
                address="4.223.132.56",
                user="azureuser",
                credentials=[
                    CredentialFinding(
                        secret="/Users/artisan/mithron-dev-vm_key.pem",
                        type="identity-file",
                    )
                ],
            )
        },
    )
    calls: list[list[str]] = []

    async def fake_run(
        command: list[str],
        *,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        calls.append(command)
        return CommandResult(exit_code=0, stdout=b"ok", stderr=b"", timed_out=False)

    asyncio.run(
        run_on_host(
            state,
            "mithron",
            "hostname",
            _settings(),
            run_command=fake_run,
        )
    )

    joined = " ".join(calls[0])
    assert "-i" in joined
    assert "/Users/artisan/mithron-dev-vm_key.pem" in joined
    assert "azureuser@4.223.132.56" in joined


def test_ssh_identity_file_prefers_absolute_path_over_tilde() -> None:
    from agent_redteam.execution.ssh import ssh_identity_file

    host = HostRuntime(
        transport=Transport.REMOTE,
        address="4.223.132.56",
        credentials=[
            CredentialFinding(secret="~/mithron-dev-vm_key.pem", type="ssh_key_file"),
            CredentialFinding(
                secret="/Users/artisan/mithron-dev-vm_key.pem",
                type="ssh_key_file",
            ),
        ],
    )
    assert ssh_identity_file(host) == "/Users/artisan/mithron-dev-vm_key.pem"


def test_legacy_runner_transport_normalizes_to_remote(tmp_path: Path) -> None:
    store = EngagementStore.connect(tmp_path / "eng.db")
    store._conn.execute(
        """
        INSERT INTO hosts (
            engagement_id, host_id, transport, address, user, via_json,
            runner_endpoint, runner_ready_announced
        ) VALUES (
            'eng-1', 'legacy', 'runner', '10.0.0.9', 'ubuntu', '[]',
            'http://127.0.0.1:8765', 1
        )
        """
    )
    store._conn.commit()

    host = store.load_state("eng-1").hosts["legacy"]
    assert host.transport is Transport.REMOTE
    assert host.address == "10.0.0.9"
