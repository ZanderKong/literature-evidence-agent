# 文献证据 Agent 第一轮开发执行计划

> 目标执行模型：DeepSeek-V4-Pro  
> 文件用途：作为 Coding Agent 的第一轮主计划文件，要求模型逐项执行、逐项验证、逐项记录，不得只生成代码而跳过运行与验收。  
> 计划版本：Round 1 / v1.0  
> 制定日期：2026-07-10  
> 建议文件位置：`docs/plans/ROUND1_DEEPSEEK_V4_PRO_PLAN.md`

---

## 0. 计划结论

第一轮只完成一个闭环：

```text
本地导入一篇可解析 PDF
→ 建立外部资料档案
→ 解析正文与章节
→ 提取与任务相关的作者主张
→ 校验原文与定位
→ 生成人工复核包
→ 应用人工复核结果
→ 写入 SQLite 外部证据库
→ 支持全文检索和来源回溯
```

第一轮不接入在线文献检索、专利检索、知识图谱、向量数据库、外部数值仓库和自动实验决策。

本轮成功标准是：

1. 系统能够稳定处理本地 PDF。
2. 每条作者主张都能追溯到原文和位置。
3. 外部资料永远保持「外部、未经内部验证」身份。
4. 自动结果必须经过可操作的人工复核流程。
5. 数据库可以由资料包重新构建。
6. 所有主要功能都有自动测试和可重复的验收命令。

---

# 1. DeepSeek-V4-Pro 执行协议

## 1.1 运行假设

本计划假设 DeepSeek-V4-Pro 运行在具备以下能力的 Coding Agent 或终端 Harness 中：

- 可以读取和修改本地文件。
- 可以执行 Shell 命令。
- 可以创建 Python 虚拟环境。
- 可以运行测试。
- 可以读取 Git 状态和差异。
- 可以分阶段提交或至少生成阶段性状态报告。

直接在普通聊天界面中运行时，不具备上述工具能力，因此不能视为完成本计划。

## 1.2 模型配置建议

推荐：

```text
model = deepseek-v4-pro
thinking = enabled
reasoning_effort = max
context = 1M
```

若通过官方 OpenAI 兼容接口运行：

- 模型名使用 `deepseek-v4-pro`。
- 思考模式显式开启。
- 复杂编码任务使用 `reasoning_effort=max`。
- 思考模式下不要依赖 `temperature`、`top_p` 等采样参数。
- 工具调用后的后续请求必须完整保留对应的 `reasoning_content`。
- 不要向思考模式请求中传递强制性的 `tool_choice`。
- 工具调用消息的 `content` 不应为 `null`。

若使用 Claude Code 兼容接口，优先使用官方推荐的 Anthropic 兼容端点与 `deepseek-v4-pro[1m]`。

## 1.3 DeepSeek 执行纪律

DeepSeek-V4-Pro 必须遵守以下规则：

### 每个任务开始前

1. 阅读本计划中该任务的目标、输入、执行步骤和验收条件。
2. 检查当前仓库状态。
3. 检查前置任务是否完成。
4. 将任务状态更新为 `in_progress`。
5. 不得一次性修改与当前任务无关的大量文件。

### 每个任务完成后

1. 运行该任务规定的测试和验收命令。
2. 保存终端结果摘要。
3. 检查 `git diff`。
4. 更新执行日志。
5. 将任务状态更新为：
   - `completed`
   - `blocked`
   - `failed`
6. 只有验收条件全部满足，才允许标记为 `completed`。

### 禁止行为

- 只写代码，不运行测试。
- 用「理论上可运行」代替真实运行。
- 因测试失败而删除测试。
- 为通过测试而硬编码固定输出。
- 将外部文献数据写入内部实验数据结构。
- 无依据地扩大本轮范围。
- 静默跳过 PDF 解析失败或 LLM 输出异常。
- 覆盖用户已有文件而不备份或不检查。
- 把 LLM 生成的转述当成作者原文。
- 在没有定位信息时将主张标记为可接受。

---

# 2. 第一轮范围

## 2.1 必须完成

### 基础设施

- Python 项目骨架。
- 配置系统。
- SQLite 数据库。
- 数据库迁移。
- SQLite FTS5 全文检索。
- 稳定 ID。
- 原始文件 SHA-256。
- 资料包目录。
- JSONL 和 Markdown 导出。
- 日志与处理运行记录。

### 本地资料处理

- 导入本地 PDF。
- 重复导入识别。
- PDF 文本解析。
- 页码映射。
- 基础章节识别。
- 图题、表题的文本识别。
- 作者主张提取。
- 原文匹配。
- 页码和章节定位校验。
- 主张类型分类。
- 作者限定词记录。
- 证据依据的描述性记录。

### 人工复核

- 生成复核包。
- 支持批准。
- 支持编辑后批准。
- 支持拒绝。
- 支持标记遗漏。
- 支持保存复核理由。
- 支持保留修改历史。
- 未审核记录与已审核记录分开查询。

### 查询与导出

- 按资料查询。
- 按主张查询。
- 全文搜索。
- 按材料、方法和性能实体筛选。
- 从主张返回原始资料路径和页码。
- 导出单份资料报告。
- 导出研究任务证据报告。

### 质量保障

- 单元测试。
- 集成测试。
- 回归测试。
- 一条端到端验收路径。
- Golden Set 人工样本。
- 数据污染测试。
- 数据库重建测试。

## 2.2 明确不做

- 在线论文检索。
- OpenAlex、Crossref 和 EPO 接口。
- 专利族识别。
- 网页抓取。
- OCR 批处理。
- 扫描版 PDF 的完整支持。
- 图片视觉理解。
- 曲线数字化。
- 表格数值全量提取。
- 外部实验数值数据库。
- 内部实验数据管理。
- 跨论文定量合并。
- 向量数据库。
- 图数据库。
- 自动研究结论。
- 自动实验方案。
- 多 Agent 协作。
- 生产级 Web 前端。
- 用户账户和权限系统。

出现这些需求时，记录到 `docs/roadmap.md`，不得在第一轮顺手实现。

---

# 3. 第一轮 Definition of Done

只有同时满足以下条件，第一轮才算完成。

## 3.1 功能完成

- [ ] 可以使用 CLI 初始化工作区。
- [ ] 可以导入一篇本地 PDF。
- [ ] 重复导入同一文件不会生成重复资料。
- [ ] 可以解析 PDF 文本并保留页码。
- [ ] 可以生成资料包。
- [ ] 可以调用 LLM 或测试替身提取主张。
- [ ] 每条主张包含原文、忠实转述、类型、依据描述和定位。
- [ ] 原文无法匹配时，记录不会进入可审核状态。
- [ ] 可以生成复核 CSV、JSONL 和 HTML 或 Markdown 包。
- [ ] 可以应用复核决定。
- [ ] 可以全文搜索已审核主张。
- [ ] 可以从检索结果返回原始文件路径和页码。
- [ ] 可以导出单份资料的资料记录。
- [ ] 可以由资料包重建数据库。

## 3.2 质量完成

- [ ] 所有数据库迁移可从空库执行。
- [ ] 所有数据库迁移可以重复检查，不能重复破坏数据。
- [ ] 外键检查通过。
- [ ] 单元测试全部通过。
- [ ] 集成测试全部通过。
- [ ] 端到端测试全部通过。
- [ ] 外部资料写入内部数据结构的测试为 0 条。
- [ ] Golden Set 中所有接受的原文都能精确或规范化匹配。
- [ ] 所有正式接受的主张都有定位。
- [ ] 所有正式接受的主张都有人工复核记录。
- [ ] 项目可在新的虚拟环境中安装和运行。
- [ ] README 中的命令经真实执行验证。

## 3.3 文档完成

- [ ] 架构说明存在。
- [ ] 数据库说明存在。
- [ ] 主张数据合同存在。
- [ ] 人工复核说明存在。
- [ ] 已知限制存在。
- [ ] 第一轮完成报告存在。
- [ ] 每个阶段的真实命令和测试结果有记录。

