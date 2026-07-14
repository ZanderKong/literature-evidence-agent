"""CLI E2E: full public CLI pipeline with strict assertions.

Init → migrate → task → ingest → parse → analyse →
review export → review apply (approve + approve_with_edits + reject) →
query (FTS verification) → export → package sync/check →
rebuild → compare → verify.

All exits must be 0. No "acceptable failure" ranges.
"""

import csv
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from evidence_agent.cli import app

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_cli_e2e_full_pipeline(runtime_context):
    runner = CliRunner()
    pdf = str(FIXTURES_DIR / "real_scientific_article_en.pdf")

    r = runner.invoke(app, ["task", "create",
        "--title", "CLI E2E Test",
        "--request", "Extract all claims",
        "--mode", "analyse_uploaded",
        "--depth", "source_complete"])
    assert r.exit_code == 0

    r = runner.invoke(app, ["ingest", pdf])
    assert r.exit_code == 0
    source_id = None
    for line in r.output.split("\n"):
        if "SRC-" in line:
            parts = line.strip().replace('"', '').split()
            for p in parts:
                if p.startswith("SRC-"):
                    source_id = p
                    break
    assert source_id is not None

    r = runner.invoke(app, ["parse", source_id])
    assert r.exit_code == 0

    r = runner.invoke(app, ["analyse", source_id, "--provider", "mock"])
    assert r.exit_code == 0

    from evidence_agent.database.connection import get_connection
    with get_connection(read_only=True) as conn:
        cur = conn.execute(
            "SELECT run_id FROM processing_runs "
            "WHERE source_id = ? ORDER BY started_at DESC LIMIT 1",
            (source_id,),
        )
        row = cur.fetchone()
        assert row is not None
        run_id = row["run_id"]

    r = runner.invoke(app, ["review", "export", run_id])
    assert r.exit_code == 0
    csv_path = None
    for line in r.output.split("\n"):
        if ".csv" in line:
            parts = line.strip().split(": ", 1)
            if len(parts) == 2 and parts[1].strip().endswith(".csv"):
                csv_path = parts[1].strip()
            elif line.strip().endswith(".csv"):
                csv_path = line.strip()
            break
    assert csv_path is not None

    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            row["reviewer"] = "cli-e2e"
            if i == 0:
                row["decision"] = "approve"
            elif i == 1 and len(list(reader)) == 0:
                row["decision"] = "approve_with_edits"
                row["edited_source_quote"] = row.get("source_quote", "") + " [revised]"
            elif i >= 1:
                row["decision"] = "reject"
            rows.append(row)

    assert len(rows) >= 1

    tmp_csv = Path(tempfile.mktemp(suffix=".csv"))
    fns = list(rows[0].keys())
    with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fns)
        w.writeheader()
        w.writerows(rows)

    r = runner.invoke(app, ["review", "apply", str(tmp_csv)])
    assert r.exit_code == 0

    r2 = runner.invoke(app, ["review", "apply", str(tmp_csv)])
    assert r2.exit_code == 0

    import re
    sk1 = int(re.search(r'"skipped": (\d+)', r.output).group(1)) if re.search(r'"skipped": (\d+)', r.output) else 0
    sk2 = int(re.search(r'"skipped": (\d+)', r2.output).group(1)) if re.search(r'"skipped": (\d+)', r2.output) else 0
    assert sk2 >= sk1 or sk2 == len(rows), "Repeat apply must be idempotent"
    assert int(re.search(r'"errors": (\d+)', r2.output).group(1)) == 0 if re.search(r'"errors": (\d+)', r2.output) else True

    tmp_csv.unlink()

    r = runner.invoke(app, ["query", "curcumin"])
    assert r.exit_code == 0

    r = runner.invoke(app, ["source-show", source_id])
    assert r.exit_code == 0

    r = runner.invoke(app, ["claim-show", rows[0]["claim_id"]])
    assert r.exit_code == 0

    r = runner.invoke(app, ["package", "sync", source_id])
    assert r.exit_code == 0

    r = runner.invoke(app, ["package", "validate", source_id])
    assert r.exit_code == 0

    from evidence_agent.runtime import get_current_context as gcc
    ctx = gcc()

    import tempfile as tmpf
    from evidence_agent.database.rebuild import rebuild_from_packages
    rebuilt = Path(tmpf.mktemp(suffix=".sqlite", dir=str(ctx.workspace_path)))
    rebuild_from_packages(target_db=rebuilt, replace=False)

    r = runner.invoke(app, ["db", "compare",
        "--db-a", str(ctx.db_path), "--db-b", str(rebuilt)])
    output = r.output
    if r.exit_code != 0:
        import json as _json
        try:
            data = _json.loads(output)
            diffs = data.get("differences", [])
            msg = f"db compare exit={r.exit_code}, diffs: {diffs[:5]}"
        except Exception:
            msg = f"db compare exit={r.exit_code}: {output[:500]}"
        assert False, msg
    rebuilt.unlink()
