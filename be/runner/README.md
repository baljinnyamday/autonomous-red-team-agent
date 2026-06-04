# Engagement runner (authorized lab use)

Minimal HTTP service that executes `bash -lc` on a remote host for the agent
`exec` tool. Intended only inside explicitly authorized red-team lab networks.

## Endpoints

- `GET /health` — liveness (no auth)
- `POST /exec` — JSON `{"command":"..."}` with header
  `Authorization: Bearer <ENGAGEMENT_RUNNER_TOKEN>`

Response: `{"exit_code", "stdout", "stderr", "timed_out"}`.

## Environment

| Variable | Purpose |
|----------|---------|
| `ENGAGEMENT_RUNNER_TOKEN` | Required bearer secret |
| `RUNNER_PORT` | Listen port (default `8765`) |
| `RUNNER_BIND` | Bind address (default `127.0.0.1`; bootstrap sets `0.0.0.0`) |
| `RUNNER_EXEC_TIMEOUT_SECONDS` | Optional per-command timeout |

## Run locally

From `be/` with the package on `PYTHONPATH`:

```bash
export ENGAGEMENT_RUNNER_TOKEN=dev-token
export RUNNER_PORT=8765
uv run python runner/server.py
```

The agent bootstraps this script onto `ssh_pending` hosts via internal SSH; the
model should call `exec(host=...)` only, never embed `ssh` in commands.
