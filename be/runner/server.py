#!/usr/bin/env python3
"""Minimal authorized-lab HTTP runner for remote exec."""

from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from policy import RM_COMMAND_WARNING, contains_rm_command

POLICY_DENIED_EXIT_CODE = 126

DEFAULT_PORT = 8765
DEFAULT_BIND = "127.0.0.1"
DEFAULT_EXEC_TIMEOUT_SECONDS = 3600.0
HTTP_CLIENT_BUFFER_SECONDS = 30.0


class RunnerHandler(BaseHTTPRequestHandler):
    server_version = "AgentRunner/0.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/health":
            self.send_response(200)
            self.end_headers()
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/exec":
            self.send_error(404)
            return
        if not self._authorized():
            self.send_error(401)
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode())
        except json.JSONDecodeError:
            self.send_error(400)
            return

        command = payload.get("command")
        if not isinstance(command, str) or not command.strip():
            self.send_error(400)
            return

        timeout_seconds = _resolve_exec_timeout(payload)
        result = _run_command(command, timeout_seconds=timeout_seconds)
        encoded = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _authorized(self) -> bool:
        expected = _load_runner_token()
        if not expected:
            return False
        header = self.headers.get("Authorization", "")
        return header == f"Bearer {expected}"


def _load_runner_token() -> str:
    token_file = os.environ.get("RUNNER_TOKEN_FILE", "").strip()
    if token_file:
        return Path(token_file).read_text(encoding="utf-8").strip()
    return os.environ.get("ENGAGEMENT_RUNNER_TOKEN", "").strip()


def _resolve_exec_timeout(payload: dict[str, object]) -> float | None:
    request_timeout = payload.get("timeout_seconds")
    if isinstance(request_timeout, (int, float)) and request_timeout > 0:
        return float(request_timeout)

    env_default = os.environ.get("RUNNER_EXEC_TIMEOUT_SECONDS", "").strip()
    if env_default:
        return float(env_default)
    return DEFAULT_EXEC_TIMEOUT_SECONDS


def _run_command(command: str, *, timeout_seconds: float | None) -> dict[str, object]:
    if contains_rm_command(command):
        return {
            "exit_code": POLICY_DENIED_EXIT_CODE,
            "stdout": "",
            "stderr": RM_COMMAND_WARNING,
            "timed_out": False,
        }

    try:
        completed = subprocess.run(
            ["bash", "-lc", command],
            capture_output=True,
            text=False,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "exit_code": completed.returncode,
            "stdout": completed.stdout.decode("utf-8", errors="replace"),
            "stderr": completed.stderr.decode("utf-8", errors="replace"),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": None,
            "stdout": exc.stdout.decode("utf-8", errors="replace") if exc.stdout else "",
            "stderr": exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "",
            "timed_out": True,
        }


def main() -> None:
    port = int(os.environ.get("RUNNER_PORT", DEFAULT_PORT))
    bind = os.environ.get("RUNNER_BIND", DEFAULT_BIND)
    server = ThreadingHTTPServer((bind, port), RunnerHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
