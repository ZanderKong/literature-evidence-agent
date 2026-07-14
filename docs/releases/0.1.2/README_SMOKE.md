# README Smoke — v0.1.2

Reconstructed from automated README smoke execution.

## Executed Command

```bash
python scripts/readme_smoke.py \
  --output artifacts/release/0.1.2/readme-smoke.json
```

## Workspace

Isolated temporary workspace created by the smoke script.

## Provider

Mock provider (no external API calls).

## CLI Steps

1. `evidence-agent --version`
2. `evidence-agent init`
3. `evidence-agent db migrate`
4. `evidence-agent db check`
5. `evidence-agent task create`
6. `evidence-agent ingest` (tests/fixtures/real_scientific_article_en.pdf)
7. `evidence-agent parse`
8. `evidence-agent analyse --provider mock`
9. `evidence-agent review export`
10. `evidence-agent review apply`
11. `evidence-agent query "curcumin"`
12. `evidence-agent source-show`
13. `evidence-agent package sync`
14. `evidence-agent package validate`

## Result

All commands exited 0. The full pipeline from init through package validate completes without error using the mock provider.

## Known Limitations

- DeepSeek live smoke not executed (no API key)
- Mock provider returns deterministic synthetic claims, not real extraction quality
