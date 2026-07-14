# AGENTS.md — Literature Evidence Agent

## Current Version: v0.1.1 (stable) / v0.1.2 (next)

Current stable version: v0.1.1
Current stable branch: main
Current development branch: dev
Next release target: v0.1.2

See `docs/releases/` for release documentation.
See `docs/VERSIONING_AND_BRANCHING.md` for version and branch policy.

## Branching Rules

1. 长期分支只允许 `main` 和 `dev`。
2. `main` 只保存 Review 通过的可发布状态。
3. 所有开发直接进入 `dev`。
4. 每个独立 prompt 或任务单独 commit。
5. 每个 commit 完成后 push `dev`。
6. 项目版本只在 RC 或正式发布时修改。
7. RC 使用 `vX.Y.Z-rc.N`，正式发布使用 `vX.Y.Z`。
8. 禁止 `Round`、`RC2`、`review-04` 等组合命名。
9. 禁止 force-push `main`。
10. Release Gate 非 PASS 时禁止 tag。
11. 历史 tag 不得移动或覆盖。
12. 不得创建临时 fix/feat/release 分支。

## 当前范围：v0.1.x 修补

v0.1.x 完成完整闭环：
```
本地 PDF 导入 → 解析 → 主张提取 → 人工复核 → SQLite 数据库 → 检索导出
→ Package Snapshot → 精确 Rebuild → DB Compare → Verify → Golden Set
```

## 必须遵守的规则

1. **运行测试** — 每次修改后运行 `python -m pytest -q`
2. **外部数据隔离** — 所有来源表 origin_scope 固定为 "external"
3. **科学验证状态** — 第一轮只能写入 "unverified"
4. **禁止扩大范围** — 不接入在线检索、OCR、向量数据库、Web UI、多 Agent
5. **原文匹配** — LLM 输出必须先通过确定性校验
6. **幂等性** — 导入、迁移、FTS 重建必须幂等
7. **不吞异常** — migration/rebuild 不得 `except Exception: pass`
8. **不使用 INSERT OR IGNORE** — rebuild 恢复状态不得静默冲突
9. **不生成新业务 ID** — rebuild 保持所有原始 ID
10. **不提前宣布 PASS** — 最终以独立只读 Review 为准

## 开发环境

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 关键命令

```bash
evidence-agent --help
evidence-agent init
evidence-agent db migrate
evidence-agent db check
python -m pytest -q
python -m ruff check .
python -m mypy src
```
