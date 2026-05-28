import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from agent_redteam import __version__
from agent_redteam.cli.render import (
    load_audit,
    print_usage_summary,
    render_audit,
    usage_summary_from_audit,
)
from agent_redteam.core.logging import configure_logging
from agent_redteam.orchestration.workflow import EngagementWorkflow

app = typer.Typer(
    name="redteam",
    help="Authorized agentic red teaming CLI.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    configure_logging()


@app.command()
def version() -> None:
    typer.echo(__version__)


@app.command()
def replay(
    audit_log: Annotated[
        Path,
        typer.Argument(
            help="Path to a raw audit JSONL file.",
            exists=True,
            dir_okay=False,
        ),
    ] = Path(".runs/audit.jsonl"),
) -> None:
    """Pretty-print a recorded agent run from its raw audit log."""
    render_audit(load_audit(audit_log))


@app.command()
def usage(
    audit_log: Annotated[
        Path,
        typer.Argument(
            help="Path to a raw audit JSONL file.",
            exists=True,
            dir_okay=False,
        ),
    ] = Path(".runs/audit.jsonl"),
) -> None:
    """Summarize token usage and prompt-cache hit rate from an audit log."""
    console = Console()
    summary = usage_summary_from_audit(load_audit(audit_log))
    if summary.requests == 0:
        console.print("[yellow]No usage events found.[/yellow]")
        return
    print_usage_summary(console, summary)


@app.command()
def run(
    engagement_id: str = typer.Option(..., help="Engagement identifier for audit logs."),
    operator: str = typer.Option("cli", help="Operator identity."),
) -> None:
    """Run the default planner → executor → reporter workflow."""
    workflow = EngagementWorkflow()

    async def _run() -> dict[str, object]:
        return await workflow.run(engagement_id)

    try:
        result = asyncio.run(_run())
        typer.echo(result)
    except Exception as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
