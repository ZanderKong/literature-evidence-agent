# Literature Evidence Agent

文献证据 Agent — 从 PDF 文献中提取作者主张、人工复核、全文检索的证据管理系统。

## Round 1 能力（当前）

- ✅ 本地 PDF 导入与重复识别
- ✅ PDF 文本解析、页码映射、章节识别
- ✅ LLM 主张提取（Mock 提供者可用于离线测试）
- ✅ 确定性校验（原文匹配、定位、泄漏检查）
- ✅ 人工复核包生成（CSV/JSONL/Markdown/HTML）
- ✅ 复核决定应用与修订历史
- ✅ SQLite 数据库 + FTS5 全文检索
- ✅ Markdown/JSONL 导出

## Round 1 明确不做

- 在线论文检索、专利检索
- OCR 批处理、扫描版 PDF
- 图片视觉理解、曲线数字化
- 向量数据库、图数据库
- Web 前端、用户账户系统

## 安装

```bash
# 需要 Python >= 3.11
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 快速开始

```bash
# 初始化工作区
evidence-agent init

# 运行数据库迁移
evidence-agent db migrate

# 导入一篇 PDF
evidence-agent ingest path/to/paper.pdf

# 解析 PDF
evidence-agent parse SRC-xxxxxxxx

# 检查数据库完整性
evidence-agent db check

# 搜索已审核主张
evidence-agent query "关键词"

# 导出资料记录
evidence-agent export-source SRC-xxxxxxxx

# 运行验证
evidence-agent verify round1
```

## 开发

```bash
# 运行所有测试
pytest

# 代码检查
ruff check .
python -m mypy src
```

## 外部数据安全边界

所有导入的文献数据标记为：
- `origin_scope = "external"`
- `scientific_verification_status = "unverified"`

人工审核「批准」只表示记录忠实于来源，**不表示**科学结论已被内部实验验证。

## 项目结构

```
src/evidence_agent/
├── cli.py          # CLI 入口
├── config.py       # 配置系统
├── ids.py          # ID 生成
├── database/       # 数据库连接与迁移
├── schemas/        # Pydantic 数据模型
├── ingest/         # 文件导入与哈希
├── parsers/        # PDF 解析
├── extraction/     # LLM 主张提取
├── validators/     # 确定性校验
├── review/         # 复核包与决定
├── search/         # FTS5 全文搜索
└── exports/        # Markdown/JSONL 导出
```

## 已知限制

- 仅支持文字型 PDF（不支持扫描版）
- Mock Provider 返回固定响应（真实 API 需配置密钥）
- 不支持复杂双栏、公式、表格提取
- 单用户、单机运行

## License

MIT
