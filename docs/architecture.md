# Architecture — 文献证据 Agent

## 整体架构

```
CLI (Typer)
  ├── ingest   → 文件验证 → SHA-256 → 资料包 → SQLite
  ├── parse    → pdfplumber → 页面 → 章节 → Markdown
  ├── extract  → Mock/DeepSeek Provider → 主张提取
  ├── validate → Schema + Quote + Locator + Leakage
  ├── review   → CSV/HTML 复核包 → 应用决定
  ├── search   → FTS5 → 全文搜索
  └── export   → Markdown/JSONL 导出
```

## 数据流

```mermaid
graph LR
    PDF[PDF 文件] --> Ingest[导入]
    Ingest --> Package[资料包]
    Package --> Parse[解析]
    Parse --> Sections[章节/页面]
    Sections --> Extract[LLM 提取]
    Extract --> RawClaims[候选主张]
    RawClaims --> Validate[确定性校验]
    Validate --> Validated[通过的主张]
    Validated --> Review[人工复核包]
    Review --> Decisions[复核决定]
    Decisions --> DB[(SQLite)]
    DB --> FTS[FTS5 索引]
    DB --> Export[导出]
```

## 数据库

SQLite 3 + FTS5 全文检索。详见 `docs/database_design.md`。

## 外部数据身份

所有来源表通过 CHECK 约束保证：
- `origin_scope = 'external'`
- `scientific_verification_status = 'unverified'`（第一轮）

Pydantic 模型层面也有相同的 validator。
