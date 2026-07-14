# Versioning and Branching Policy — Literature Evidence Agent

## Versioning

This project uses Semantic Versioning (SemVer) compatible with Python PEP 440.

| Type | Version Pattern | Git Tag | Example |
|------|----------------|---------|---------|
| Release Candidate | `X.Y.ZrcN` | `vX.Y.Z-rc.N` | `v0.1.1-rc.1` |
| Stable Release | `X.Y.Z` | `vX.Y.Z` | `v0.1.1` |

### Release Candidate
- Built from `fix/*` branch
- All Release Gate checks must PASS or PASS_OFFLINE_LIVE_BLOCKED
- Reviewed and approved before stable release

### Stable Release
- Merged to `main` via `git merge --no-ff`
- Tagged with `vX.Y.Z`
- All historical tags preserved, never moved or deleted

### Project Version in `pyproject.toml`

The single source of truth for the version string is `pyproject.toml` under `[project] version =`. All runtime code reads from `importlib.metadata.version("literature-evidence-agent")`. Do not hardcode version strings in source files.

## Branching

### Long-lived Branches
- **`main`** — Only contains reviewed, release-gated stable versions. Never force-pushed. Never rebased after publication.
- **`dev`** — Active development branch. All features, fixes, and enhancements land here first.

### Merge Rules
- `dev` → `main`: `git merge --no-ff dev -m "release: merge version X.Y.Z"`
- Never: `git push --force origin main`
- Never: `git reset --hard` on `main` or published branches

## Commit Discipline

- Each independent prompt or task gets at least one commit
- Each commit targets a single, clear topic
- Never mix: core code changes, README rewrites, version bumps, and release reports in the same commit
- Commit messages use conventional format: `type(scope): description`

## Release Workflow

1. Develop in `dev` (or `fix/*` branch for release-specific hardening)
2. Run `python scripts/release_gate.py --version X.Y.Z --mode release`
3. Verify PASS or PASS_OFFLINE_LIVE_BLOCKED
4. Merge to `main` with `--no-ff`
5. Tag `vX.Y.Z` on `main`
6. Push `main` and tag

## Historical Tags

The following tags are preserved for audit trail. They will never be moved, renamed, or deleted:

- `round1-failed-baseline`
- `round1.1-rc2-review-01` through `round1.1-rc2-review-04`
- `v0.1.1-rc.N`
- `vX.Y.Z`

## Hotfix

1. Fix on `dev`, run targeted tests
2. Release Gate must PASS
3. Merge `dev` to `main` with `--no-ff`
4. Tag patch version on `main`
5. Fast-forward `dev` to `main`
