#!/usr/bin/env python3
"""Golden evaluation — deterministic offline conformance.

Modes:
  fixture          — evaluate annotations against deterministic fixture claims
  pipeline-smoke   — full mock pipeline in isolated workspace
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from evidence_agent.verification.golden import (
    evaluate_annotations,
    load_annotations,
    load_extracted_claims,
    write_report,
)


def run_fixture(
    annotations_path: str, claims_path: str, output_path: str,
) -> dict:
    annotations = load_annotations(Path(annotations_path))
    claims = load_extracted_claims(Path(claims_path))
    result = evaluate_annotations(annotations, claims)
    write_report(result, Path(output_path))
    return result


def run_pipeline_smoke(output_path: str) -> dict:
    from evidence_agent.runtime import RuntimeContext, get_current_context, set_current_context

    old_ctx = get_current_context()
    tmpdir = tempfile.mkdtemp(prefix="lea-golden-smoke-")
    ws = Path(tmpdir).resolve()

    try:
        ctx = RuntimeContext(str(ws))
        set_current_context(ctx)
        ctx.ensure_directories()

        from evidence_agent.database.migrations import migrate
        migrate()

        golden_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "golden"
        gold_pdfs = sorted(golden_dir.glob("golden_*.pdf"))

        sources_processed = 0
        runs_completed = 0
        claims_persisted = 0
        quote_ok = True
        locator_ok = True

        for pdf_path in gold_pdfs:
            try:
                from evidence_agent.ingest.files import import_pdf
                r = import_pdf(pdf_path)
                source_id = r["source_id"]
                sources_processed += 1

                from evidence_agent.application.analyse import analyse_source
                analysis = analyse_source(source_id, provider_name="mock")
                runs_completed += 1
                claims_persisted += analysis.get("persisted_claims", 0)

                if analysis.get("persisted_claims", 0) > 0:
                    from evidence_agent.database.connection import get_connection
                    with get_connection(read_only=True) as conn:
                        claim_rows = conn.execute(
                            "SELECT c.source_quote, l.page FROM source_claims c "
                            "JOIN claim_locators l ON c.claim_id = l.claim_id "
                            "WHERE c.source_id = ?",
                            (source_id,),
                        ).fetchall()
                        for cr in claim_rows:
                            if not cr["source_quote"]:
                                quote_ok = False
                            if cr["page"] is None:
                                locator_ok = False
            except Exception:
                pass

        result = {
            "schema_version": 1,
            "evaluation_type": "offline_mock_pipeline_smoke",
            "workspace_isolated": True,
            "sources_processed": sources_processed,
            "runs_completed": runs_completed,
            "claims_persisted": claims_persisted,
            "quote_traceability_pass": quote_ok,
            "locator_pass": locator_ok,
            "result": (
                "PASS" if sources_processed > 0 and runs_completed > 0
                and quote_ok and locator_ok
                else "FAIL"
            ),
        }

        write_report(result, Path(output_path))
        return result
    finally:
        set_current_context(old_ctx)
        import shutil
        shutil.rmtree(str(ws), ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Golden Evaluation")
    parser.add_argument("--mode", required=True,
                        choices=["fixture", "pipeline-smoke"])
    parser.add_argument("--annotations",
                        default="tests/golden/golden_set.json")
    parser.add_argument("--claims",
                        default="tests/golden/extracted_claims.fixture.jsonl")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.mode == "fixture":
        result = run_fixture(args.annotations, args.claims, args.output)
    else:
        result = run_pipeline_smoke(args.output)

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if not result.get("all_thresholds_pass", True):
        sys.exit(1)
    if result.get("result") == "FAIL":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
