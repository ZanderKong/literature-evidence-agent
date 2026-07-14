#!/usr/bin/env python3
"""Release gate — machine-enforced quality checks for v0.1.x releases.

Usage:
    python scripts/release_gate.py --version 0.1.1 --mode local
    python scripts/release_gate.py --version 0.1.1 --mode ci
    python scripts/release_gate.py --version 0.1.1 --mode release
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ARTIFACTS_DIR = Path("artifacts/release")


def run(cmd: list[str], output_file: Path | None = None, timeout: int = 300) -> int:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(result.stdout + "\n" + result.stderr)
    return result.returncode


def run_gate(version: str, mode: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "version": version,
        "mode": mode,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": [],
        "result": "PENDING",
    }
    out_dir = ARTIFACTS_DIR / version
    out_dir.mkdir(parents=True, exist_ok=True)

    def add_check(name: str, passed: bool, evidence: str = "") -> None:
        report["checks"].append({
            "name": name, "status": "PASS" if passed else "FAIL",
            "evidence": evidence[:300],
        })
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")

    # 1. Git status
    r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    clean = r.stdout.strip() == "" or mode != "release"
    add_check("git_clean", clean, r.stdout.strip()[:200] if not clean else "clean")

    # 2. Ruff
    rc = run(["python", "-m", "ruff", "check", "."], out_dir / "ruff.txt")
    add_check("ruff", rc == 0, f"exit={rc}")

    # 3. Mypy
    rc = run(["python", "-m", "mypy", "src"], out_dir / "mypy.txt")
    add_check("mypy", rc == 0, f"exit={rc}")

    # 4-6. Pytest 3x
    for i in range(1, 4):
        rc = run(
            ["pytest", "-q", "-m", "not live_deepseek"],
            out_dir / f"pytest-run-{i}.txt",
        )
        add_check(f"pytest_run_{i}", rc == 0, f"exit={rc}")

    # 7-9. Random seeds
    for seed in [1, 2, 3]:
        rc = run(
            ["pytest", "-q", "--randomly-seed", str(seed), "-m", "not live_deepseek"],
            out_dir / f"pytest-seed-{seed}.txt",
        )
        add_check(f"random_seed_{seed}", rc == 0, f"exit={rc}")

    # 10. Verify
    rc = run(
        ["evidence-agent", "verify", "--round-name", "round1"],
        out_dir / "verify.txt",
    )
    try:
        vdata = json.loads((out_dir / "verify.txt").read_text()) if rc == 0 else {}
    except Exception:
        vdata = {}
    add_check("verify", rc == 0, vdata.get("result", "FAIL") if vdata else f"exit={rc}")

    # 11. Golden
    from tests.golden.evaluator import evaluate_golden
    from evidence_agent.database.connection import get_connection
    with get_connection(read_only=True) as conn:
        rows = conn.execute(
            "SELECT * FROM source_claims "
            "WHERE record_review_status = 'approved' LIMIT 50"
        ).fetchall()
    claims = [dict(r) for r in rows]
    golden_result = evaluate_golden(claims)
    (out_dir / "golden.json").write_text(
        json.dumps(golden_result, indent=2, ensure_ascii=False),
    )
    add_check("golden", golden_result.get("all_thresholds_pass", False),
              f"recall={golden_result.get('recall')}% pass={golden_result.get('all_thresholds_pass')}")

    # 12. CLI E2E
    rc = run(
        ["pytest", "tests/e2e/test_cli_round1_rc2.py", "-q"],
        out_dir / "cli_e2e.txt",
    )
    add_check("cli_e2e", rc == 0, f"exit={rc}")

    # 13. Snapshot/Rebuild
    rc = run(
        ["pytest", "tests/integration/test_package_snapshot.py",
         "tests/integration/test_package_snapshot_integrity.py",
         "tests/integration/test_rebuild_complete_state.py",
         "tests/regression/test_rebuild_identity.py", "-q"],
        out_dir / "snapshot_rebuild.txt",
    )
    add_check("snapshot_rebuild", rc == 0, f"exit={rc}")

    # 14. Review workflow
    rc = run(
        ["pytest", "tests/integration/test_review_batches.py",
         "tests/regression/test_review_edit_revalidation.py", "-q"],
        out_dir / "review_workflow.txt",
    )
    add_check("review_workflow", rc == 0, f"exit={rc}")

    # 15. Live DeepSeek (if key exists)
    api_key = os.getenv("EVIDENCE_AGENT_LLM_API_KEY")
    if api_key:
        rc = run(
            ["pytest", "-m", "live_deepseek", "-q"],
            out_dir / "live_deepseek.txt",
        )
        add_check("live_deepseek", rc == 0, f"exit={rc}")
    else:
        add_check("live_deepseek", True, "BLOCKED_EXTERNAL")
        if mode == "release":
            report["result"] = "PASS_OFFLINE_LIVE_BLOCKED"

    # 16. Repo hygiene
    secrets_check = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True, text=True,
    )
    paths = secrets_check.stdout.split("\0")
    violations = []
    for p in paths:
        if not p:
            continue
        if any(x in p for x in [".venv", "__pycache__", ".pyc"]):
            violations.append(p)
        if p.endswith((".sqlite", ".sqlite3", ".db", ".sqlite-wal", ".sqlite-shm")):
            violations.append(p)
        if p.endswith(".env") and p != ".env.example":
            violations.append(p)
    repo_ok = len(violations) == 0
    add_check("repo_hygiene", repo_ok,
              f"violations={violations[:5]}" if violations else "clean")

    # Final result
    all_pass = all(c["status"] == "PASS" for c in report["checks"])
    if not all_pass:
        report["result"] = "FAIL"
    elif report["result"] != "PASS_OFFLINE_LIVE_BLOCKED":
        report["result"] = "PASS"

    # Write reports
    (out_dir / "release_gate.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
    )
    (out_dir / "release_gate.md").write_text(_md_report(report))

    return report


def _md_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Release Gate — v{report['version']}",
        f"**Mode**: {report['mode']}",
        f"**Timestamp**: {report['timestamp']}",
        f"**Result**: {report['result']}",
        "",
        "| Check | Status | Evidence |",
        "|-------|--------|----------|",
    ]
    for c in report["checks"]:
        lines.append(f"| {c['name']} | {c['status']} | {c['evidence']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Release Gate")
    parser.add_argument("--version", required=True, help="Version (e.g. 0.1.1)")
    parser.add_argument("--mode", default="local",
                        choices=["local", "ci", "release"],
                        help="Gate mode")
    args = parser.parse_args()

    print(f"Release Gate v{args.version} ({args.mode})")
    report = run_gate(args.version, args.mode)
    print(f"\nResult: {report['result']}")

    if report["result"] == "FAIL":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
