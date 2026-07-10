# AGENTS.md — Literature Evidence Agent

## 当前范围：Round 1

Round 1 只完成一个闭环：
```
本地 PDF 导入 → 解析 → 主张提取 → 人工复核 → SQLite 数据库 → 检索导出
```

## 必须遵守的规则

1. **运行测试** — 每次修改后运行 `pytest -q`
2. **外部数据隔离** — 所有来源表 origin_scope 固定为 "external"
3. **科学验证状态** — 第一轮只能写入 "unverified"
4. **禁止扩大范围** — 不接入在线检索、OCR、向量数据库
5. **原文匹配** — LLM 输出必须先通过确定性校验
6. **幂等性** — 导入、迁移、FTS 重建必须幂等

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
pytest -q
ruff check .
python -m mypy src
```
