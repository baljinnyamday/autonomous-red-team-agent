import asyncio

import typer

from agent_redteam import __version__
from agent_redteam.core.logging import configure_logging
from agent_redteam.services.engagement_service import EngagementService

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
def run(
    engagement_id: str = typer.Option(..., help="Engagement identifier for audit logs."),
    target: str = typer.Option(..., help="In-scope target host or URL."),
    operator: str = typer.Option("cli", help="Operator identity."),
) -> None:
    """Run the default planner → executor → reporter workflow."""
    service = EngagementService()

    async def _run() -> dict[str, object]:
        return await service.run(engagement_id, target)

    try:
        result = asyncio.run(_run())
        typer.echo(result)
    except Exception as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