---

# 4. 目标代码结构

如果现有仓库已经有合理结构，应在不破坏现有功能的前提下适配。新项目推荐：

```text
literature-evidence-agent/
├── AGENTS.md
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── docs/
│   ├── architecture.md
│   ├── database_design.md
│   ├── claim_contract.md
│   ├── review_protocol.md
│   ├── known_limitations.md
│   ├── roadmap.md
│   └── plans/
│       ├── ROUND1_DEEPSEEK_V4_PRO_PLAN.md
│       └── ROUND1_EXECUTION_LOG.md
├── migrations/
│   ├── 001_initial.sql
│   ├── 002_fts.sql
│   └── 003_constraints.sql
├── src/
│   └── evidence_agent/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── ids.py
│       ├── logging.py
│       ├── state.py
│       ├── workflow.py
│       ├── database/
│       │   ├── connection.py
│       │   ├── migrations.py
│       │   ├── repositories.py
│       │   ├── queries.py
│       │   └── rebuild.py
│       ├── schemas/
│       │   ├── task.py
│       │   ├── source.py
│       │   ├── section.py
│       │   ├── claim.py
│       │   ├── review.py
│       │   └── run.py
│       ├── ingest/
│       │   ├── files.py
│       │   ├── hashing.py
│       │   └── package.py
│       ├── parsers/
│       │   ├── base.py
│       │   ├── pdf.py
│       │   └── sections.py
│       ├── extraction/
│       │   ├── provider.py
│       │   ├── prompts.py
│       │   ├── claims.py
│       │   └── mock_provider.py
│       ├── validators/
│       │   ├── quote.py
│       │   ├── locator.py
│       │   ├── provenance.py
│       │   └── leakage.py
│       ├── review/
│       │   ├── packet.py
│       │   ├── decisions.py
│       │   └── revisions.py
│       ├── search/
│       │   └── fts.py
│       └── exports/
│           ├── markdown.py
│           ├── jsonl.py
│           └── csv.py
├── tests/
│   ├── fixtures/
│   ├── golden/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── scripts/
│   ├── smoke_test.py
│   ├── rebuild_database.py
│   └── verify_round1.py
└── workspace/
    └── external_evidence/
        ├── evidence.sqlite
        ├── sources/
        ├── review/
        ├── exports/
        ├── logs/
        └── backups/
```

---

# 5. 核心领域规则

## 5.1 外部资料身份

文献证据 Agent 中的来源统一为：

```text
origin_scope = external
verification_status = unverified
```

人工确认只表示「记录忠实于来源」，不表示科学结论已被内部验证。

建议增加两个分离字段：

```text
record_review_status:
- pending
- approved
- approved_with_edits
- rejected

scientific_verification_status:
- unverified
- internally_reproduced
- independently_confirmed
- contradicted
```

第一轮只允许自动设置：

```text
scientific_verification_status = unverified
```

## 5.2 主张的定义

一条主张是来源中能够独立表达的陈述，例如：

- 作者报告的观察。
- 作者报告的结果。
- 作者提出的解释。
- 作者得出的结论。
- 作者提出的假设。
- 作者声明的限制。
- 作者提出的后续研究方向。

每条主张必须同时拥有：

```text
source_quote
faithful_paraphrase
claim_type
evidence_basis_description
locator
author_hedging
origin_scope
record_review_status
scientific_verification_status
```

## 5.3 数据处理边界

第一轮允许：

- 描述某个结论由哪张图、哪张表或哪组实验支持。
- 描述数据的方向和比较关系。
- 记录作者原文中的关键数值，但仍作为文本引用的一部分。
- 标记条件缺失。

第一轮禁止：

- 把图表数值抽成独立数据集。
- 把外部数值写入内部实验表。
- 自动复算。
- 自动合并不同文献的数据。
- 自动生成新的机理结论。

---

# 6. 数据库详细设计

数据库文件：

```text
workspace/external_evidence/evidence.sqlite
```

SQLite 启动时必须执行：

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

测试环境可以使用独立临时数据库。

## 6.1 `research_tasks`

