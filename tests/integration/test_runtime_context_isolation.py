"""Integration tests: RuntimeContext isolation — verify no cross-context leakage."""

import json
import shutil
from pathlib import Path

from evidence_agent.runtime import RuntimeContext, clear_current_context, use_context

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
SAMPLE_PDF = FIXTURES_DIR / "sample_article.pdf"


def _setup_ctx_with_pdf(tmp_path: Path, name: str) -> RuntimeContext:
    """Create a RuntimeContext and import a sample PDF into it."""
    ws = tmp_path / f"ctx-{name}"
    ws.mkdir()
    ctx = RuntimeContext(str(ws))
    ctx.ensure_directories()

    from evidence_agent.database.migrations import migrate
    migrate(ctx.db_path)

    pdf_dir = ctx.sources_dir / "SRC-iso-test"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    orig_dir = pdf_dir / "original"
    orig_dir.mkdir(exist_ok=True)
    if SAMPLE_PDF.exists():
        shutil.copy(SAMPLE_PDF, orig_dir / "main.pdf")
    (pdf_dir / "manifest.json").write_text(json.dumps({
        "source_id": "SRC-iso-test", "source_type": "journal_article",
        "title": "Isolation Test", "original_file_sha256": f"sha:{name}",
        "created_at": "2025-01-01T00:00:00", "updated_at": "2025-01-01T00:00:00",
    }))

    return ctx


def _source_count(ctx: RuntimeContext) -> int:
    """Count sources in ctx's database."""
    import sqlite3
    conn = sqlite3.connect(str(ctx.db_path))
    conn.row_factory = sqlite3.Row
    count = conn.execute("SELECT COUNT(*) as c FROM sources").fetchone()["c"]
    conn.close()
    return count


class TestContextIsolation:
    """Verify ingest and DB operations don't leak between contexts."""

    def test_ingest_isolated_between_contexts(self, tmp_path):
        """ctx A import → ctx B has 0 sources."""
        clear_current_context()
        ctx_a = _setup_ctx_with_pdf(tmp_path, "a")
        ctx_b = _setup_ctx_with_pdf(tmp_path, "b")

        with use_context(ctx_a):
            from evidence_agent.ingest.files import import_pdf
            import_pdf(SAMPLE_PDF)
            assert _source_count(ctx_a) > 0

        with use_context(ctx_b):
            assert _source_count(ctx_b) == 0, (
                "ctx B should have 0 sources — ctx A's import leaked!"
            )
        clear_current_context()

    def test_ingest_isolation_reverse_order(self, tmp_path):
        """B→A then A→B — each context is independent."""
        clear_current_context()
        ctx_a = _setup_ctx_with_pdf(tmp_path, "a")
        ctx_b = _setup_ctx_with_pdf(tmp_path, "b")

        # Import in B first
        with use_context(ctx_b):
            from evidence_agent.ingest.files import import_pdf
            import_pdf(SAMPLE_PDF)

        # Then import in A
        with use_context(ctx_a):
            from evidence_agent.ingest.files import import_pdf
            import_pdf(SAMPLE_PDF)

        # Each should have exactly 1 source
        with use_context(ctx_a):
            assert _source_count(ctx_a) == 1
        with use_context(ctx_b):
            assert _source_count(ctx_b) == 1
        clear_current_context()

    def test_ingest_isolation_repeated_switch(self, tmp_path):
        """A→B→A — no cross-contamination with repeated switches."""
        clear_current_context()
        ctx_a = _setup_ctx_with_pdf(tmp_path, "a")
        ctx_b = _setup_ctx_with_pdf(tmp_path, "b")

        with use_context(ctx_a):
            from evidence_agent.ingest.files import import_pdf
            import_pdf(SAMPLE_PDF)

        with use_context(ctx_b):
            assert _source_count(ctx_b) == 0
            from evidence_agent.ingest.files import import_pdf
            import_pdf(SAMPLE_PDF)

        with use_context(ctx_a):
            assert _source_count(ctx_a) == 1, "ctx A leaked to B or duplicated"

        clear_current_context()

    def test_ab_db_isolation(self, tmp_path):
        """Two contexts have independent databases."""
        clear_current_context()
        ctx_a = RuntimeContext(str(tmp_path / "a"))
        ctx_a.ensure_directories()
        ctx_b = RuntimeContext(str(tmp_path / "b"))
        ctx_b.ensure_directories()

        from evidence_agent.database.migrations import migrate
        migrate(ctx_a.db_path)
        migrate(ctx_b.db_path)

        # Insert into A only
        import sqlite3
        conn_a = sqlite3.connect(str(ctx_a.db_path))
        conn_a.execute("INSERT INTO sources (source_id,source_type,title,authors_json,original_file_sha256,origin_scope,scientific_verification_status,created_at,updated_at) VALUES ('SRC-A','journal_article','A','[]','sha:a','external','unverified','2025-01-01T00:00:00','2025-01-01T00:00:00')")
        conn_a.commit()
        conn_a.close()

        # B should still be empty
        conn_b = sqlite3.connect(str(ctx_b.db_path))
        conn_b.row_factory = sqlite3.Row
        count_b = conn_b.execute("SELECT COUNT(*) as c FROM sources").fetchone()["c"]
        conn_b.close()
        assert count_b == 0, f"DB B has {count_b} sources, expected 0"

        clear_current_context()
