# Release Gate — v0.1.3

## Release Identity

| Field | Value |
|-------|-------|
| Version | v0.1.3-rc.1 |
| Gate SHA | `36dc6d8aa58b4c9bec067e897b26f55c4b02d578` |
| Gate branch | dev |

## Gate Command

```bash
python scripts/release_gate.py --version 0.1.3 --mode release
```

## Local Gate Results

| Check | Result | Evidence |
|-------|--------|----------|
| git_clean | PASS | clean |
| version_consistency | PASS | all=0.1.3 |
| ruff | PASS | exit=0 |
| mypy | PASS | exit=0 |
| pytest_1 | PASS | 215 passed |
| pytest_2 | PASS | 215 passed |
| pytest_3 | PASS | 215 passed |
| seed_1 | PASS | 215 passed |
| seed_2 | PASS | 215 passed |
| seed_3 | PASS | 215 passed |
| golden_fixture | PASS | all thresholds pass |
| golden_smoke | PASS | PASS |
| readme_smoke | PASS | PASS |
| verify | PASS | ROUND1_VERIFICATION=PASS |
| cli_e2e | PASS | exit=0 |
| snapshot_rebuild | PASS | exit=0 |
| review_workflow | PASS | exit=0 |
| live_deepseek | PASS_OFFLINE_LIVE_BLOCKED | no API key |
| repo_hygiene | PASS | clean |

## Remote CI Gate Results

| Check | py3.11 | py3.12 |
|-------|--------|--------|
| Lint (ruff) | PASS | PASS |
| Type check (mypy) | PASS | PASS |
| Run tests | PASS | PASS |
| Golden fixture | PASS | PASS |
| README smoke | PASS | PASS |
| Release gate | PASS | PASS |
| Live DeepSeek | skipped | skipped |

## Overall Result

PASS_OFFLINE_LIVE_BLOCKED