```sql
CREATE TABLE research_tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    user_request TEXT NOT NULL,
    research_background TEXT,
    task_mode TEXT NOT NULL CHECK (
        task_mode IN (
            'analyse_uploaded',
            'source_complete_analysis',
            'evidence_query'
        )
    ),
    analysis_depth TEXT NOT NULL CHECK (
        analysis_depth IN ('task_focused', 'source_complete')
    ),
    status TEXT NOT NULL CHECK (
        status IN ('created', 'running', 'review', 'completed', 'failed')
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

## 6.2 `sources`

```sql
CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (
        source_type IN (
            'journal_article',
            'preprint',
            'conference_paper',
            'technical_report',
            'product_documentation',
            'other'
        )
    ),
    title TEXT,
    authors_json TEXT NOT NULL DEFAULT '[]',
    organisation TEXT,
    publication_date TEXT,
    doi TEXT,
    language TEXT,
    version_label TEXT,
    original_file_sha256 TEXT NOT NULL UNIQUE,
    origin_scope TEXT NOT NULL DEFAULT 'external'
        CHECK (origin_scope = 'external'),
    scientific_verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (
            scientific_verification_status IN (
                'unverified',
                'internally_reproduced',
                'independently_confirmed',
                'contradicted'
            )
        ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

第一轮代码不得自动写入除 `unverified` 外的科学验证状态。

## 6.3 `source_assets`

```sql
CREATE TABLE source_assets (
    asset_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    asset_type TEXT NOT NULL CHECK (
        asset_type IN ('main_document', 'supplementary', 'attachment')
    ),
    relative_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    file_size INTEGER NOT NULL CHECK (file_size >= 0),
    acquired_from TEXT,
    acquired_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE,
    UNIQUE (source_id, sha256)
);
```

## 6.4 `source_sections`

```sql
CREATE TABLE source_sections (
    section_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    section_type TEXT NOT NULL,
    heading TEXT,
    page_start INTEGER,
    page_end INTEGER,
    sequence_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE,
    UNIQUE (source_id, sequence_number)
);
```

约束：

- 页码为空时必须明确记录解析器未能映射。
- `page_end` 不得小于 `page_start`。
- 文本为空的章节不写入数据库。

## 6.5 `source_claims`

```sql
CREATE TABLE source_claims (
    claim_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    task_id TEXT,
    claim_type TEXT NOT NULL CHECK (
        claim_type IN (
            'background_statement',
            'method_statement',
            'reported_observation',
            'reported_result',
            'author_interpretation',
            'author_conclusion',
            'author_hypothesis',
            'author_limitation',
            'future_work'
        )
    ),
    source_quote TEXT NOT NULL,
    faithful_paraphrase TEXT NOT NULL,
    evidence_basis_description TEXT NOT NULL,
    scope_description TEXT,
    author_hedging TEXT,
    origin_scope TEXT NOT NULL DEFAULT 'external'
        CHECK (origin_scope = 'external'),
    record_review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            record_review_status IN (
                'pending',
                'approved',
                'approved_with_edits',
                'rejected'
            )
        ),
    scientific_verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (
            scientific_verification_status IN (
                'unverified',
                'internally_reproduced',
                'independently_confirmed',
                'contradicted'
            )
        ),
    quote_match_status TEXT NOT NULL CHECK (
        quote_match_status IN (
            'exact',
            'normalised',
            'ambiguous',
            'not_found'
        )
    ),
    created_by_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES research_tasks(task_id) ON DELETE SET NULL
);
```

进入人工复核包的最低要求：

```text
quote_match_status ∈ {exact, normalised}
```

进入正式查询结果的最低要求：

```text
record_review_status ∈ {approved, approved_with_edits}
```

## 6.6 `claim_locators`

```sql
CREATE TABLE claim_locators (
    locator_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL UNIQUE,
    section_id TEXT,
    page INTEGER,
    paragraph_index INTEGER,
    figure_label TEXT,
    table_label TEXT,
    supplementary_label TEXT,
    character_start INTEGER,
    character_end INTEGER,
    locator_confidence TEXT NOT NULL CHECK (
        locator_confidence IN ('high', 'medium', 'low')
    ),
    FOREIGN KEY (claim_id) REFERENCES source_claims(claim_id) ON DELETE CASCADE,
    FOREIGN KEY (section_id) REFERENCES source_sections(section_id) ON DELETE SET NULL
);
```

正式批准的主张必须满足：

```text
page 非空，或 section_id 非空
```

## 6.7 `entities`

```sql
CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (
        entity_type IN (
            'material',
            'compound',
            'product',
            'method',
            'instrument',
            'property',
            'process',
            'company',
            'author',
            'institution',
            'application'
        )
    ),
    canonical_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    normalised_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE (entity_type, normalised_name)
);
```

## 6.8 `claim_entity_links`

```sql
CREATE TABLE claim_entity_links (
    claim_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (
        role IN (
            'subject',
            'object',
            'material',
            'method',
            'property',
            'condition',
            'application'
        )
    ),
    PRIMARY KEY (claim_id, entity_id, role),
    FOREIGN KEY (claim_id) REFERENCES source_claims(claim_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE
);
```

## 6.9 `processing_runs`

```sql
CREATE TABLE processing_runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT,
    source_id TEXT,
    module_name TEXT NOT NULL,
    model_name TEXT,
    model_mode TEXT,
    prompt_version TEXT,
    parser_name TEXT,
    parser_version TEXT,
    code_commit TEXT,
    input_hash TEXT NOT NULL,
    output_hash TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('started', 'completed', 'failed', 'cancelled')
    ),
    error_type TEXT,
    error_message TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (task_id) REFERENCES research_tasks(task_id) ON DELETE SET NULL,
    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE SET NULL
);
```

## 6.10 `review_decisions`

```sql
CREATE TABLE review_decisions (
    review_id TEXT PRIMARY KEY,
    object_type TEXT NOT NULL CHECK (
        object_type IN ('claim', 'source', 'entity_link')
    ),
    object_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (
        decision IN (
            'approve',
            'approve_with_edits',
            'reject',
            'mark_missing',
            'needs_followup'
        )
    ),
    original_content_json TEXT NOT NULL,
    edited_content_json TEXT,
    reviewer TEXT NOT NULL,
    review_reason TEXT,
    reviewed_at TEXT NOT NULL
);
```

## 6.11 `claim_revisions`

```sql
CREATE TABLE claim_revisions (
    revision_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    previous_content_json TEXT NOT NULL,
    new_content_json TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    change_reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES source_claims(claim_id) ON DELETE CASCADE
);
```

## 6.12 FTS5

建立两个全文索引：

```sql
CREATE VIRTUAL TABLE source_fts USING fts5(
    source_id UNINDEXED,
    title,
    section_text,
    tokenize = 'unicode61'
);

CREATE VIRTUAL TABLE claim_fts USING fts5(
    claim_id UNINDEXED,
    source_id UNINDEXED,
    source_quote,
    faithful_paraphrase,
    evidence_basis_description,
    tokenize = 'unicode61'
);
```

实现时需要选择：

1. 数据库触发器自动同步，或
2. Repository 层统一同步。

第一轮优先采用 Repository 层统一同步，代码更容易测试。必须有 FTS 重建命令。

## 6.13 索引

至少建立：

```sql
CREATE INDEX idx_sources_doi ON sources(doi);
CREATE INDEX idx_sources_created_at ON sources(created_at);
CREATE INDEX idx_sections_source_sequence
    ON source_sections(source_id, sequence_number);
CREATE INDEX idx_claims_source ON source_claims(source_id);
CREATE INDEX idx_claims_task ON source_claims(task_id);
CREATE INDEX idx_claims_review_status
    ON source_claims(record_review_status);
CREATE INDEX idx_claims_type ON source_claims(claim_type);
CREATE INDEX idx_runs_source ON processing_runs(source_id);
CREATE INDEX idx_reviews_object
    ON review_decisions(object_type, object_id);
```

---

# 7. 资料包设计

每份来源使用一个独立资料包：

```text
workspace/external_evidence/sources/SRC-000001/
├── manifest.json
├── original/
│   └── main.pdf
├── parsed/
│   ├── document.md
│   ├── pages.jsonl
│   ├── sections.jsonl
│   └── parse_report.json
├── analysis/
│   ├── claims.raw.jsonl
│   ├── claims.validated.jsonl
│   ├── unresolved_items.jsonl
│   └── source_record.md
└── provenance/
    └── processing_runs.jsonl
```

## 7.1 `manifest.json`

必须包含：

```json
{
  "source_id": "SRC-000001",
  "source_type": "journal_article",
  "title": null,
  "original_file": "original/main.pdf",
  "original_file_sha256": "...",
  "origin_scope": "external",
  "scientific_verification_status": "unverified",
  "created_at": "...",
  "updated_at": "...",
  "assets": []
}
```

## 7.2 不可变规则

- `original/` 下的原始文件导入后不得修改。
- 重新解析只更新 `parsed/` 和 `analysis/`。
- 原始文件变化后必须生成新的 SHA-256。
- 同一 SHA-256 不得生成第二个来源记录。
- 资料包中的 JSONL 应足以重建数据库主要内容。

---

# 8. Agent 工作流设计

第一轮可使用显式 Python 工作流，也可以使用 LangGraph。无论使用哪种实现，节点和状态必须保持清晰。

## 8.1 状态模型

```python
class EvidenceAgentState(TypedDict):
    run_id: str
    task_id: str
    source_id: str

    input_file: str
    source_package_dir: str

    task_mode: str
    analysis_depth: str
    research_question: str | None
    research_background: str | None

    parsed_pages: list[dict]
    parsed_sections: list[dict]

    raw_claims: list[dict]
    validated_claims: list[dict]
    rejected_claims: list[dict]
    unresolved_items: list[dict]

    review_packet_path: str | None
    errors: list[dict]
    status: str
```

不要把整篇 PDF 的全部文本重复存储在每个状态字段中。状态保存路径、哈希和必要摘要，正文由资料包读取。

## 8.2 节点

```text
validate_input
→ create_or_load_source
→ parse_pdf
→ assess_parse_quality
→ create_analysis_prompt
→ extract_claims
→ validate_claims
→ persist_draft
→ generate_review_packet
→ wait_for_review
→ apply_review
→ index_approved_content
→ export_source_record
→ final_verification
```

## 8.3 路由

### 输入无效

```text
validate_input
→ failed
```

### 文件已存在且解析版本未变化

```text
create_or_load_source
→ load_existing_parse
```

### 解析质量不足

```text
assess_parse_quality
→ unresolved
```

第一轮不自动启动 OCR。应生成明确错误：

```text
SCAN_OR_LOW_TEXT_DENSITY
```

### LLM 输出无法解析

```text
extract_claims
→ retry_once_with_repair_prompt
→ failed 或继续
```

最多自动修复一次。仍然失败时保存原始响应并停止，不得用空列表伪装成功。

### 原文无法匹配

```text
validate_claims
→ rejected_claims
```

此类记录不能进入人工审批的普通列表，应进入「定位失败」区域。

### 人工未复核

```text
wait_for_review
```

不得自动标记工作流完成。

## 8.4 幂等性

以下动作必须幂等：

- 导入同一 PDF。
- 执行数据库迁移。
- 重新建立 FTS。
- 重新生成复核包。
- 重复应用同一 `review_id`。
- 重新导出资料记录。

验收方法：

- 连续执行两次命令。
- 第二次不得生成重复数据库记录。
- 输出文件内容哈希可相同或仅时间戳变化。
- 数据库行数不得无原因增加。

---

# 9. 主张提取数据合同

## 9.1 LLM 输入

输入必须包含：

- 研究任务。
- 当前章节。
- 页码。
- 章节标题。
- 附近段落。
- 已识别的图表标题。
- 允许的主张类型。
- 禁止行为。
- JSON Schema。

不要一次把整篇论文无分段地交给模型后要求输出全部主张。第一轮按章节或受控块提取，再统一去重。

## 9.2 LLM 输出

每条候选主张：

```json
{
  "claim_type": "author_interpretation",
  "source_quote": "原文中的连续文本",
  "faithful_paraphrase": "忠实转述",
  "evidence_basis_description": "作者依据哪些实验、图或表提出该主张",
  "scope_description": "主张适用的样品、条件或范围",
  "author_hedging": "suggests",
  "locator_hint": {
    "page": 6,
    "section_heading": "Results and Discussion",
    "figure_label": "Figure 3",
    "table_label": null
  },
  "entities": [
    {
      "entity_type": "material",
      "display_name": "HP-β-CD",
      "role": "material"
    }
  ]
}
```

## 9.3 忠实转述规则

模型必须：

- 保留作者限定语气。
- 保留可能性和不确定性。
- 保留样品和条件范围。
- 区分观察和解释。
- 区分结果和因果推断。
- 区分作者结论和 Agent 提醒。
- 不补充原文不存在的实验条件。
- 不将综述转述伪装成原始实验。
- 不把图表中未明确报告的数值写入记录。

## 9.4 Prompt 版本

Prompt 必须单独文件化：

```text
src/evidence_agent/extraction/prompts/
├── claim_extraction_v1.md
├── repair_json_v1.md
└── entity_extraction_v1.md
```

`processing_runs.prompt_version` 保存版本名和文件哈希。

---

# 10. 确定性校验设计

LLM 输出不得直接写入正式主张表。先通过以下校验。

## 10.1 Schema 校验

检查：

- 必填字段。
- 枚举字段。
- 字符串长度。
- locator 结构。
- entities 结构。

失败时：

- 保存原始模型响应。
- 尝试一次 JSON 修复。
- 修复失败后标记运行失败。

## 10.2 原文匹配

依次执行：

1. 精确匹配。
2. Unicode 规范化后匹配。
3. 合并连续空白后匹配。
4. 规范化连字符和换行后匹配。

输出：

```text
exact
normalised
ambiguous
not_found
```

禁止模糊语义相似度直接替代原文匹配。

## 10.3 定位校验

检查：

- 页码是否存在。
- 章节是否属于该来源。
- quote 是否位于该页或该章节。
- 图号或表号是否在上下文中存在。
- 字符区间是否越界。

## 10.4 泄漏校验

检查：

- `origin_scope` 必须为 `external`。
- `scientific_verification_status` 必须为 `unverified`。
- 不得出现内部样品 ID。
- 不得写入任何内部数据库连接。
- 数据库表名不得含 `internal_measurements` 等内部结构。
- 导出中必须显示「外部来源、未经内部验证」。

## 10.5 重复主张检测

第一轮采用保守规则：

- 同一来源。
- 相同规范化 quote。
- 相同 claim type。

满足时判定重复。

不要在第一轮通过语义相似度自动合并不同表述。

---

# 11. 人工复核设计

## 11.1 复核包格式

第一轮生成：

```text
workspace/external_evidence/review/RUN-000001/
├── review_packet.md
├── review_packet.html
├── claims_for_review.csv
├── claims_for_review.jsonl
├── failed_locators.jsonl
└── review_instructions.md
```

HTML 可以是静态页面，不要求完整 Web 应用。

## 11.2 每条主张展示

必须展示：

- 资料标题。
- 来源类型。
- PDF 相对路径。
- 页码。
- 章节。
- 原文前后文。
- 模型选择的原文。
- 忠实转述。
- 证据依据描述。
- 主张类型。
- 作者限定词。
- 实体标签。
- 原文匹配状态。
- 定位置信度。
- 处理模型。
- Prompt 版本。
- 决策输入列。

## 11.3 决策字段

CSV 至少包含：

```text
claim_id
decision
edited_source_quote
edited_faithful_paraphrase
edited_evidence_basis_description
edited_claim_type
edited_page
edited_section
review_reason
reviewer
```

`decision` 允许：

```text
approve
approve_with_edits
reject
mark_missing
needs_followup
```

## 11.4 应用复核决定

执行顺序：

1. 读取 CSV。
2. 校验 `claim_id`。
3. 校验决定值。
4. 对编辑后的 quote 重新做原文匹配。
5. 对编辑后的 locator 重新校验。
6. 写入 `review_decisions`。
7. 如有编辑，先写入 `claim_revisions`。
8. 更新 `source_claims`。
9. 只把批准记录写入 FTS。
10. 生成应用报告。

重复应用同一复核文件时，不得重复写入决定。

## 11.5 人工复核完成标准

一个来源可标记为「资料分析完成」前必须满足：

- 所有候选主张都有决策，或明确标为待跟进。
- 所有批准主张原文匹配通过。
- 所有批准主张有页码或章节定位。
- 所有编辑都有修订历史。
- 拒绝记录保留，不从运行档案中删除。
- 复核人和复核时间存在。

---

# 12. CLI 设计

第一轮命令：

```bash
evidence-agent init
evidence-agent db migrate
evidence-agent db check
evidence-agent db rebuild

evidence-agent ingest path/to/paper.pdf
evidence-agent parse SRC-000001

evidence-agent task create \
  --title "测试任务" \
  --request "分析论文中与目标材料相关的作者主张" \
  --mode analyse_uploaded \
  --depth task_focused

evidence-agent analyse SRC-000001 \
  --task TASK-000001

evidence-agent review export RUN-000001
evidence-agent review apply \
  workspace/external_evidence/review/RUN-000001/review_decisions.csv

evidence-agent query "环糊精 水溶性"
evidence-agent source show SRC-000001
evidence-agent claim show CLM-000001
evidence-agent export source SRC-000001 --format markdown

evidence-agent verify round1
```

## 12.1 CLI 返回码

- `0`：成功。
- `1`：普通运行失败。
- `2`：输入或参数错误。
- `3`：数据库错误。
- `4`：解析错误。
- `5`：模型输出错误。
- `6`：复核数据错误。
- `7`：验收未通过。

## 12.2 CLI 输出要求

终端输出必须简洁，同时将详细日志写入文件。每次运行输出：

```text
run_id
status
source_id
task_id
output_paths
warning_count
error_count
next_action
```

---

# 13. 分阶段执行任务

以下任务必须按顺序推进。每个任务都有明确的完成证据。

---

## TASK 00：仓库盘点与基线冻结

### 目标

确认现有仓库状态，避免覆盖已有实现，并形成可追溯基线。

### 前置条件

无。

### 详细执行方法

1. 确认当前工作目录。
2. 检查是否为 Git 仓库。
3. 列出根目录两层以内文件。
4. 阅读：
   - `README.md`
   - `AGENTS.md`
   - `pyproject.toml`
   - 已有计划和架构文件
5. 执行现有测试。
6. 记录 Python 版本。
7. 记录依赖管理方式。
8. 检查是否已有数据库、解析器或工作区。
9. 创建或更新：
   - `docs/plans/ROUND1_EXECUTION_LOG.md`
   - `docs/roadmap.md`
10. 在执行日志中写入基线：
    - 当前 commit
    - 当前测试结果
    - 已有功能
    - 风险
    - 计划适配点

### 推荐命令

```bash
pwd
git status --short
git rev-parse --show-toplevel
git rev-parse HEAD
find . -maxdepth 2 -type f | sort
python --version
python -m pip --version
pytest -q
```

如果不是 Git 仓库，不强制初始化，但必须在日志中说明。

### 产物

- `docs/plans/ROUND1_EXECUTION_LOG.md`
- 仓库盘点记录。
- 当前测试结果。

### 完成判定

- [ ] 已阅读现有关键文件。
- [ ] 已执行现有测试。
- [ ] 已记录 commit 或「非 Git 仓库」。
- [ ] 已确认不会覆盖已有重要文件。
- [ ] 已列出第一轮需要新增和修改的文件。
- [ ] 已记录所有测试失败，未隐藏失败。

### 失败处理

现有测试失败时：

- 记录失败。
- 判断与本轮是否相关。
- 不得直接修改无关测试。
- 在开始新功能前建立「基线失败列表」。

---

## TASK 01：冻结第一轮数据合同与范围

### 目标

先写清楚系统如何表示来源、主张、定位和复核，再开始编码。

### 前置条件

TASK 00 完成。

### 详细执行方法

1. 创建 `docs/claim_contract.md`。
2. 创建 `docs/database_design.md`。
3. 创建 `docs/review_protocol.md`。
4. 将本计划中的数据库字段转换为 Pydantic 模型草案。
5. 明确：
   - 外部来源身份。
   - 科学验证状态。
   - 主张类型。
   - 原文匹配状态。
   - 复核状态。
   - 定位最低要求。
6. 写出至少三条完整示例：
   - reported_result
   - author_interpretation
   - author_limitation
7. 写出至少三条无效示例：
   - 没有原文。
   - 原文不在资料中。
   - 把作者推测改写成确定事实。
8. 定义 JSON Schema 或 Pydantic schema。
9. 为所有枚举编写测试。

### 产物

- `docs/claim_contract.md`
- `docs/database_design.md`
- `docs/review_protocol.md`
- `src/evidence_agent/schemas/*.py`
- `tests/unit/test_schemas.py`

### 完成判定

- [ ] 所有核心字段有定义和用途。
- [ ] 外部身份和科学验证状态分离。
- [ ] Pydantic 模型能拒绝无效枚举。
- [ ] Pydantic 模型能拒绝缺少原文的主张。
- [ ] 示例可以通过 schema。
- [ ] 无效示例会失败。
- [ ] `pytest tests/unit/test_schemas.py -q` 通过。

### Review 检查

人工检查以下问题：

- 字段是否会让外部资料和内部数据混淆。
- `approved` 是否容易被误解为科学真实。
- 主张是否可以准确回到来源。
- 是否存在过早的复杂设计。

---

## TASK 02：项目骨架与开发环境

### 目标

建立可安装、可测试、可执行的 Python 项目。

### 前置条件

TASK 01 完成。

### 详细执行方法

1. 创建目标目录结构。
2. 配置 `pyproject.toml`。
3. 最低支持 Python 3.11。
4. 配置：
   - pytest
   - ruff
   - mypy 或 pyright 二选一
   - Pydantic
   - Typer
   - SQLite 标准库
   - PDF 解析依赖
5. 设置 CLI 入口：
   ```toml
   evidence-agent = "evidence_agent.cli:app"
   ```
6. 创建 `.env.example`。
7. 创建 `config.py`：
   - 工作区路径。
   - 数据库路径。
   - LLM provider。
   - 模型名。
   - Prompt 版本。
8. 创建 `AGENTS.md`，写入：
   - 本轮范围。
   - 必须运行测试。
   - 外部数据隔离规则。
   - 禁止自动扩大范围。
9. 安装项目。
10. 运行空测试和 CLI 帮助。

### 推荐命令

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
ruff check .
python -m mypy src
pytest -q
evidence-agent --help
```

### 产物

- 可安装项目。
- CLI 帮助。
- 开发依赖。
- `AGENTS.md`。

### 完成判定

- [ ] 新环境安装成功。
- [ ] `evidence-agent --help` 返回 0。
- [ ] `ruff check .` 通过。
- [ ] 类型检查通过，或已记录少量明确基线。
- [ ] `pytest -q` 通过。
- [ ] `.env.example` 不含真实密钥。
- [ ] 工作区路径可由环境变量覆盖。

---

## TASK 03：SQLite 数据库与迁移

### 目标

建立可重复创建、检查和重建的外部证据数据库。

### 前置条件

TASK 02 完成。

### 详细执行方法

1. 创建三份迁移 SQL。
2. 实现迁移表：
   ```text
   schema_migrations
   ```
3. 每次迁移记录版本和应用时间。
4. 实现：
   - `db migrate`
   - `db check`
   - `db rebuild`
5. `db check` 至少检查：
   - foreign_keys
   - integrity_check
   - 表是否存在
   - 索引是否存在
   - FTS 是否存在
6. 编写 Repository 基础层。
7. 编写事务封装。
8. 编写测试：
   - 空库迁移。
   - 重复迁移。
   - 外键约束。
   - 唯一 SHA-256。
   - 非 external 来源写入失败。
   - 非法科学验证状态失败。
9. 实现测试数据库 fixture。

### 推荐命令

```bash
evidence-agent db migrate
evidence-agent db check
sqlite3 workspace/external_evidence/evidence.sqlite ".tables"
pytest tests/unit/test_database.py -q
pytest tests/integration/test_migrations.py -q
```

### 产物

- `migrations/*.sql`
- 数据库连接和迁移代码。
- 数据库测试。
- `database_design.md` 与实际 schema 一致。

### 完成判定

- [ ] 空库可以迁移到最新版本。
- [ ] 第二次迁移不报错且不重复建表。
- [ ] `PRAGMA integrity_check` 返回 `ok`。
- [ ] `PRAGMA foreign_key_check` 无结果。
- [ ] 相同 SHA-256 无法建立两个来源。
- [ ] `origin_scope != external` 无法写入。
- [ ] FTS 表存在。
- [ ] 数据库测试全部通过。

### 失败处理

数据库 schema 与文档不一致时，优先修正文档或迁移，不得在 Repository 中用隐藏兼容逻辑掩盖。

---

## TASK 04：资料包与 PDF 导入

### 目标

稳定导入 PDF，创建不可变原始资料包，并支持重复导入识别。

### 前置条件

TASK 03 完成。

### 详细执行方法

1. 验证文件存在、可读、扩展名和 MIME。
2. 检查 PDF magic bytes。
3. 计算 SHA-256。
4. 查询数据库是否已有相同哈希。
5. 若已存在：
   - 返回已有 `source_id`。
   - 不重复复制。
   - 记录一次幂等命中。
6. 若不存在：
   - 生成 `SRC-xxxxxx`。
   - 创建资料包。
   - 复制原始 PDF。
   - 写入 manifest。
   - 写入 sources。
   - 写入 source_assets。
7. 文件复制后再次计算目标文件哈希。
8. 源文件和目标文件哈希必须一致。
9. 加入最大文件大小配置。
10. 对损坏 PDF 返回明确错误。

### 推荐命令

```bash
evidence-agent ingest tests/fixtures/sample_article.pdf
evidence-agent ingest tests/fixtures/sample_article.pdf
```

### 产物

- `workspace/external_evidence/sources/SRC-*/`
- 数据库来源记录。
- 导入日志。

### 完成判定

- [ ] 合法 PDF 导入成功。
- [ ] 原始文件哈希一致。
- [ ] manifest 字段完整。
- [ ] 重复导入返回同一 source_id。
- [ ] 数据库 sources 行数不增加。
- [ ] 非 PDF 文件被拒绝。
- [ ] 损坏 PDF 被拒绝。
- [ ] 测试覆盖以上情况。

---

## TASK 05：PDF 解析与页码映射

### 目标

将 PDF 转换为可追溯的页面、章节和 Markdown，不处理扫描版 OCR。

### 前置条件

TASK 04 完成。

### 详细执行方法

1. 选择一个主 PDF 解析器。
2. 提取每页文本。
3. 保存 `pages.jsonl`：
   ```json
   {
     "page": 1,
     "text": "...",
     "char_count": 1800,
     "text_sha256": "..."
   }
   ```
4. 计算：
   - 总页数。
   - 有文本页数。
   - 平均字符数。
   - 空白页比例。
5. 判断低文本密度：
   - 若绝大多数页面无文本，标记扫描版或解析失败。
6. 基础章节识别：
   - Abstract
   - Introduction
   - Experimental
   - Materials and Methods
   - Results
   - Discussion
   - Conclusion
   - References
7. 保存 `sections.jsonl`。
8. 生成 `document.md`，保留页分隔标记。
9. 识别文本中的 Figure、Fig.、Table、Scheme 等标签。
10. 生成 `parse_report.json`。
11. 所有解析结果记录解析器名称和版本。
12. 重新解析时不得覆盖原始 PDF。

### 完成判定

- [ ] 每页有独立记录。
- [ ] 页码与 PDF 页顺序一致。
- [ ] 文档 Markdown 可人工阅读。
- [ ] 章节顺序正确。
- [ ] 解析报告含质量指标。
- [ ] 扫描版 fixture 被识别为低文本密度。
- [ ] 低文本密度文件不会进入 LLM 提取。
- [ ] `pytest tests/unit/test_pdf_parser.py -q` 通过。
- [ ] `pytest tests/integration/test_parse_pipeline.py -q` 通过。

### 人工 Review

随机抽查至少 3 页：

- 页面文本是否来自正确页。
- 数学符号、上下标和连字符是否产生严重错误。
- 图表标签是否可定位。
- 章节边界是否基本合理。

---

## TASK 06：LLM Provider 和可离线测试替身

### 目标

将模型调用封装为可替换 Provider，并保证没有 API Key 时仍能运行测试。

### 前置条件

TASK 05 完成。

### 详细执行方法

1. 定义 Provider Protocol：
   ```python
   class ClaimExtractionProvider(Protocol):
       def extract_claims(self, request: ExtractionRequest) -> ExtractionResponse:
           ...
   ```
2. 实现：
   - `DeepSeekProvider`
   - `MockProvider`
3. DeepSeekProvider 配置：
   - `deepseek-v4-pro`
   - thinking enabled
   - reasoning effort max
   - JSON 输出
4. 不把 API Key 写入日志。
5. 保存：
   - 模型名。
   - Prompt 版本。
   - 输入哈希。
   - 输出哈希。
6. 对网络错误、429、超时和 JSON 失败做明确处理。
7. 自动重试采用有限次数和退避。
8. MockProvider 从 fixture 返回固定合法响应。
9. 测试默认使用 MockProvider。
10. 真实 API 测试使用显式环境变量启用，不进入普通 CI。

### 完成判定

- [ ] 无 API Key 时单元和集成测试可运行。
- [ ] MockProvider 输出可重复。
- [ ] Provider 不泄露密钥。
- [ ] Provider 保存模型与 Prompt 版本。
- [ ] 非法 JSON 会进入修复或失败流程。
- [ ] 429 和超时不会导致未捕获异常。
- [ ] DeepSeek 适配代码遵守思考模式和工具调用兼容要求。

---

## TASK 07：主张分块提取

### 目标

从已解析资料中生成候选作者主张，不直接写入正式记录。

### 前置条件

TASK 06 完成。

### 详细执行方法

1. 设计受控文本块：
   - 优先按章节。
   - 长章节按段落窗口拆分。
   - 每块保留页码范围。
   - 重叠少量上下文，避免跨块丢失。
2. 过滤：
   - 参考文献列表。
   - 页眉页脚。
   - 极短无意义块。
3. 对每块调用 Provider。
4. 输出写入：
   - `claims.raw.jsonl`
5. 每条候选主张记录：
   - block_id
   - page range
   - model
   - prompt_version
   - raw_response_id
6. 合并完全相同 quote 的重复记录。
7. 不做跨语义自动合并。
8. 对 task-focused 模式，仅提取与任务相关主张。
9. 对 source-complete 模式，按允许类型提取全文主张。
10. 生成提取报告：
    - 处理块数。
    - 成功块数。
    - 失败块数。
    - 候选主张数。
    - 重复数。

### 完成判定

- [ ] 每个候选主张有来源块。
- [ ] 页码范围保留。
- [ ] 参考文献列表不会产生大量主张。
- [ ] 原始模型响应可追溯。
- [ ] 同一 quote 的重复记录被识别。
- [ ] task-focused 和 source-complete 行为不同。
- [ ] MockProvider 端到端提取测试通过。

---

## TASK 08：主张确定性校验

### 目标

只让能够追溯到原始资料的主张进入复核包。

### 前置条件

TASK 07 完成。

### 详细执行方法

1. 对每条候选记录执行 Schema 校验。
2. 执行 quote 精确和规范化匹配。
3. 确定 source_quote 在哪个页面和章节。
4. 校验 locator_hint。
5. 修正可确定的页码和字符范围。
6. 检查图表标签。
7. 执行外部身份泄漏检查。
8. 检查科学验证状态。
9. 分类：
   - validated
   - failed_locator
   - invalid_schema
   - duplicated
10. 保存：
    - `claims.validated.jsonl`
    - `unresolved_items.jsonl`
11. 只有 validated 记录写入数据库的 pending 区。
12. failed 记录保存但不进入普通审批列表。

### 完成判定

- [ ] quote 不存在的记录不会进入 validated。
- [ ] quote 存在但模型页码错误时，可由确定性定位修正。
- [ ] 多处重复 quote 标记 ambiguous。
- [ ] 所有 validated 记录有 source_id。
- [ ] 所有 validated 记录为 external。
- [ ] 所有 validated 记录科学状态为 unverified。
- [ ] 所有 validated 记录有页码或 section_id。
- [ ] 泄漏测试通过。
- [ ] Quote validator 测试覆盖换行、连字符和 Unicode 规范化。

---

## TASK 09：复核包生成

### 目标

让用户能够高效判断主张是否忠实、定位是否正确。

### 前置条件

TASK 08 完成。

### 详细执行方法

1. 按来源和页码排序主张。
2. 为每条主张生成上下文：
   - 前一段。
   - 命中段。
   - 后一段。
3. 高亮 source_quote。
4. 生成 CSV、JSONL、Markdown 和静态 HTML。
5. CSV 预填空白决策字段。
6. 失败定位记录单独展示。
7. 在复核说明中解释：
   - 批准只表示忠实记录。
   - 不表示科学真实性。
8. 为每条记录提供原始 PDF 相对路径和页码。
9. 生成复核统计：
   - 待审核。
   - 定位失败。
   - 主张类型分布。
   - 高风险类型。

### 完成判定

- [ ] CSV 可正常打开。
- [ ] HTML 无外部服务也能打开。
- [ ] 所有主张有上下文。
- [ ] source_quote 高亮正确。
- [ ] 原始 PDF 路径有效。
- [ ] 定位失败记录单独列出。
- [ ] 复核说明明确区分记录批准和科学验证。
- [ ] 重复生成不会创建重复数据库记录。

---

## TASK 10：复核决定应用与修订历史

### 目标

可靠应用人工决定，保留所有修改历史。

### 前置条件

TASK 09 完成。

### 详细执行方法

1. 读取复核 CSV。
2. 检查必填列。
3. 检查 claim_id 是否存在且属于该运行。
4. 检查重复 claim_id。
5. 对 approve：
   - 写入 review_decisions。
   - 更新状态 approved。
6. 对 approve_with_edits：
   - 校验编辑内容。
   - 重新匹配 quote。
   - 重新校验定位。
   - 写入 claim_revisions。
   - 写入 review_decisions。
   - 更新主张。
7. 对 reject：
   - 更新状态 rejected。
   - 保留原记录。
8. 对 mark_missing：
   - 保存为运行级问题。
9. 对 needs_followup：
   - 保持不可正式检索状态。
10. 事务中执行全部更新。
11. 任一严重错误时整批回滚。
12. 生成 apply report。
13. 已批准记录进入 FTS。

### 完成判定

- [ ] 批准状态正确更新。
- [ ] 编辑后的 quote 必须重新匹配。
- [ ] 编辑前后内容都有记录。
- [ ] 拒绝记录仍可追溯。
- [ ] 错误复核文件不会造成部分写入。
- [ ] 重复应用同一 review_id 幂等。
- [ ] 只有批准记录进入正式搜索。
- [ ] 事务回滚测试通过。

---

## TASK 11：全文搜索和来源回溯

### 目标

搜索已审核作者主张，并返回明确来源。

### 前置条件

TASK 10 完成。

### 详细执行方法

1. 实现 claim FTS 查询。
2. 默认只查：
   - approved
   - approved_with_edits
3. 支持过滤：
   - claim_type
   - source_id
   - entity_type
   - entity_name
4. 返回：
   - claim_id
   - snippet
   - source title
   - page
   - section
   - source path
   - record review status
   - scientific verification status
5. 明确显示：
   ```text
   外部来源，科学状态：未经内部验证
   ```
6. 实现 `source show` 和 `claim show`。
7. 实现 FTS 重建。
8. 测试中英文关键词。
9. 测试拒绝记录不被默认检索。

### 完成判定

- [ ] 已批准记录可搜索。
- [ ] pending 和 rejected 默认不可搜索。
- [ ] 搜索结果能返回原始资料路径。
- [ ] 页码或章节存在。
- [ ] 外部身份标签显示。
- [ ] FTS 重建后结果一致。
- [ ] 中文和英文 fixture 均可搜索。
- [ ] SQL 注入式输入不会破坏查询。

---

## TASK 12：资料记录导出

### 目标

为单份资料生成可人工阅读的外部资料记录。

### 前置条件

TASK 11 完成。

### 详细执行方法

1. 读取来源元数据。
2. 读取已批准主张。
3. 按类型和页码组织。
4. 生成 `source_record.md`。
5. 每条记录包括：
   - 作者原文。
   - 忠实转述。
   - 依据描述。
   - 页码和图表。
   - 作者限定词。
   - 外部、未经内部验证标签。
6. 在报告开头列出：
   - 资料身份。
   - 原始文件哈希。
   - 解析器版本。
   - 模型和 Prompt 版本。
   - 复核人。
7. 在报告结尾列出：
   - 拒绝记录数量。
   - 待跟进数量。
   - 已知解析限制。
8. 同时导出 JSONL。
9. 导出不得包含未批准主张，除非使用显式 `--include-pending`。

### 完成判定

- [ ] Markdown 可阅读。
- [ ] 每条主张可回溯。
- [ ] 默认不含 rejected。
- [ ] 默认不含 pending。
- [ ] 外部身份标签明显。
- [ ] 模型、Prompt 和处理版本可追踪。
- [ ] 同一输入重复导出内容稳定。

---

## TASK 13：数据库重建

### 目标

证明 SQLite 不是唯一事实来源，资料包可恢复数据库。

### 前置条件

TASK 12 完成。

### 详细执行方法

1. 创建数据库备份。
2. 使用新的空数据库路径。
3. 扫描所有资料包 manifest。
4. 导入：
   - sources
   - assets
   - sections
   - claims
   - locators
   - processing runs
5. 从 review 决定恢复审核状态。
6. 重建 FTS。
7. 比较原数据库和重建库：
   - 表行数。
   - source_id 集合。
   - claim_id 集合。
   - 审核状态。
   - 搜索结果。
8. 输出重建报告。
9. 不允许覆盖原数据库，除非显式 `--replace`。

### 完成判定

- [ ] 新数据库创建成功。
- [ ] source_id 集合一致。
- [ ] approved claim_id 集合一致。
- [ ] FTS 查询结果一致。
- [ ] 外键检查通过。
- [ ] 原数据库未被覆盖。
- [ ] 重建过程有完整报告。

---

## TASK 14：Golden Set 和科学内容 Review

### 目标

建立一个可重复评估主张忠实度的最小人工样本集。

### 前置条件

TASK 08 至少完成。

### 详细执行方法

准备至少 5 份可合法使用的测试资料或自制等价 fixture，覆盖：

1. 明确实验结果。
2. 带「suggests」「may」「possibly」的作者解释。
3. 作者声明的限制。
4. 图表支持但正文表达较弱的结论。
5. 同一句话在多个页面重复。
6. 至少一份中文资料。
7. 至少一份英文资料。
8. 至少一份解析质量较差但仍可读的 PDF。

人工标注：

```text
source_id
expected_claim
claim_type
source_quote
page
section
required_hedging
evidence_basis
must_extract
```

计算：

- 核心主张召回率。
- 无依据主张率。
- 原文匹配率。
- 定位准确率。
- 主张类型准确率。
- 限定词保留率。
- 人工接受率。

第一轮门槛建议：

```text
无依据主张率：正式批准记录中 0%
原文匹配率：100%
批准记录定位完整率：100%
限定词保留率：≥ 95%
核心主张召回率：≥ 80%
主张类型准确率：≥ 85%
```

注意：

- 召回率不达标可以进入下一轮优化。
- 无依据主张率不能通过降低人工标准来掩盖。
- 机器指标不能代替人工判读。

### 产物

- `tests/golden/annotations.jsonl`
- `scripts/evaluate_golden.py`
- `artifacts/round1_golden_report.md`

### 完成判定

- [ ] Golden Set 文件存在。
- [ ] 评估脚本可运行。
- [ ] 指标计算有测试。
- [ ] 无依据批准记录为 0。
- [ ] 所有失败样本有归因。
- [ ] 结果写入完成报告。

---

## TASK 15：端到端验收

### 目标

在全新临时工作区中走通完整闭环。

### 前置条件

TASK 00 至 TASK 14 完成。

### 详细执行方法

端到端脚本必须执行：

```text
创建临时工作区
→ 初始化数据库
→ 导入 fixture PDF
→ 重复导入验证幂等
→ 解析 PDF
→ 创建研究任务
→ 使用 MockProvider 提取主张
→ 确定性校验
→ 生成复核包
→ 应用预制人工复核决定
→ 搜索批准主张
→ 打开来源记录
→ 导出 Markdown
→ 重建数据库
→ 比较重建前后结果
```

### 推荐命令

```bash
python scripts/smoke_test.py
python scripts/verify_round1.py
pytest tests/e2e -q
```

### 验收输出

`verify_round1.py` 最后打印：

```text
ROUND1_VERIFICATION=PASS
database_integrity=PASS
ingest_idempotency=PASS
quote_traceability=PASS
review_workflow=PASS
fts_search=PASS
database_rebuild=PASS
external_data_isolation=PASS
```

任何一项失败，程序返回码必须为 7。

### 完成判定

- [ ] 全新临时目录中运行成功。
- [ ] 不依赖开发者机器上的隐式文件。
- [ ] 不需要真实 API Key。
- [ ] 所有 PASS 标记存在。
- [ ] 返回码为 0。
- [ ] `pytest -q` 全部通过。
- [ ] `ruff check .` 通过。
- [ ] 类型检查通过。

---

## TASK 16：README、完成报告和交付审查

### 目标

使其他人可以安装、运行、复核和理解当前边界。

### 前置条件

TASK 15 完成。

### 详细执行方法

1. 更新 README：
   - 项目定位。
   - 第一轮能力。
   - 明确不做的内容。
   - 安装。
   - 快速开始。
   - CLI 示例。
   - 人工复核。
   - 外部资料安全边界。
   - 已知限制。
2. 创建：
   - `docs/architecture.md`
   - `docs/known_limitations.md`
   - `docs/ROUND1_COMPLETION_REPORT.md`
3. 完成报告包含：
   - 实际完成范围。
   - 未完成范围。
   - 主要架构。
   - 数据库版本。
   - 真实执行命令。
   - 测试结果。
   - Golden Set 指标。
   - 失败样本。
   - 已知风险。
   - 下一轮建议。
4. 执行 README 中所有命令。
5. 检查 Git 差异。
6. 检查是否意外提交：
   - API Key。
   - 大型 PDF。
   - 数据库临时文件。
   - 用户私人资料。
7. 生成最终文件清单。

### 完成判定

- [ ] README 命令已真实验证。
- [ ] 完成报告包含测试结果。
- [ ] 完成报告没有虚构的已完成项。
- [ ] 已知限制清楚。
- [ ] 第一轮之外的工作进入 roadmap。
- [ ] 仓库无密钥。
- [ ] 仓库无不应提交的用户资料。
- [ ] 最终 `git diff` 已人工或模型逐文件检查。
- [ ] `verify_round1.py` 最终通过。

---

# 14. 测试矩阵

| 测试类别 | 必测内容 | 完成标准 |
|---|---|---|
| Schema | 枚举、必填字段、非法状态 | 全部通过 |
| 数据库 | 迁移、外键、唯一约束、事务 | 全部通过 |
| 导入 | 合法 PDF、重复文件、损坏文件 | 行为符合约定 |
| 解析 | 页码、章节、低文本密度 | 全部通过 |
| Provider | Mock、异常、非法 JSON | 全部受控 |
| Quote | 精确、空白、连字符、Unicode | 全部通过 |
| Locator | 页码、章节、多重命中 | 全部通过 |
| Leakage | external 固定、内部表隔离 | 污染为 0 |
| Review | 批准、编辑、拒绝、回滚 | 全部通过 |
| FTS | 中英文、状态过滤、重建 | 全部通过 |
| Export | 默认只导出批准记录 | 全部通过 |
| Rebuild | 资料包恢复数据库 | 关键集合一致 |
| E2E | 完整闭环 | PASS |
| Golden Set | 忠实度指标 | 达到门槛或明确归因 |

---

# 15. Review 方法

## 15.1 每个 TASK 的代码 Review

DeepSeek 完成每个 TASK 后必须回答以下问题，并写入执行日志：

1. 修改了哪些文件？
2. 为什么修改？
3. 运行了哪些命令？
4. 测试结果是什么？
5. 有哪些失败或警告？
6. 是否修改了任务范围外的文件？
7. 是否新增技术债？
8. 下一任务的前置条件是否满足？

## 15.2 数据库 Review

检查：

- schema 与文档一致。
- 所有外键存在。
- 外部身份有数据库约束。
- 审核状态和科学验证状态没有混为一谈。
- FTS 只索引允许的记录。
- 数据库可以重建。
- 删除来源是否按预期级联。
- Review 历史不会随主张修改丢失。

## 15.3 Agent Review

检查：

- 每个节点职责单一。
- LLM 输出先校验后持久化。
- 异常不会静默吞掉。
- 重试次数有限。
- 运行可恢复。
- Prompt 有版本。
- 模型输出可追溯。
- 状态不重复存储整篇论文。
- MockProvider 足以离线测试。

## 15.4 科学内容 Review

人工逐条判断：

- 原文是否真实。
- 转述是否忠实。
- 是否保留限定词。
- 是否扩大适用范围。
- 是否把相关性写成因果。
- 是否把作者解释写成实验事实。
- 依据描述是否确实来自文中。
- 页码和章节是否正确。
- 外部身份是否明显。
- 是否误加入 Agent 自己的新分析。

## 15.5 完成状态规则

```text
completed：
所有验收条件满足，测试通过，产物存在。

blocked：
外部依赖缺失，且存在明确阻塞证据。

failed：
执行后未达到核心目标，需要返工。

partial：
禁止作为正式任务状态。
如只完成部分，状态保持 in_progress 或 failed。
```

---

# 16. 第一轮验收命令清单

最终至少执行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

ruff check .
python -m mypy src
pytest -q

evidence-agent init
evidence-agent db migrate
evidence-agent db check

evidence-agent ingest tests/fixtures/sample_article.pdf
evidence-agent parse SRC-000001

evidence-agent task create \
  --title "Round 1 acceptance" \
  --request "提取与测试任务相关的作者主张" \
  --mode analyse_uploaded \
  --depth task_focused

evidence-agent analyse SRC-000001 \
  --task TASK-000001 \
  --provider mock

evidence-agent review export RUN-000001
evidence-agent review apply tests/fixtures/review_decisions.csv

evidence-agent query "test keyword"
evidence-agent source show SRC-000001
evidence-agent export source SRC-000001 --format markdown

python scripts/rebuild_database.py \
  --source workspace/external_evidence/sources \
  --target /tmp/evidence_rebuilt.sqlite

python scripts/evaluate_golden.py
python scripts/smoke_test.py
python scripts/verify_round1.py
```

实际 ID 允许不同，但完成报告必须记录真实 ID 和真实输出。

---

# 17. 第一轮完成报告模板

```markdown
# Round 1 Completion Report

## 1. 状态

PASS / FAIL

## 2. 实际完成内容

逐项列出。

## 3. 未完成内容

逐项列出，不得隐藏。

## 4. 架构

说明数据库、资料包、工作流和复核流程。

## 5. 数据库

- schema version
- table list
- integrity check
- rebuild result

## 6. 实际执行命令

粘贴真实命令。

## 7. 测试结果

- ruff
- type check
- pytest
- e2e
- verify_round1

## 8. Golden Set

- claim recall
- unsupported claim rate
- quote match
- locator accuracy
- hedging preservation
- claim type accuracy

## 9. 已知失败样本

逐条说明。

## 10. 外部数据隔离检查

说明如何证明污染率为 0。

## 11. 已知限制

扫描版、图像、复杂双栏、公式、表格等。

## 12. 下一轮建议

只列建议，不在本轮实现。
```

---

# 18. DeepSeek-V4-Pro 最终执行提示

将本文件交给 DeepSeek-V4-Pro 时，附加以下指令：

```text
严格按照 ROUND1_DEEPSEEK_V4_PRO_PLAN.md 执行。

先完成 TASK 00，并读取仓库现状后再决定如何适配计划。
不要一次性实现所有任务。
每完成一个 TASK：
1. 运行该 TASK 的全部验收命令；
2. 更新 ROUND1_EXECUTION_LOG.md；
3. 汇报修改文件、测试结果和未解决问题；
4. 只有所有完成判定满足，才能进入下一个 TASK。

现有仓库结构优先，计划中的目录不是强制重建理由。
不得删除已有有效功能。
不得扩大第一轮范围。
不得把外部资料中的数值写入内部实验数据结构。
不得把人工批准解释为科学验证。
不得用模型生成内容代替真实命令和测试结果。

在没有人为阻塞的情况下持续执行到第一轮完成。
遇到局部实现选择时自行采用最简单、可测试、可审计的方案，
并将选择和理由写入执行日志。
```

---

# 19. 官方模型适配参考

制定本计划时采用的 DeepSeek 官方能力信息：

- DeepSeek-V4-Pro 于 2026-04-24 发布 V4 Preview。
- 官方 API 模型名为 `deepseek-v4-pro`。
- 官方服务提供 1M 上下文。
- 最大输出上限为 384K。
- 支持思考模式、JSON 输出和工具调用。
- 思考模式默认开启，复杂 Agent 任务可使用 `reasoning_effort=max`。
- 思考模式的工具调用轮次需要保留 `reasoning_content`。
- DeepSeek-V4 思考模式不应依赖 `tool_choice`。
- 官方提供 OpenAI 与 Anthropic 兼容接口。

参考：

- DeepSeek V4 Preview Release  
  https://api-docs.deepseek.com/news/news260424/
- Models & Pricing  
  https://api-docs.deepseek.com/quick_start/pricing/
- Thinking Mode  
  https://api-docs.deepseek.com/guides/thinking_mode/
- Integrate with AI Tools  
  https://api-docs.deepseek.com/guides/coding_agents/
- Using DeepSeek with Oh My Pi  
  https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/
