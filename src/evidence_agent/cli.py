"""CLI entry point for the Literature Evidence Agent."""

import typer

app = typer.Typer(
    name="evidence-agent",
    help="文献证据 Agent — 文献主张提取与人工复核系统",
    no_args_is_help=True,
)


@app.command()
def init() -> None:
    """Initialize the workspace directory structure."""
    from evidence_agent.config import config

    config.ensure_directories()
    typer.echo(f"Workspace initialized at: {config.workspace_path}")
    typer.echo(f"Database path: {config.db_path}")


@app.command()
def version() -> None:
    """Show version information."""
    typer.echo("literature-evidence-agent v0.1.0")


# Sub-command groups (stubs for now)
db_app = typer.Typer(help="Database management commands")
app.add_typer(db_app, name="db")


@db_app.command()
def migrate() -> None:
    """Run database migrations."""
    typer.echo("DB migrate (not yet implemented)")


@db_app.command()
def check() -> None:
    """Check database integrity."""
    typer.echo("DB check (not yet implemented)")


@db_app.command()
def rebuild() -> None:
    """Rebuild database from source packages."""
    typer.echo("DB rebuild (not yet implemented)")


if __name__ == "__main__":
    app()
