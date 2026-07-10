"""CLI entry point for the Literature Evidence Agent."""

import json

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


# ── Database sub-commands ──────────────────────────────

db_app = typer.Typer(help="Database management commands")
app.add_typer(db_app, name="db")


@db_app.command()
def migrate() -> None:
    """Run database migrations."""
    from evidence_agent.config import config
    from evidence_agent.database.migrations import migrate as run_migrate

    config.ensure_directories()

    try:
        applied = run_migrate()
        if applied:
            for version, name in applied:
                typer.echo(f"Applied migration {version}: {name}")
            typer.echo(f"Total: {len(applied)} migration(s) applied")
        else:
            typer.echo("No pending migrations.")
    except Exception as e:
        typer.echo(f"Migration failed: {e}", err=True)
        raise typer.Exit(code=3) from e


@db_app.command()
def check() -> None:
    """Check database integrity."""
    from evidence_agent.database.migrations import check as run_check

    try:
        results = run_check()
        typer.echo(json.dumps(results, indent=2, default=str))
        if results["errors"]:
            raise typer.Exit(code=3)
    except Exception as e:
        typer.echo(f"Database check failed: {e}", err=True)
        raise typer.Exit(code=3) from e


@db_app.command()
def rebuild() -> None:
    """Rebuild database from source packages (destructive, re-runs all migrations)."""
    from evidence_agent.database.migrations import rebuild as run_rebuild

    typer.echo("WARNING: This will drop all existing data!")
    typer.echo("Continue? [y/N] ", nl=False)
    answer = input().strip().lower()
    if answer not in ("y", "yes"):
        typer.echo("Aborted.")
        raise typer.Exit(code=0)

    try:
        applied = run_rebuild()
        typer.echo(f"Rebuilt: {len(applied)} migration(s) applied")
    except Exception as e:
        typer.echo(f"Rebuild failed: {e}", err=True)
        raise typer.Exit(code=3) from e


@app.command()
def ingest(file: str) -> None:
    """Import a local PDF as an external source."""
    from pathlib import Path

    from evidence_agent.ingest.files import import_pdf

    file_path = Path(file).resolve()

    try:
        result = import_pdf(file_path)
        if result["is_new"]:
            typer.echo(f"Imported: {result['source_id']}")
        else:
            typer.echo(f"Already imported: {result['source_id']}")
        typer.echo(f"  Package: {result['package_dir']}")
        typer.echo(f"  SHA-256: {result['sha256']}")
        typer.echo(f"  Size: {result['file_size']} bytes")
    except (ValueError, RuntimeError) as e:
        typer.echo(f"Import failed: {e}", err=True)
        raise typer.Exit(code=2) from e


@app.command()
def parse(source_id: str) -> None:
    """Parse an imported PDF source."""
    from evidence_agent.config import config
    from evidence_agent.parsers.pdf import parse_pdf

    package_dir = config.sources_dir / source_id

    if not package_dir.exists():
        typer.echo(f"Source not found: {source_id}", err=True)
        raise typer.Exit(code=2)

    try:
        result = parse_pdf(source_id, package_dir)
        typer.echo(f"Parsed {source_id}")
        typer.echo(f"  Pages: {result['quality']['total_pages']}")
        typer.echo(f"  Sections: {result['quality'].get('section_count', len(result['sections']))}")
        typer.echo(f"  Low text density: {result['quality']['is_low_text_density']}")
        for name, path in result["output_paths"].items():
            typer.echo(f"  {name}: {path}")
    except FileNotFoundError as e:
        typer.echo(f"Parse failed: {e}", err=True)
        raise typer.Exit(code=4) from e
    except Exception as e:
        typer.echo(f"Parse failed: {e}", err=True)
        raise typer.Exit(code=4) from e


if __name__ == "__main__":
    app()
