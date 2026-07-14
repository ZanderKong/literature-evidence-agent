# Literature Evidence Agent

从 PDF 文献中提取作者主张、人工复核、全文检索的证据管理系统。

## Round 1.1 能力

- ✅ 本地 PDF 导入与重复识别（SHA-256）
- ✅ PDF 文本解析、页码映射、章节识别
- ✅ LLM 主张提取（Mock + DeepSeek Provider）
- ✅ 确定性校验（quote 匹配、locator 交叉验证、泄漏检查）
- ✅ 统一 `analyse` 工作流（parse→extract→validate→persist）
- ✅ 人工复核包生成（从数据库读取真实数据）
- ✅ 复核决定应用（编辑重校验 + 幂等 + 修订历史）
- ✅ SQLite + FTS5 全文检索
- ✅ Markdown/JSONL 导出
- ✅ 从资料包重建数据库
- ✅ `verify round1` 真实验收

## 安装

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 快速开始

```bash
# 初始化
evidence-agent init
evidence-agent db migrate

# 创建任务
evidence-agent task create --title "分析姜黄素论文" --request "提取所有作者主张" -m analyse_uploaded -d source_complete

# 导入并分析
evidence-agent ingest tests/fixtures/real_scientific_article_en.pdf
evidence-agent analyse SRC-xxxxxxxx --task TASK-xxxxxxxx --provider mock

# 复核
evidence-agent review export RUN-xxxxxxxx
# 编辑 claims_for_review.csv 填写决策
evidence-agent review apply /path/to/review_decisions.csv

# 搜索
evidence-agent query "curcumin"

# 查看
evidence-agent source-show SRC-xxxxxxxx
evidence-agent claim-show CLM-xxxxxxxx

# 导出
evidence-agent export-source SRC-xxxxxxxx

# 从资料包重建
evidence-agent db rebuild-from-packages

# 验证
evidence-agent verify --round-name round1
```

## 项目结构

```
src/evidence_agent/
├── cli.py              # CLI (Typer)
├── config.py           # 配置
├── ids.py              # 稳定 ID 生成
├── application/        # analyse 工作流
├── database/           # 连接、迁移、重建、仓储
├── schemas/            # Pydantic 模型
├── ingest/             # PDF 导入与哈希
├── parsers/            # PDF 解析 (pdfplumber)
├── extraction/         # LLM Provider + 响应解析
├── validators/         # 确定性校验
├── review/             # 复核包与决定
├── search/             # FTS5 搜索
└── exports/            # Markdown/JSONL 导出
```

## 开发

```bash
ruff check .          # Lint
python -m mypy src    # Type check
pytest -q             # 122 tests
```

## 外部数据安全

所有文献数据：`origin_scope = "external"`, `scientific_verification_status = "unverified"`。
审核「批准」只表示记录忠实于来源，不表示科学验证。

## License

MIT
