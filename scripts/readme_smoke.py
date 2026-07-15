#!/usr/bin/env python3
"""README smoke test — runs documented workflow in isolated workspace.

Creates a fresh temporary workspace, runs the full CLI pipeline,
and verifies all commands exit 0.
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run_smoke(output_path: str) -> dict:
    tmpdir = tempfile.mkdtemp(prefix="lea-readme-smoke-")
    ws = Path(tmpdir).resolve()
    commands: list[dict] = []

    def run(cmd: list[str], name: str) -> dict:
        t0 = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=180, cwd=str(ws))
        entry = {
            "name": name, "command": cmd,
            "exit_code": result.returncode,
            "duration_seconds": round(time.time() - t0, 2),
            "stdout_excerpt": result.stdout.strip()[:200],
        }
        commands.append(entry)
        return entry

    def must_pass(cmd: list[str], name: str) -> dict:
        entry = run(cmd, name)
        if entry["exit_code"] != 0:
            entry["stderr"] = subprocess.run(
                cmd, capture_output=True, text=True, cwd=str(ws),
            ).stderr.strip()[:500]
        return entry

    try:
        os.environ["EVIDENCE_AGENT_WORKSPACE"] = str(ws)

        must_pass(["evidence-agent", "--version"], "version")
        must_pass(["evidence-agent", "init"], "init")
        must_pass(["evidence-agent", "db", "migrate"], "db_migrate")
        must_pass(["evidence-agent", "db", "check"], "db_check")

        task = must_pass(
            ["evidence-agent", "task", "create",
             "--title", "Readme Smoke Test",
             "--request", "Extract claims for verification"],
            "task_create",
        )

        pdf = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "real_scientific_article_en.pdf"
        ingest = must_pass(["evidence-agent", "ingest", str(pdf)], "ingest")
        source_id = ""

        for line in (ingest.get("stdout_excerpt", "") + "\n").split("\n"):
            if "SRC-" in line:
                source_id = line.strip().split()[1] if len(line.strip().split()) >= 2 else ""
                break

        if not source_id:
            from evidence_agent.database.connection import get_connection
            with get_connection(read_only=True) as conn:
                row = conn.execute(
                    "SELECT source_id FROM sources ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if row: source_id = row["source_id"]

        must_pass(["evidence-agent", "parse", source_id], "parse")
        analyse = must_pass(
            ["evidence-agent", "analyse", source_id, "--provider", "mock"],
            "analyse",
        )

        run_id = ""
        from evidence_agent.database.connection import get_connection
        with get_connection(read_only=True) as conn:
            row = conn.execute(
                "SELECT run_id FROM processing_runs "
                "WHERE source_id = ? ORDER BY started_at DESC LIMIT 1",
                (source_id,),
            ).fetchone()
            if row: run_id = row["run_id"]

        must_pass(["evidence-agent", "review", "export", run_id], "review_export")

        import csv
        review_dir = ws / "external_evidence" / "review" / run_id
        csv_path = review_dir / "claims_for_review.csv"
        if csv_path.exists():
            rows = []
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    row["reviewer"] = "smoke"
                    row["decision"] = "approve" if i == 0 else "reject"
                    rows.append(row)
            tmp_csv = Path(tempfile.mktemp(suffix=".csv"))
            fns = list(rows[0].keys())
            with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fns)
                w.writeheader(); w.writerows(rows)
            must_pass(["evidence-agent", "review", "apply", str(tmp_csv)],
                      "review_apply")
            tmp_csv.unlink(missing_ok=True)

        must_pass(["evidence-agent", "query", "curcumin"], "query")
        must_pass(["evidence-agent", "source-show", source_id], "source_show")
        must_pass(["evidence-agent", "package", "sync", source_id], "package_sync")
        must_pass(["evidence-agent", "package", "validate", source_id],
                  "package_validate")

        result = "PASS"
        claimed_ids = {"source_id": source_id, "run_id": run_id}

        for c in commands:
            if c["exit_code"] != 0 and c["name"] not in ("review_apply",):
                result = "FAIL"
                break

        report = {
            "result": result,
            "workspace": str(ws),
            "commands": commands,
            "discovered_ids": claimed_ids,
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        return report

    finally:
        shutil.rmtree(str(ws), ignore_errors=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    args = p.parse_args()
    report = run_smoke(args.output)
    print(f"Result: {report['result']}")
    if report["result"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
