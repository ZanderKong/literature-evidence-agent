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
    from evidence_agent.runtime import get_current_context

    ctx = get_current_context()
    ctx.ensure_directories()
    typer.echo(f"Workspace initialized at: {ctx.workspace_path}")
    typer.echo(f"Database path: {ctx.db_path}")


@app.command()
def version() -> None:
    """Show version information."""
    typer.echo("literature-evidence-agent v0.1.0")


# ── Task sub-commands ──────────────────────────────────

task_app = typer.Typer(help="Research task management commands")
app.add_typer(task_app, name="task")


@task_app.command()
def create(
    title: str = typer.Option(..., "--title", "-t", help="Task title"),
    request: str = typer.Option(..., "--request", "-r", help="User request"),
    background: str = typer.Option(None, "--background", "-b", help="Research background"),
    mode: str = typer.Option("analyse_uploaded", "--mode", "-m", help="Task mode"),
    depth: str = typer.Option("task_focused", "--depth", "-d", help="Analysis depth"),
) -> None:
    """Create a new research task."""
    from evidence_agent.database.repositories import create_task

    try:
        result = create_task(title, request, background, mode, depth)
        typer.echo(f"Created task: {result['task_id']}")
        typer.echo(f"  Title: {result['title']}")
        typer.echo(f"  Mode: {result['task_mode']}")
        typer.echo(f"  Depth: {result['analysis_depth']}")
        typer.echo(f"  Status: {result['status']}")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=2) from e


@task_app.command()
def show(task_id: str) -> None:
    """Show details of a research task."""
    from evidence_agent.database.repositories import get_task

    task = get_task(task_id)
    if task is None:
        typer.echo(f"Task not found: {task_id}", err=True)
        raise typer.Exit(code=2)
    typer.echo(json.dumps(task, indent=2, default=str))


@task_app.command()
def list(
    status: str = typer.Option(None, "--status", "-s", help="Filter by status"),
) -> None:
    """List research tasks."""
    from evidence_agent.database.repositories import list_tasks

    tasks = list_tasks(status=status)
    if not tasks:
        typer.echo("No tasks found.")
    for t in tasks:
        typer.echo(
            f"[{t['task_id']}] {t['status']:10s} {t['title'][:50]}"
        )


# ── Database sub-commands ──────────────────────────────

db_app = typer.Typer(help="Database management commands")
app.add_typer(db_app, name="db")


@db_app.command()
def migrate() -> None:
    """Run database migrations."""
    from evidence_agent.database.migrations import migrate as run_migrate
    from evidence_agent.runtime import get_current_context

    ctx = get_current_context()
    ctx.ensure_directories()

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
def rebuild_from_packages(
    source: str = typer.Option(None, "--source", help="Sources directory"),
    target: str = typer.Option(None, "--target", help="Target database path"),
) -> None:
    """Rebuild database from all source packages."""
    from pathlib import Path as _Path

    from evidence_agent.database.rebuild import rebuild_from_packages

    src_dir = _Path(source) if source else None
    tgt = _Path(target) if target else None
    try:
        report = rebuild_from_packages(source_dir=src_dir, target_db=tgt)
        typer.echo(json.dumps(report, indent=2, default=str))
    except Exception as e:
        typer.echo(f"Rebuild failed: {e}", err=True)
        raise typer.Exit(code=3) from e


@db_app.command()
def reset() -> None:
    """Drop all tables and re-run migrations (DESTRUCTIVE)."""
    from evidence_agent.database.migrations import rebuild as run_rebuild
    typer.echo("WARNING: Drops all data!")
    ans = input("Continue? [y/N] ").strip().lower()
    if ans not in ("y", "yes"):
        typer.echo("Aborted.")
        raise typer.Exit(code=0)
    try:
        applied = run_rebuild()
        typer.echo(f"Reset: {len(applied)} migrations applied")
    except Exception as e:
        typer.echo(f"Reset failed: {e}", err=True)
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
    from evidence_agent.parsers.pdf import parse_pdf
    from evidence_agent.runtime import get_current_context

    ctx = get_current_context()
    package_dir = ctx.sources_dir / source_id

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


# ── Review sub-commands ────────────────────────────────

review_app = typer.Typer(help="Review management commands")
app.add_typer(review_app, name="review")


@review_app.command()
def export(run_id: str) -> None:
    """Export a review packet for a processing run."""
    from evidence_agent.review.packet import generate_review_packet

    try:
        paths = generate_review_packet(run_id)
        typer.echo(f"Review packet: {paths['csv']}")
        for k, v in paths.items():
            typer.echo(f"  {k}: {v}")
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=6) from e
    except Exception as e:
        typer.echo(f"Review export failed: {e}", err=True)
        raise typer.Exit(code=6) from e


@review_app.command()
def apply(csv_file: str) -> None:
    """Apply review decisions from a CSV file."""
    from pathlib import Path

    from evidence_agent.review.decisions import apply_review_csv

    try:
        report = apply_review_csv(Path(csv_file))
        typer.echo(json.dumps(report, indent=2))
    except Exception as e:
        typer.echo(f"Review apply failed: {e}", err=True)
        raise typer.Exit(code=6) from e


# ── Query command ──────────────────────────────────────

