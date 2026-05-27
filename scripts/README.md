# Scripts

Operational helpers (database migrations, one-off exports, lab provisioning) live here.

Keep them outside `src/agent_redteam` so the installable package stays lean. Prefer `uv run python scripts/<name>.py`.
