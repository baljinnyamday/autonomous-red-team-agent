# Agent Red Team (`be`)

Python backend for **authorized agentic red teaming**: multi-agent orchestration, scoped targets, and structured run reporting inside a controlled environment.

## Requirements

- Python 3.13+ ([`.python-version`](.python-version))
- [uv](https://docs.astral.sh/uv/) for dependencies and commands

## Quick start

```bash
cd be
cp .env.example .env
# Set AUTHORIZED_ENGAGEMENT=true before running anything.

uv sync --all-groups
uv run redteam --help
uv run main.py --help
```

`uv run main.py` starts the simple agent loop. Its default config uses the OpenAI
Responses provider (`AGENT_PROVIDER=openai`) and registers the local `bash` tool.
Set `OPENAI_API_KEY` and `AUTHORIZED_ENGAGEMENT=true` in `.env` before running
an agent task. Describe hosts and scope in the task prompt or engagement metadata.
Interactive `main.py` sessions keep chat history for the current process and write
observable user, assistant, tool, and usage events under `AUDIT_LOG_PATH` using
dated per-run logs like `.runs/YYYY-MM-DD/analytics/run-0001.jsonl`.
Inside an interactive session, run `/analysis` to see current-session token usage,
prompt-cache hit rate, and chat-history counts without sending a task to the model.

Use `uv run redteam replay .runs` to inspect the latest saved transcript and
`uv run redteam usage .runs` to summarize input/output tokens, cached
input tokens, and prompt-cache hit rate.

## Editor setup

Cursor and VS Code read the workspace settings in `.vscode/`. After `uv sync --all-groups`,
install the recommended extensions when prompted, then use **Tasks: Run Task** for
`quality: all`, `ruff: fix`, or `ty: check`.

## Layout

```
be/
├── src/agent_redteam/     # Application package (src layout)
│   ├── agents/            # Agent roles, prompts, tool bindings
│   ├── api/               # HTTP API (versioned routes)
│   ├── cli/               # `redteam` CLI entry point
│   ├── core/              # Config, logging, shared exceptions
│   ├── guardrails/        # Authorization and in-scope enforcement
│   ├── orchestration/     # Multi-agent workflows and guardrail enforcement
│   ├── schemas/           # Shared Pydantic DTOs
│   ├── targets/           # Authorized target definitions
│   └── techniques/        # Technique / playbook registry
├── scripts/               # Operational helpers (non-package)
└── docs/                  # Architecture and authorized-use policy
```

## Authorized use

This codebase is intended **only** for engagements with explicit written authorization. See [docs/authorized-use.md](docs/authorized-use.md). Runtime guardrails in `guardrails/` require explicit authorization before agents execute.
