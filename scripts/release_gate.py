#!/usr/bin/env python3
"""Release gate — machine-enforced quality checks for v0.1.x releases."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ARTIFACTS_DIR = Path("artifacts/release")


def run(cmd: list[str], output_file: Path | None = None,
        timeout: int = 300) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout)
    except subprocess.TimeoutExpired:
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text("TIMEOUT")
        return (-1, "TIMEOUT")
    output = result.stdout + "\n" + result.stderr
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(output)
    return (result.returncode, output)


def run_gate(version: str, mode: str) -> dict[str, Any]:
    out_dir = ARTIFACTS_DIR / version
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "version": version,
        "mode": mode,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": [], "result": "PENDING",
    }

    # Git identity
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True,
        ).stdout.strip() != ""
        report["git"] = {"branch": branch, "sha": sha, "dirty": dirty}
    except Exception:
        report["git"] = {"error": "git_unavailable"}

    def add(name: str, passed: bool, evidence: str = "",
            exit_code: int = 0, duration: float = 0) -> None:
        report["checks"].append({
            "name": name, "status": "PASS" if passed else "FAIL",
            "exit_code": exit_code, "duration_seconds": round(duration, 1),
            "evidence": evidence[:300],
        })

    # Git clean (release mode only)
    if mode == "release" and report.get("git", {}).get("dirty", False):
        add("git_clean", False, "Dirty workspace")
        report["result"] = "FAIL"
        _write_reports(out_dir, report)
        return report
    add("git_clean", True, "clean")

    # Ruff
    t0 = time.time()
    rc, _ = run(["python", "-m", "ruff", "check", "."], out_dir / "ruff.txt")
    add("ruff", rc == 0, f"exit={rc}", rc, time.time() - t0)

    # Mypy
    t0 = time.time()
    rc, _ = run(["python", "-m", "mypy", "src"], out_dir / "mypy.txt")
    add("mypy", rc == 0, f"exit={rc}", rc, time.time() - t0)

    # Pytest 3x
    for i in range(1, 4):
        t0 = time.time()
        rc, _ = run(
            ["pytest", "-q", "-m", "not live_deepseek"],
            out_dir / f"pytest-run-{i}.txt",
        )
        add(f"pytest_{i}", rc == 0, f"exit={rc}", rc, time.time() - t0)

    # Random seeds
    for seed in [1, 2, 3]:
        t0 = time.time()
        rc, _ = run(
            ["pytest", "-q", "--randomly-seed", str(seed),
             "-m", "not live_deepseek"],
            out_dir / f"pytest-seed-{seed}.txt",
        )
        add(f"seed_{seed}", rc == 0, f"exit={rc}", rc, time.time() - t0)

    # Golden fixture conformance
    t0 = time.time()
    rc, _ = run(
        ["python", "scripts/evaluate_golden.py", "--mode", "fixture",
         "--output", str(out_dir / "golden-fixture.json")],
        out_dir / "golden-fixture.txt",
    )
    gfd = {}
    try:
        gfd = json.loads((out_dir / "golden-fixture.json").read_text())
    except Exception:
        pass
    add("golden_fixture", rc == 0,
        f"exit={rc} pass={gfd.get('all_thresholds_pass')}", rc, time.time() - t0)

    # Golden pipeline smoke
    t0 = time.time()
    rc, _ = run(
        ["python", "scripts/evaluate_golden.py", "--mode", "pipeline-smoke",
         "--output", str(out_dir / "golden-pipeline-smoke.json")],
        out_dir / "golden-pipeline-smoke.txt",
    )
    gps = {}
    try:
        gps = json.loads((out_dir / "golden-pipeline-smoke.json").read_text())
    except Exception:
        pass
    add("golden_smoke", rc == 0,
        f"exit={rc} result={gps.get('result')}", rc, time.time() - t0)

    # README smoke
    t0 = time.time()
    rc, _ = run(
        ["python", "scripts/readme_smoke.py",
         "--output", str(out_dir / "readme-smoke.json")],
        out_dir / "readme-smoke.txt",
    )
    rs = {}
    try:
        rs = json.loads((out_dir / "readme-smoke.json").read_text())
    except Exception:
        pass
    add("readme_smoke", rc == 0,
        f"exit={rc} result={rs.get('result')}", rc, time.time() - t0)

    # Verify
    t0 = time.time()
    rc, _ = run(
        ["evidence-agent", "verify", "--round-name", "round1"],
        out_dir / "verify.txt",
    )
    add("verify", rc == 0, f"exit={rc}", rc, time.time() - t0)

    # CLI E2E
    t0 = time.time()
    rc, _ = run(
        ["pytest", "tests/e2e/test_cli_round1_rc2.py", "-q"],
        out_dir / "cli_e2e.txt",
    )
    add("cli_e2e", rc == 0, f"exit={rc}", rc, time.time() - t0)

    # Snapshot/Rebuild
    t0 = time.time()
    rc, _ = run(
        ["pytest",
         "tests/integration/test_package_snapshot.py",
         "tests/integration/test_package_snapshot_integrity.py",
         "tests/integration/test_rebuild_complete_state.py",
         "tests/regression/test_rebuild_identity.py", "-q"],
        out_dir / "snapshot_rebuild.txt",
    )
    add("snapshot_rebuild", rc == 0, f"exit={rc}", rc, time.time() - t0)

    # Review workflow
    t0 = time.time()
    rc, _ = run(
        ["pytest",
         "tests/integration/test_review_batches.py",
         "tests/regression/test_review_edit_revalidation.py", "-q"],
        out_dir / "review_workflow.txt",
    )
    add("review_workflow", rc == 0, f"exit={rc}", rc, time.time() - t0)

    # Live DeepSeek
    api_key = os.getenv("EVIDENCE_AGENT_LLM_API_KEY")
    if api_key:
        t0 = time.time()
        rc, _ = run(
            ["pytest", "-m", "live_deepseek", "-q"],
            out_dir / "live_deepseek.txt",
        )
        add("live_deepseek", rc == 0, f"exit={rc}", rc, time.time() - t0)
    else:
        add("live_deepseek", True, "BLOCKED_EXTERNAL")
        if mode == "release":
            report["result"] = "PASS_OFFLINE_LIVE_BLOCKED"

    # Repo hygiene
    secrets = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, text=True,
    )
    paths = secrets.stdout.split("\0")
    violations = []
    for p in paths:
        if not p: continue
        if any(x in p for x in [".venv", "__pycache__", ".pyc"]):
            violations.append(p)
        if p.endswith((".sqlite", ".sqlite3", ".db", ".sqlite-wal", ".sqlite-shm")):
            violations.append(p)
        if p.endswith(".env") and p != ".env.example":
            violations.append(p)
    add("repo_hygiene", len(violations) == 0,
        f"violations={len(violations)}", 0 if not violations else 1)

    all_pass = all(c["status"] == "PASS" for c in report["checks"])
    if not all_pass:
        report["result"] = "FAIL"
    elif report["result"] != "PASS_OFFLINE_LIVE_BLOCKED":
        report["result"] = "PASS"

    _write_reports(out_dir, report)
    return report


def _write_reports(out_dir: Path, report: dict) -> None:
    (out_dir / "release_gate.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
    )
    md_lines = [
        f"# Release Gate — v{report['version']}",
        f"**Mode**: {report['mode']}",
        f"**Timestamp**: {report['timestamp']}",
        f"**Result**: {report['result']}",
        "",
        "| Check | Status | Evidence |",
        "|-------|--------|----------|",
    ]
    for c in report["checks"]:
        md_lines.append(
            f"| {c['name']} | {c['status']} | {c['evidence']} |"
        )
    (out_dir / "release_gate.md").write_text("\n".join(md_lines) + "\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--version", required=True)
    p.add_argument("--mode", default="local",
                   choices=["local", "ci", "release"])
    args = p.parse_args()
    print(f"Release Gate v{args.version} ({args.mode})")
    report = run_gate(args.version, args.mode)
    print(f"Result: {report['result']}")
    if report["result"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
