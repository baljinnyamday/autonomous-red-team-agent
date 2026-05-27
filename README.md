# Agent Red Team (`be`)

Python backend for **authorized agentic red teaming**: multi-agent orchestration, scoped targets, and structured run reporting inside a controlled environment.

## Requirements

- Python 3.13+ ([`.python-version`](.python-version))
- [uv](https://docs.astral.sh/uv/) for dependencies and commands

## Quick start

```bash
cd be
cp .env.example .env
# Set AUTHORIZED_ENGAGEMENT=true and scope variables before running anything.

uv sync --all-groups
uv run redteam --help
```

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

This codebase is intended **only** for engagements with explicit written authorization. See [docs/authorized-use.md](docs/authorized-use.md). Runtime guardrails in `guardrails/` enforce scope before agents execute.
