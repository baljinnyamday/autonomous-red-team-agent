import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import AsyncMock

import pytest

from agent_redteam.agents.base import AgentContext
from agent_redteam.core.config import Settings
from agent_redteam.execution.bootstrap import bootstrap_runner
from agent_redteam.execution.policy import contains_rm_command, contains_ssh_command
from agent_redteam.execution.run_on_host import run_on_host
from agent_redteam.targets.state import EngagementState, HostRuntime
from agent_redteam.targets.topology import Transport
from agent_redteam.tools.exec import exec_tool
from agent_redteam.tools.types import ToolCall


def _settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        authorized_engagement=True,
        engagement_runner_token="test-token",
        bash_timeout_seconds=None,
        **overrides,
    )


def _local_state() -> EngagementState:
    return EngagementState(
        engagement_id="eng-1",
        hosts={"operator": HostRuntime(transport=Transport.LOCAL)},
    )


def _context(
    state: EngagementState | None = None,
    settings: Settings | None = None,
) -> AgentContext:
    resolved_state = state or _local_state()
    resolved_settings = settings or _settings()
    return AgentContext(
        engagement_id="eng-1",
        metadata={
            "engagement_state": resolved_state,
            "settings": resolved_settings,
            "engagement_state_path": "/tmp/engagement-state.json",
        },
    )


def test_rm_policy_detects_nested_rm() -> None:
    assert contains_rm_command("bash -lc 'rm -rf /tmp/x'")
    assert not contains_rm_command("printf rm")


def test_ssh_policy_blocks_ssh_invocation() -> None:
    assert contains_ssh_command("ssh user@host uptime")
    assert not contains_ssh_command("printf ssh")


def test_local_exec_runs_command() -> None:
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


def test_local_exec_blocks_rm(tmp_path: Path) -> None:
    protected = tmp_path / "keep.txt"
    protected.write_text("keep", encoding="utf-8")

    output, _state = asyncio.run(
        run_on_host(
            _local_state(),
            "operator",
            f"rm {protected}",
            _settings(),
        )
    )

    assert protected.exists()
    assert "exit_code=126" in output
    assert "rm" in output.lower()


def test_exec_tool_blocks_ssh() -> None:
    output = asyncio.run(
        exec_tool(
            _context(),
            ToolCall(
                call_id="c1",
                name="exec",
                arguments={"host": "operator", "command": "ssh user@remote id"},
            ),
        )
    )
    assert "exit_code=126" in output
    assert "ssh" in output.lower()


class _RunnerHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/exec":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode())
        body = json.dumps(
            {
                "exit_code": 0,
                "stdout": f"ran:{payload['command']}",
                "stderr": "",
                "timed_out": False,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


def test_runner_exec_posts_to_endpoint() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RunnerHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        endpoint = f"http://127.0.0.1:{port}"
        state = EngagementState(
            engagement_id="eng-1",
            hosts={
                "remote": HostRuntime(
                    transport=Transport.RUNNER,
                    runner_endpoint=endpoint,
                )
            },
        )
        output, _state = asyncio.run(
            run_on_host(
                state,
                "remote",
                "printf lab",
                _settings(),
            )
        )
        assert "exit_code=0" in output
        assert "ran:printf lab" in output
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_bootstrap_promotes_ssh_pending_host() -> None:
    state = EngagementState(
        engagement_id="eng-1",
        hosts={
            "target": HostRuntime(
                transport=Transport.SSH_PENDING,
                address="10.0.0.5",
                user="ubuntu",
            )
        },
    )
    mock_bootstrap = AsyncMock(
        return_value=(
            "http://127.0.0.1:8765",
            state.set_runner("target", "http://127.0.0.1:8765"),
        )
    )

    server = ThreadingHTTPServer(("127.0.0.1", 0), _RunnerHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        endpoint = f"http://127.0.0.1:{port}"
        promoted = state.set_runner("target", endpoint)
        hosts = dict(promoted.hosts)
        hosts["target"] = hosts["target"].model_copy(update={"address": None})
        promoted = promoted.model_copy(update={"hosts": hosts})
        mock_bootstrap.return_value = (endpoint, promoted)

        output, new_state = asyncio.run(
            run_on_host(
                state,
                "target",
                "printf boot",
                _settings(),
                bootstrap_runner_fn=mock_bootstrap,
            )
        )
        mock_bootstrap.assert_awaited_once()
        assert new_state.hosts["target"].transport is Transport.RUNNER
        assert output.startswith("runner_ready: target")
        assert "exit_code=0" in output
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_bootstrap_builds_ssh_commands_before_health_check() -> None:
    from agent_redteam.core.exceptions import ConfigurationError

    state = EngagementState(
        engagement_id="eng-1",
        hosts={
            "jump": HostRuntime(
                transport=Transport.SSH_PENDING,
                address="jump.lab",
                user="ubuntu",
            ),
            "web": HostRuntime(
                transport=Transport.SSH_PENDING,
                address="10.0.0.8",
                user="ubuntu",
                via=["jump"],
            ),
        },
    )
    calls: list[list[str]] = []

    async def fake_run(command: list[str]) -> int:
        calls.append(command)
        joined = " ".join(command)
        if "/health" in joined:
            return 1
        return 0

    with pytest.raises(ConfigurationError, match="health"):
        asyncio.run(
            bootstrap_runner(
                host_id="web",
                host=state.hosts["web"],
                state=state,
                settings=_settings(),
                resolve_via=lambda host_id: state.hosts[host_id],
                run_command=fake_run,
            )
        )

    assert calls
    assert all("ssh" in " ".join(command) or "scp" in " ".join(command) for command in calls)