@app.command()
def query(keywords: str) -> None:
    """Search approved claims by keywords."""
    from evidence_agent.search.fts import search_claims

    try:
        results = search_claims(keywords)
        for r in results:
            typer.echo(
                f"[{r['claim_id']}] {r['claim_type']} | "
                f"{r['source_quote'][:80]}..."
            )
            typer.echo(
                f"  Source: {r['source_id']} Page: {r.get('page', 'N/A')} "
                f"| {r.get('_note', '')}"
            )
        if not results:
            typer.echo("No results found.")
    except Exception as e:
        typer.echo(f"Query failed: {e}", err=True)
        raise typer.Exit(code=1) from e


# ── Export commands ────────────────────────────────────

@app.command()
def export_source(
    source_id: str,
    output_format: str = "markdown",
    include_pending: bool = False,
) -> None:
    """Export a source's approved claims."""
    from evidence_agent.exports.markdown import (
        export_source_jsonl,
        export_source_markdown,
    )
    from evidence_agent.runtime import get_current_context

    ctx = get_current_context()
    exports_dir = ctx.exports_dir
    exports_dir.mkdir(parents=True, exist_ok=True)

    try:
        if output_format == "markdown":
            path = exports_dir / f"{source_id}.md"
            export_source_markdown(source_id, path, include_pending)
            typer.echo(f"Exported: {path}")
        elif output_format == "jsonl":
            path = exports_dir / f"{source_id}.jsonl"
            export_source_jsonl(source_id, path, include_pending)
            typer.echo(f"Exported: {path}")
        else:
            typer.echo(f"Unknown format: {output_format}")
            raise typer.Exit(code=2)
    except Exception as e:
        typer.echo(f"Export failed: {e}", err=True)
        raise typer.Exit(code=1) from e


# ── Verify command ─────────────────────────────────────

@app.command()
def analyse(
    source_id: str,
    task: str = typer.Option(None, "--task", help="Task ID to associate"),
    provider: str = typer.Option(None, "--provider", help="Provider: mock|deepseek"),
) -> None:
    """Run full analysis pipeline on a source."""
    from evidence_agent.application.analyse import analyse_source

    try:
        result = analyse_source(source_id, task, provider)
        typer.echo(json.dumps(result, indent=2, default=str))
        if result["status"] == "failed":
            raise typer.Exit(code=5)
    except ValueError as e:
        typer.echo(f"Analysis failed: {e}", err=True)
        raise typer.Exit(code=2) from e
    except Exception as e:
        typer.echo(f"Analysis failed: {e}", err=True)
        raise typer.Exit(code=5) from e


@app.command()
def source_show(source_id: str) -> None:
    """Show source details."""
    import json as _json

    from evidence_agent.database.connection import get_connection
    with get_connection(read_only=True) as conn:
        cursor = conn.execute("SELECT * FROM sources WHERE source_id=?", (source_id,))
        row = cursor.fetchone()
        if not row:
            typer.echo(f"Source not found: {source_id}", err=True)
            raise typer.Exit(code=2)
        typer.echo(_json.dumps(dict(row), indent=2, default=str))


@app.command()
def claim_show(claim_id: str) -> None:
    """Show claim details."""
    import json as _json

    from evidence_agent.database.connection import get_connection
    with get_connection(read_only=True) as conn:
        cursor = conn.execute(
            "SELECT c.*, l.page, l.figure_label, l.table_label "
            "FROM source_claims c "
            "LEFT JOIN claim_locators l ON c.claim_id = l.claim_id "
            "WHERE c.claim_id=?", (claim_id,))
        row = cursor.fetchone()
        if not row:
            typer.echo(f"Claim not found: {claim_id}", err=True)
            raise typer.Exit(code=2)
        typer.echo(_json.dumps(dict(row), indent=2, default=str))


@app.command()
def run_show(run_id: str) -> None:
    """Show processing run details."""
    import json as _json

    from evidence_agent.database.connection import get_connection
    with get_connection(read_only=True) as conn:
        cursor = conn.execute(
            "SELECT * FROM processing_runs WHERE run_id=?", (run_id,))
        row = cursor.fetchone()
        if not row:
            typer.echo(f"Run not found: {run_id}", err=True)
            raise typer.Exit(code=2)
        typer.echo(_json.dumps(dict(row), indent=2, default=str))


@app.command()
def verify(round_name: str = "round1") -> None:
    """Run verification checks."""
    if round_name == "round1":
        _verify_round1()
    else:
        typer.echo(f"Unknown verification: {round_name}")
        raise typer.Exit(code=7)


def _verify_round1() -> None:
    """Run Round 1 verification with real behavioral checks."""
    from evidence_agent.verification.round1 import run_round1_verification

    report = run_round1_verification()

    for check in report.checks:
        status = check["status"]
        name = check["name"]
        evidence = check.get("evidence", "")
        reason = check.get("reason", "")
        if status == "PASS":
            typer.echo(
                f"{name}=PASS duration_ms={check['duration_ms']} "
                f"evidence={evidence}"
            )
        else:
            typer.echo(
                f"{name}=FAIL duration_ms={check['duration_ms']} "
                f"reason={reason} evidence={evidence}"
            )

    if report.all_pass:
        typer.echo("ROUND1_VERIFICATION=PASS")
        raise typer.Exit(code=0)
    else:
        typer.echo("ROUND1_VERIFICATION=FAIL")
        raise typer.Exit(code=7)


if __name__ == "__main__":
    app()
