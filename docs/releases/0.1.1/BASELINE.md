# v0.1.1 Release Baseline

- **Date**: 2026-07-14
- **Phase**: Pre-Review Freeze

## Candidate Info

| Item | Value |
|------|-------|
| Candidate SHA | `3c7557dcc9abde5170e0606f5d12c592256b31b4` |
| Current Branch | `fix/round1.1-rc2-hardening` |
| Main SHA | `6f216aaa3886d31c4f5a345f65ecb0a22f26ea38` |
| Main..Candidate commits | 53 |
| pyproject.toml version | `0.1.0` |
| Migration versions | 5 (001-005) |
| Python version | 3.11 / 3.12 |

## Existing Review Tags

| Tag | Commit | Status |
|-----|--------|--------|
| `round1.1-rc2-review-01` | `2f6b915` | Premature — DO NOT USE |
| `round1.1-rc2-review-02` | `c636071` | C-stage intermediate — DO NOT USE |
| `round1.1-rc2-review-03` | `f5abc07` | Pre-remediation candidate — DO NOT USE |
| `round1.1-rc2-review-04` | `3c7557d` | Final RC2 review candidate |

## Test Results (as of baseline freeze)

- **pytest**: 203 passed / 0 failed / 2 deselected (live_deepseek)
- **Ruff src**: clean
- **Mypy**: clean
- **3x pytest**: all pass
- **3x random seeds**: all pass

## Known Pending Items

1. Formal Independent Review not yet performed
2. README not yet smoke-tested in fresh environment
3. Release Gate script not yet written
4. CI has not been executed remotely (local only)
5. DeepSeek Live Smoke not executed (no API key in env)
6. Golden Set evaluator tested with known claims only
7. Package version still reads `0.1.0`
