# Literature Evidence Agent — Round 1.1 RC2 完整 Coding Plan

> **执行工具**：OpenCode  
> **执行模型**：DeepSeek-V4-Pro  
> **目标仓库**：`ZanderKong/literature-evidence-agent`  
> **基线分支**：`fix/round1.1-remediation`  
> **基线 commit**：`a93c353800fce4e4680f29e2538ea612f0f66b07`  
> **目标分支**：`fix/round1.1-rc2-hardening`  
> **计划文件建议位置**：`plan/ROUND1_1_RC2_OPENCODE_DEEPSEEK_V4_PRO_CODING_PLAN.md`  
> **最终目标**：将当前「核心路径基本可运行，但验收、恢复和复核完整性不足」的 RC1，修复成可真实验收的 Round 1.1 RC2。

---

# 0. 计划摘要

当前版本已经实现：

```text
PDF 导入
→ PDF 解析
→ Mock/DeepSeek Provider
→ analyse 工作流
→ claims 和 locators 写入 SQLite
→ review export
→ review apply
→ FTS 查询
→ 资料导出
```

当前仍有六类阻断问题：

1. `verify round1` 多项检查仍然只检查表存在、`COUNT >= 0` 或 migration version。
2. 数据库重建没有保持原始 claim ID、locator ID、review status、decisions 和 revisions。
3. `approve_with_edits` 在 `source_sections` 为空时跳过 quote 校验，也没有完整校验 edited locator。
4. E2E 中 FTS 断言仍为 `len(results) >= 0`，没有覆盖真实 rebuild。
5. Golden Set 只有 5 条英文标注，部分指标仍返回 `manual_review_required`。
6. 旧执行日志仍将未完成任务全部勾选为完成。

RC2 的唯一核心目标：

```text
使用正式 CLI 和真实文字 PDF
→ 生成真实 claims
→ 持久化完整来源、章节、运行、主张和定位
→ 生成人工复核批次
→ 严格应用审核决定
→ approved 可检索，rejected 不可检索
→ 导出包含来源和页码
→ 删除数据库
→ 从资料包恢复完全相同的业务状态
→ verify 对以上过程执行真实检查
```

---

# 1. OpenCode 与 DeepSeek-V4-Pro 执行环境

## 1.1 OpenCode 版本

执行前运行：

```bash
opencode --version
```

要求：

```text
OpenCode >= 1.14.24
```

版本不足时先升级，不得继续执行业务修改。

## 1.2 Provider 配置

在 OpenCode 中执行：

```text
/connect
```

然后：

1. 搜索并选择 `deepseek`。
2. 输入 DeepSeek API Key。
3. 选择 `DeepSeek-V4-Pro`。
4. 确认当前会话模型显示为 DeepSeek-V4-Pro。

API Key 只能写入 OpenCode 的凭据存储或环境变量，禁止写入：

- `opencode.json`
- `AGENTS.md`
- `.env.example`
- Git commit
- 日志
- 测试 fixture

## 1.3 项目初始化

进入仓库根目录：

```bash
cd /path/to/literature-evidence-agent
opencode
```

如果根目录已有 `AGENTS.md`：

- 先读取。
- 只增补当前计划需要的规则。
- 不得覆盖已有有效说明。

如果没有：

```text
/init
```

OpenCode 会扫描项目并建立 `AGENTS.md`。

## 1.4 推荐 `opencode.json`

如项目没有 `opencode.json`，允许创建：

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": [
    "AGENTS.md",
    "plan/ROUND1_1_RC2_OPENCODE_DEEPSEEK_V4_PRO_CODING_PLAN.md",
    "docs/reviews/round1/10_final_review_report.md",
    "docs/ROUND1_1_COMPLETION_REPORT.md"
  ],
  "autoupdate": "notify",
  "snapshot": true
}
```

不要在项目配置中硬编码 API Key。

## 1.5 必须写入 `AGENTS.md` 的执行规则

确保根目录 `AGENTS.md` 包含以下语义：

```text
1. 以本计划文件为 Round 1.1 RC2 唯一执行依据。
2. 每个任务必须先写失败测试，再修改实现，再运行任务级验收。
3. 禁止硬编码 PASS，禁止使用 >= 0 等永真断言。
4. 禁止用 Mock 测试声称真实 DeepSeek API 已验证。
5. 禁止扩大到在线检索、OCR、向量数据库、多 Agent 和 Web 前端。
6. 外部资料始终保持 origin_scope=external。
7. 人工批准只表示记录忠实，不表示科学验证。
8. 每完成一个任务，更新执行日志并检查 git diff。
9. 每个 Batch 完成后执行独立 Gate Review。
10. 任一 Hard Gate 失败，最终结论必须为 FAIL。
```

---

# 2. DeepSeek-V4-Pro 执行提示

DeepSeek-V4-Pro 在本项目中的职责：

- 阅读现有代码和 Review 证据。
- 自主完成实现选择。
- 使用工具执行命令和测试。
- 不等待用户逐步确认。
- 遇到局部设计选择时采用最简单、可测试、可审计的方案。
- 所有假设写入执行日志。
- 不把未运行的命令写成已验证。

OpenCode 首次执行时，向模型发送：

```text
读取并严格执行：
@AGENTS.md
@plan/ROUND1_1_RC2_OPENCODE_DEEPSEEK_V4_PRO_CODING_PLAN.md
@docs/reviews/round1/10_final_review_report.md
@docs/ROUND1_1_COMPLETION_REPORT.md

当前基线必须是 commit a93c353800fce4e4680f29e2538ea612f0f66b07。

从 PREP 00 开始。
按 Batch 顺序持续执行。
每个任务先建立失败测试，确认测试在旧代码上失败，再修复实现。
完成一个任务后运行任务级验收、更新执行日志、检查 git diff，并创建一个独立 commit。
不得跳过 Gate Review。
不得用空数据、表存在、COUNT >= 0、固定 Mock 返回或硬编码输出代替真实验收。
```

---

# 3. 范围控制

## 3.1 本轮必须完成

- 清理重复和误导性 CLI。
- 持久化 `source_sections`。
- 正确使用 task 的 `analysis_depth`。
- 校验 task、provider 和 source。
- 完整记录 processing run 元数据。
- 将实际 DB ID 回写资料包。
- 资料包按 run 保存，不覆盖历史。
- 新增 review batch 数据模型。
- 对 edited quote 和 locator 全量重新校验。
- 正确实现审核幂等。
- FTS 查询、更新和重建完整测试。
- 从资料包恢复完整业务状态。
- 重写 verify 为真实隔离验收。
- 重写 E2E 为强断言。
- 建立中英文 Golden Set。
- 修正执行日志和完成报告。
- 增加 GitHub Actions 基础 CI。

## 3.2 本轮禁止开发

- 在线论文检索。
- Crossref/OpenAlex/EPO。
- OCR。
- 扫描版 PDF 支持。
- 向量数据库。
- 图数据库。
- 多 Agent。
- Web UI。
- 曲线数字化。
- 表格数据全量抽取。
- 外部数值仓库。
- 自动机理判断。
- 自动实验建议。
- 用户账户和权限系统。

发现相关需求时只写入 `docs/roadmap.md`。

---

# 4. 最终 Definition of Done

## 4.1 Hard Gate

以下 12 项必须全部通过：

1. DeepSeek 响应解析路径可产生 claims；有 Key 时真实 API smoke 通过。
2. 正式 `analyse` 入口可运行。
3. tasks、sections、runs、claims、locators 可完整持久化。
4. review export 按 run 读取真实 pending claims。
5. edited quote 和 locator 会重新校验，无法绕过。
6. approved/rejected 与 FTS 状态严格同步。
7. 从资料包可恢复完整业务状态和原始 ID。
8. `verify round1` 的每个 PASS 来自真实行为验证。
9. E2E 使用真实文字 PDF 和强断言。
10. Golden Set 有中英文和实际指标。
11. 外部数据隔离保持为 0 污染。
12. README、执行日志和完成报告与实际状态一致。

## 4.2 发布结论

### PASS

满足：

- 12/12 Hard Gate 通过。
- 真实 DeepSeek API smoke 通过。
- 全部自动测试通过。
- Golden Set 达到阈值。
- CI 通过。

### CONDITIONAL PASS

仅允许以下情况：

- 11 个内部 Hard Gate 全部通过。
- 真实 DeepSeek API 因缺少 Key 或外部网络不可用而标记 `blocked_external`。
- HTTP 模拟测试已覆盖完整 DeepSeek 请求和响应解析。
- 文档明确写出真实 API 未验证。

### FAIL

满足任一情况：

- 内部 Hard Gate 失败。
- verify 存在形式化 PASS。
- rebuild 无法恢复原始 ID 或审核状态。
- Golden Set 没有真实标注。
- 执行日志虚报完成。

---

# 5. 目标架构

```text
CLI
└── application services
    ├── task_service
    ├── analyse_service
    ├── review_service
    ├── search_service
    ├── package_snapshot_service
    ├── rebuild_service
    └── verification_service

analyse_service
├── validate task/source/provider
├── parse or load parse result
├── persist sections
├── create processing run
├── extract claims
├── deterministic validation
├── allocate stable IDs
├── stage package snapshot
├── persist DB records transactionally
├── finalize package snapshot
└── update task/run status

review_service
├── create review batch
├── export packet
├── prevalidate decisions
├── revalidate edits
├── transactionally apply decisions
├── sync FTS
├── snapshot review records
└── update batch/task status

rebuild_service
├── validate manifests and hashes
├── create fresh database
├── restore in dependency order
├── rebuild FTS
├── run integrity checks
└── compare restored state
```

---

# 6. 新资料包结构

新写入使用按 run 和 batch 分目录的结构：

```text
workspace/external_evidence/sources/SRC-.../
├── manifest.json
├── original/
│   └── main.pdf
├── parsed/
│   ├── pages.jsonl
│   ├── sections.jsonl
│   ├── document.md
│   └── parse_report.json
├── analysis/
│   └── runs/
│       └── RUN-.../
│           ├── run.json
│           ├── claims.raw.jsonl
│           ├── claims.validated.jsonl
│           ├── claims.persisted.jsonl
│           └── unresolved_items.jsonl
├── review/
│   └── batches/
│       └── RVB-.../
│           ├── batch.json
│           ├── rows.jsonl
│           ├── decisions.jsonl
│           └── revisions.jsonl
└── provenance/
    ├── source.json
    ├── assets.jsonl
    ├── research_tasks.jsonl
    ├── processing_runs.jsonl
    ├── entities.jsonl
    └── claim_entity_links.jsonl
```

兼容策略：

- 新代码优先读取新结构。
- rebuild 可读取旧的 `analysis/claims.persisted.jsonl`。
- 旧结构只做迁移兼容，不继续写入。
- manifest 增加 `schema_version`。
- 所有 JSONL 使用稳定 ID。
- 所有 snapshot 文件使用原子写入。

---

# 7. 数据库迁移目标

新增：

```text
migrations/004_review_batches.sql
migrations/005_run_and_snapshot_metadata.sql
```

## 7.1 Review batch

```sql
CREATE TABLE review_batches (
    review_batch_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    packet_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'exported',
            'partially_applied',
            'applied',
            'invalid'
        )
    ),
    exported_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (run_id)
        REFERENCES processing_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (source_id)
        REFERENCES sources(source_id) ON DELETE CASCADE,
    UNIQUE (run_id, packet_sha256)
);

CREATE TABLE review_batch_rows (
    review_row_id TEXT PRIMARY KEY,
    review_batch_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    row_sequence INTEGER NOT NULL,
    row_input_sha256 TEXT NOT NULL,
    applied_at TEXT,
    FOREIGN KEY (review_batch_id)
        REFERENCES review_batches(review_batch_id) ON DELETE CASCADE,
    FOREIGN KEY (claim_id)
        REFERENCES source_claims(claim_id) ON DELETE CASCADE,
    UNIQUE (review_batch_id, claim_id),
    UNIQUE (review_batch_id, row_sequence)
);
```

为 `review_decisions` 增加：

```text
review_batch_id
review_row_id
```

并建立：

```text
UNIQUE(review_batch_id, review_row_id)
```

## 7.2 Processing run 元数据

确保可保存：

```text
model_mode
parser_name
parser_version
code_commit
input_hash
output_hash
artifact_schema_version
warning_json
```

可以通过新增列实现。

## 7.3 数据约束

- `source_claims.created_by_run_id` 应增加到 `processing_runs` 的外键。
- approved 或 approved_with_edits 的 claim 必须有 locator；SQLite 难以直接跨表 CHECK，可通过 service 和 verification 保证。
- review decision 必须关联 batch row。
- 原有记录兼容迁移，不删除数据。

---

# 8. 执行日志

创建：

```text
docs/plans/ROUND1_1_RC2_EXECUTION_LOG.md
```

每个任务记录：

```markdown
## TASK ID

- Status:
- Started at:
- Completed at:
- Baseline commit:
- Result commit:
- Files changed:
- Tests added:
- Commands run:
- Exit codes:
- Expected pre-fix failure:
- Post-fix result:
- Known limitations:
- Follow-up:
```

允许状态：

```text
not_started
in_progress
verified
blocked_external
failed
```

禁止使用模糊的 `done` 或无证据的 `completed`。

---

# 9. 执行任务

---

## PREP 00：冻结基线

### 目标

确认执行从指定 commit 开始，建立独立修复分支。

### 命令

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline
```

必须确认：

```text
HEAD = a93c353800fce4e4680f29e2538ea612f0f66b07
```

创建分支：

```bash
git checkout -b fix/round1.1-rc2-hardening
```

### 基线测试

```bash
python3.11 -m venv .venv-rc2
source .venv-rc2/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

ruff check .
python -m mypy src
pytest -q
```

### 产物

- 执行日志。
- 基线测试输出。
- 当前文件清单。
- 当前测试数量。

### 验收

- [ ] HEAD 正确。
- [ ] 工作区无未记录业务修改。
- [ ] 新分支创建。
- [ ] 基线命令和退出码已记录。
- [ ] 基线失败没有被隐藏。

---

## PREP 01：建立失败复现测试

### 目标

在改代码前，把当前已知缺陷转成自动测试。

### 新增测试

```text
tests/regression/test_verify_real_checks.py
tests/regression/test_rebuild_identity.py
tests/regression/test_review_edit_revalidation.py
tests/regression/test_execution_log_contract.py
tests/integration/test_sections_persistence.py
tests/integration/test_review_batches.py
tests/integration/test_rebuild_complete_state.py
```

### 必须先失败的测试

1. 空数据库执行 verify 不得 PASS。
2. `source_claims` 为 0 时 quote traceability 不得 PASS。
3. 空 `review_decisions` 时 review workflow 不得 PASS。
4. FTS 只有表但没有 approved claim 时不得 PASS。
5. migration version 足够但未执行 rebuild 时不得 PASS。
6. rebuild 后 claim ID 必须与原库一致。
7. rebuild 后 approved/rejected 状态必须一致。
8. rebuild 后 review decision 数量必须一致。
9. `source_sections` 为空时 edited quote 必须被拒绝。
10. 无效 edited page 必须被拒绝。
11. E2E 搜索结果必须大于 0。
12. Golden evaluator 遇到 negative example 被提取必须扣分。

### 验收

```bash
pytest tests/regression -q
```

要求：

- 测试因预期缺陷失败。
- 失败原因与测试目标一致。
- 执行日志记录失败摘要。
- 不允许使用 `xfail` 掩盖。

提交：

```text
test(rc2): capture remaining round1.1 hard-gate failures
```

---

# Batch A：数据与分析完整性

## FIX A01：清理 CLI 和 provider 选择

### 当前问题

- `db reset` 和旧 `db rebuild` 同时存在。
- `db rebuild` 函数有重复不可达代码。
- `_get_provider()` 对未知名字静默返回 Mock。
- CLI 默认 Mock 容易让用户误以为在使用真实模型。

### 修改

1. 保留：
   ```text
   db reset
   db rebuild-from-packages
   ```
2. 删除旧 destructive `db rebuild`，或保留为明确 deprecated alias，调用时退出并提示使用 `db reset`。
3. provider 只允许：
   ```text
   mock
   deepseek
   ```
4. 未知 provider 返回 CLI code 2。
5. CLI provider 默认值来自配置。
6. 生产默认建议：
   - 有 API Key：deepseek。
   - 无 API Key：要求显式 `--provider mock`，禁止隐式模拟。
7. `MockProvider` 在输出 claim 前检查 quote 是否存在于当前 section，只返回当前块真实包含的 fixture claim。

### 测试

- unknown provider。
- 未配置 Key 且未显式 mock。
- mock 不对无关 PDF 返回姜黄素 claims。
- CLI help 不再显示误导性 rebuild。

### 验收

```bash
pytest tests/unit/test_provider.py -q
pytest tests/integration/test_cli_provider_selection.py -q
evidence-agent db --help
evidence-agent analyse --help
```

提交：

```text
fix(cli): remove ambiguous rebuild and require explicit provider behavior
```

---

## FIX A02：硬化 ID

### 当前问题

当前 ID 只有 8 位十六进制随机部分，长期积累时碰撞风险不必要地偏高。

### 修改

使用完整 UUID4 hex：

```text
SRC-<32 hex>
TASK-<32 hex>
RUN-<32 hex>
CLM-<32 hex>
LOC-<32 hex>
SEC-<32 hex>
RVB-<32 hex>
RVR-<32 hex>
REV-<32 hex>
RVN-<32 hex>
ENT-<32 hex>
```

要求：

- 旧短 ID 仍然可以读取。
- 只改变新 ID 生成。
- 新增 review batch 和 row ID generator。
- 测试中允许注入 deterministic ID factory。

### 测试

- 生成 100000 个 ID 无重复。
- 前缀正确。
- 旧 ID 不被 schema 拒绝。
- deterministic factory 可用。

### 验收

```bash
pytest tests/unit/test_ids.py -q
```

提交：

```text
fix(ids): use full UUID identifiers and injectable factories
```

---

## FIX A03：任务和 analyse 输入校验

### 当前问题

- task 不存在时 analyse 仍可继续。
- task 的 `analysis_depth` 被硬编码为 `source_complete`。
- task status 没有正确推进。
- provider 错误可能被吞成空 claims。
- 所有 block 失败时 run 仍可能完成。

### 修改

analyse 开始前校验：

- source 存在。
- source asset 存在。
- task 存在，若提供。
- task mode 与 analyse 兼容。
- provider 合法。
- parse result 可用。

读取 task：

```text
user_request → task_description
analysis_depth → extraction analysis_depth
```

状态推进：

```text
task.created → running
task.running → review
task.running → failed
```

运行规则：

- `blocks_processed == 0`：fail `NO_ANALYZABLE_TEXT`。
- `blocks_failed == blocks_processed`：fail `PROVIDER_ALL_BLOCKS_FAILED`。
- 部分 block 失败：run completed，写 warning_json。
- source_complete 得到 0 validated claims：允许完成，但输出明确 warning。
- 验收 fixture 必须得到非零 claim。

### 测试

- 不存在 task。
- 不存在 source。
- 非法 provider。
- task_focused 真正传给 extraction。
- source_complete 真正传给 extraction。
- 所有 block 失败。
- 部分 block 失败。
- task 状态变化。

### 验收

```bash
pytest tests/integration/test_analyse_validation.py -q
```

提交：

```text
fix(analyse): validate inputs and honor task depth and lifecycle
```

---

## FIX A04：持久化 source sections

### 当前问题

parse 结果只写入文件，没有写入 `source_sections`。这会导致 review edit 无法可靠验证来源文本。

### 修改

实现：

```text
persist_source_sections(source_id, sections, parser metadata)
```

每次 parse/analyse：

1. 为 section 分配稳定 section ID。
2. 保存：
   - section_type
   - heading
   - page_start
   - page_end
   - sequence_number
   - text
   - parser_name
   - parser_version
   - text_sha256
3. 同一 source 和相同 parse hash 重跑时幂等。
4. parser 或文本变化时：
   - 在事务中替换旧 sections。
   - 重新验证未审核 claims。
   - 已审核 claims 不自动修改，只标记需复核或阻止无提示覆盖。
5. locator 写入真实 section_id。

稳定 section ID 建议基于：

```text
source_id + sequence_number + text_sha256
```

或生成后回写 `sections.jsonl`，重建时保持原 ID。

### 测试

- sections 写入非零。
- 重跑不重复。
- locator.section_id 非空。
- section 属于正确 source。
- review edit 可从 DB 读取文本。
- parse 更新行为受控。

### 验收

```bash
pytest tests/integration/test_sections_persistence.py -q
```

提交：

```text
feat(storage): persist parsed sections and bind locators
```

---

## FIX A05：完整 processing run 元数据

### 当前问题

- input_hash 当前为 `"pending"`。
- output_hash 未填。
- parser 和 code commit 缺失。
- provenance 文件可能覆盖历史。

### 修改

run 创建前计算：

```text
input_hash = SHA256(
  source file hash
  + task payload
  + provider/model
  + prompt version/hash
  + parser version
  + analysis depth
)
```

run 完成后计算：

```text
output_hash = SHA256(
  persisted claim canonical JSON
  + locator canonical JSON
  + unresolved canonical JSON
)
```

保存：

- model_name
- model_mode
- prompt_version
- prompt file hash
- parser_name
- parser_version
- code_commit
- input_hash
- output_hash
- warnings
- started_at
- completed_at

`processing_runs.jsonl` 必须 append 或按 run 独立保存，不覆盖历史。

### 测试

- input_hash 非 pending。
- 同一输入 hash 稳定。
- prompt 变化导致 hash 变化。
- output_hash 非空。
- code commit 可读取。
- 无 Git 环境时明确记录 `unknown`。

### 验收

```bash
pytest tests/integration/test_processing_run_metadata.py -q
```

提交：

```text
feat(provenance): record deterministic run input and output metadata
```

---

## FIX A06：持久化记录先分配 ID，再写 DB 和资料包

### 当前问题

数据库生成的 claim ID 和 locator ID 没有回写 `claims.persisted.jsonl`。

### 修改

将流程改为：

```text
validated claims
→ allocate persisted records with IDs
→ stage snapshot
→ DB transaction
→ finalize snapshot
```

`_persist_claims` 不再只返回 count，改为返回：

```python
list[PersistedClaimRecord]
```

每条 persisted record 必须包含：

- claim_id
- locator_id
- section_id
- source_id
- task_id
- run_id
- 完整 claim 字段
- 完整 locator 字段
- review status
- scientific status
- created_at
- updated_at
- schema_version

`claims.persisted.jsonl` 必须保存这些真实记录。

### 原子写入

实现通用：

```python
atomic_write_text(path, content)
atomic_write_json(path, data)
atomic_write_jsonl(path, records)
```

机制：

1. 同目录写 `.tmp`。
2. flush。
3. `os.fsync`。
4. `os.replace`。

按 run 写入：

```text
analysis/runs/RUN-ID/
```

禁止覆盖其他 run。

### 失败处理

- stage 文件失败：不写 DB。
- DB 事务失败：删除 stage。
- finalize rename 失败：保留 stage，run 标记 artifact sync failure，并输出修复指令。
- 不允许静默成功。

### 测试

- persisted 文件含真实 claim ID。
- DB 与文件 ID 完全一致。
- locator ID 一致。
- 多次 analyse 保留多个 run。
- 模拟文件写失败。
- 模拟 DB 失败。
- 原子写无半文件。

### 验收

```bash
pytest tests/integration/test_claim_persistence.py -q
pytest tests/integration/test_atomic_snapshots.py -q
```

提交：

```text
fix(snapshot): persist canonical IDs and atomically store run artifacts
```

---

## Gate A

### 必须执行

```bash
ruff check .
python -m mypy src
pytest tests/unit tests/integration/test_analyse_validation.py \
  tests/integration/test_sections_persistence.py \
  tests/integration/test_processing_run_metadata.py \
  tests/integration/test_claim_persistence.py \
  tests/integration/test_atomic_snapshots.py -q
```

正式 smoke：

```bash
export EVIDENCE_AGENT_WORKSPACE=/tmp/lea-gate-a
rm -rf "$EVIDENCE_AGENT_WORKSPACE"

evidence-agent init
evidence-agent db migrate
evidence-agent task create \
  --title "Gate A" \
  --request "Extract all claims" \
  --mode analyse_uploaded \
  --depth source_complete

evidence-agent ingest tests/fixtures/real_scientific_article_en.pdf
evidence-agent analyse <SRC-ID> --task <TASK-ID> --provider mock
```

数据库检查：

```sql
SELECT COUNT(*) FROM research_tasks;
SELECT COUNT(*) FROM source_sections;
SELECT COUNT(*) FROM processing_runs;
SELECT COUNT(*) FROM source_claims;
SELECT COUNT(*) FROM claim_locators;
```

要求全部大于 0。

Gate A 报告写入：

```text
docs/reviews/round1_rc2/GATE_A_REPORT.md
```

Gate A 未通过时禁止进入 Batch B。

---

# Batch B：人工复核完整性

## FIX B01：Review batch migration 和 repository

### 目标

实现真正的复核批次，而不是只靠 claim_id + decision 去重。

### 修改

新增：

- `review_batches`
- `review_batch_rows`
- 对 `review_decisions` 的 batch 关联
- repository 方法

生成 packet 时：

1. 查询 run 的 pending claims。
2. 构建 canonical rows。
3. 计算 row hash。
4. 计算 packet hash。
5. 创建 review_batch。
6. 创建 rows。
7. 写入 packet。
8. snapshot 到 source package。

如果相同 run 的相同 packet 已存在：

- 返回已有 batch。
- 不创建重复 batch。
- 可重新生成文件。

### 测试

- 非空 batch。
- row count 与 pending count 一致。
- packet hash 稳定。
- 重复 export 幂等。
- claim 变化导致新 batch。

### 验收

```bash
pytest tests/integration/test_review_batches.py -q
```

提交：

```text
feat(review): add review batches and stable packet identities
```

---

## FIX B02：复核包补齐上下文

### 修改

CSV 增加：

- review_batch_id
- review_row_id
- source title
- source path
- section heading
- page
- quote context before
- quote
- quote context after
- figure/table
- model
- prompt version
- run ID
- status
- decision fields

HTML：

- HTML escape 所有来源文本。
- 高亮 quote。
- 显示前后文。
- 显示 PDF 相对路径和页码。
- 显示「外部来源、未经内部验证」。
- 显示 batch ID 和 row ID。

Markdown 同样包含上下文。

### 测试

- HTML script 注入被转义。
- CSV 字段完整。
- 上下文与正确 section/page 对应。
- packet 不包含其他 run 的 claims。

### 验收

```bash
pytest tests/unit/test_review_packet.py -q
pytest tests/integration/test_review_export.py -q
```

提交：

```text
feat(review): export contextual and traceable review packets
```

---

## FIX B03：Review apply 两阶段校验

### 当前问题

现有实现边循环边写入，错误只 append 后 continue；这可能产生部分应用。

### 新流程

```text
read CSV
→ validate batch
→ validate every nonblank row
→ build application plan
→ if any fatal error: write nothing
→ transactionally apply all valid rows
→ sync FTS
→ snapshot decisions
```

### 输入规则

- 空 decision：视为未审核，允许跳过。
- 非空 decision 非法：整批失败。
- claim 不存在：整批失败。
- row 不属于 batch：整批失败。
- row hash 不匹配：整批失败。
- 已应用同一 row：标记 `already_applied`，不重复写。
- 不同 batch 可再次审核同一 claim。

### 编辑校验

`approve_with_edits` 必须验证：

- edited_source_quote 非空。
- quote 在 source_sections 中 exact 或 normalised。
- edited_page 存在。
- quote 位于 edited_page。
- edited_section 属于 source。
- quote 位于 edited_section。
- figure/table 标签存在于相关上下文。
- edited_claim_type 合法。
- paraphrase 非空。
- evidence basis 非空。
- origin_scope 仍 external。
- scientific status 仍 unverified。

如果 `source_sections` 为空：

```text
FAIL: SOURCE_TEXT_UNAVAILABLE
```

禁止跳过校验。

### 决策状态

- approve → approved
- approve_with_edits → approved_with_edits
- reject → rejected
- needs_followup → pending，并记录 decision
- mark_missing → batch issue，不改变 claim 为 approved

### 测试

- edited quote 不存在。
- sections 为空。
- edited page 错误。
- section 不属于 source。
- figure 不存在。
- 一行错误整批回滚。
- 同一 batch row 重复应用。
- 新 batch 再次审核合法。
- revision 内容完整。

### 验收

```bash
pytest tests/integration/test_review_apply.py -q
pytest tests/regression/test_review_edit_revalidation.py -q
```

提交：

```text
fix(review): prevalidate entire batches and recheck all edited provenance
```

---

## FIX B04：FTS 状态同步与安全查询

### 修改

明确三个服务：

```text
index_claim
remove_claim
rebuild_fts
```

规则：

- approved → index
- approved_with_edits → replace
- rejected → remove
- pending → 不索引
- needs_followup → 不索引

查询输入：

- 默认将普通用户输入转换为安全 token/phrase query。
- 捕获 SQLite FTS syntax error 并返回明确用户错误。
- 不允许异常变成空结果。
- 提供内部 `raw_fts=False` 默认值；第一版 CLI 不开放 raw 查询。

查询结果增加：

- source path
- page
- section
- review status
- scientific status
- origin scope

### 测试

- approved 可搜索。
- rejected 不可搜索。
- edited 后旧文本不可搜索，新文本可搜索。
- pending 不可搜索。
- invalid special characters。
- rebuild 前后结果一致。

### 验收

```bash
pytest tests/integration/test_fts.py -q
```

提交：

```text
fix(search): make FTS lifecycle explicit and query-safe
```

---

## FIX B05：Task 完成状态

审核后计算 task 状态：

- 任一 claim pending 或 needs_followup → review
- 所有 claims 有最终决定 → completed
- 分析失败 → failed

测试跨多个 claims 和多个 source 的 task。

提交：

```text
feat(tasks): derive task lifecycle from analysis and review state
```

---

## Gate B

执行完整流程：

```bash
export EVIDENCE_AGENT_WORKSPACE=/tmp/lea-gate-b
rm -rf "$EVIDENCE_AGENT_WORKSPACE"

evidence-agent init
evidence-agent db migrate
# create task, ingest, analyse
evidence-agent review export <RUN-ID>
# 填写一条 approve，一条 approve_with_edits，一条 reject
evidence-agent review apply <CSV>
evidence-agent query "curcumin"
```

验证：

- packet 非空。
- batch 和 rows 入库。
- edited quote 真实匹配。
- approved 可搜索。
- rejected 不可搜索。
- 重复 apply 不增加 decisions。
- task 状态正确。

报告：

```text
docs/reviews/round1_rc2/GATE_B_REPORT.md
```

---

# Batch C：完整资料包和数据库恢复

## FIX C01：资料包快照完整性

### 目标

资料包必须包含重建所有核心业务数据所需的信息。

保存：

- source
- assets
- research tasks
- sections
- processing runs
- claims
- locators
- entities
- links
- review batches
- review rows
- review decisions
- revisions

每条记录包含：

```text
schema_version
record_type
record_id
source_id
updated_at
```

manifest 保存：

- schema_version
- package ID
- source hash
- artifact 相对路径
- artifact SHA-256
- record counts
- last synchronized DB commit/time

新增：

```bash
evidence-agent package check SRC-ID
evidence-agent package sync SRC-ID
```

`package check` 验证：

- 文件存在。
- hash 正确。
- record counts 正确。
- ID 引用完整。
- 无临时未完成 snapshot。

### 测试

- 正常 package。
- 缺文件。
- hash 篡改。
- count 不一致。
- dangling claim locator。
- dangling review row。

### 验收

```bash
pytest tests/integration/test_package_integrity.py -q
```

提交：

```text
feat(package): snapshot complete rebuildable source state
```

---

## FIX C02：重写 rebuild service

### 当前问题

当前实现：

- 通过环境变量和 reload 切换数据库。
- 不能保持真实 ID。
- 强制恢复为 pending。
- 未恢复 decisions/revisions/entities。
- created_by_run_id 写入了 page 值。
- 会直接删除目标数据库。

### 新实现要求

1. 不修改全局环境变量。
2. 所有 repository 和 migration 支持显式 `db_path` 或 connection。
3. 默认拒绝覆盖已存在目标数据库。
4. `--replace` 才允许覆盖，并先备份。
5. 验证全部 manifests 和 hashes 后再开始导入。
6. 任一 package fatal error：
   - 默认整体失败。
   - 不返回成功。
7. 依赖顺序：

```text
research_tasks
→ sources
→ assets
→ sections
→ processing_runs
→ claims
→ locators
→ entities
→ claim_entity_links
→ review_batches
→ review_batch_rows
→ review_decisions
→ claim_revisions
→ FTS
```

8. 保持原始：
   - task_id
   - source_id
   - section_id
   - run_id
   - claim_id
   - locator_id
   - entity_id
   - batch_id
   - row_id
   - review_id
   - revision_id
   - review status
   - scientific status
   - created_by_run_id
9. 完成后运行：
   - integrity_check
   - foreign_key_check
   - package-to-DB count comparison
   - FTS comparison

### Rebuild report

```json
{
  "status": "pass",
  "target_db": "...",
  "packages_checked": 2,
  "records_expected": {},
  "records_restored": {},
  "id_set_comparison": {},
  "review_status_comparison": {},
  "fts_comparison": {},
  "errors": []
}
```

### 测试

- 单 source。
- 多 source。
- 同 task 多 source。
- approved/rejected/edit history。
- exact ID 集合。
- target exists。
- malformed package。
- hash mismatch。
- missing run。
- dangling FK。
- no global config mutation。

### 验收

```bash
pytest tests/integration/test_rebuild_complete_state.py -q
pytest tests/regression/test_rebuild_identity.py -q
```

提交：

```text
fix(rebuild): restore exact IDs reviews revisions and searchable state
```

---

## FIX C03：恢复状态对比工具

新增：

```bash
evidence-agent db snapshot-summary --database <path>
evidence-agent db compare <db-a> <db-b>
```

比较：

- table counts
- ID sets
- claim canonical content hashes
- locator hashes
- review status distribution
- decision hashes
- revision hashes
- FTS query fixtures

返回：

- 相同：exit 0
- 不同：exit 7

提交：

```text
feat(database): add deterministic state snapshot and comparison
```

---

## Gate C

1. 在临时 workspace 完成分析和审核。
2. 保存原 DB summary。
3. 删除或移走原 DB。
4. 从资料包重建到新路径。
5. 对比。

命令：

```bash
evidence-agent db snapshot-summary --database <original>
evidence-agent db rebuild-from-packages \
  --source <sources-dir> \
  --target <rebuilt-db>
evidence-agent db compare <original> <rebuilt-db>
```

要求：

- 所有核心 ID 集合一致。
- review status 一致。
- decisions/revisions 一致。
- FTS 关键查询一致。
- foreign key check 为空。

报告：

```text
docs/reviews/round1_rc2/GATE_C_REPORT.md
```

---

# Batch D：真实 Verify、E2E 和 Golden Set

## FIX D01：重写 verification service

### 原则

`verify` 必须在独立临时 workspace 中主动执行行为，不依赖用户当前数据库中恰好存在的数据。

新增：

```text
src/evidence_agent/verification/round1.py
```

CLI 只负责调用。

### 检查 1：database_integrity

- 创建临时 DB。
- 运行 migrations。
- integrity_check。
- foreign_key_check。
- 检查最新 migration。

### 检查 2：ingest_idempotency

- 导入同一真实 PDF 两次。
- source ID 相同。
- source count 仍为 1。
- asset count 不重复。

### 检查 3：quote_traceability

- analyse fixture。
- claim 数大于 0。
- 每条 accepted candidate quote 可在对应 page/section 找到。
- locator 非空。
- 不能使用 `COUNT >= 0`。

### 检查 4：review_workflow

- export packet。
- packet rows 大于 0。
- 应用 approve/edit/reject。
- decisions 和 revisions 数量符合预期。
- invalid edit 会失败。
- 重复 batch apply 幂等。

### 检查 5：fts_search

- approved 搜索结果大于 0。
- rejected 搜索结果为 0。
- edited old quote 为 0。
- edited new quote 大于 0。

### 检查 6：database_rebuild

- 执行真实 rebuild。
- 使用 DB compare。
- 核心状态完全一致。

### 检查 7：external_data_isolation

- 所有 sources 和 claims origin_scope 为 external。
- scientific verification 全部 unverified。
- schema 不存在内部 measurement 表。
- 代码中无向内部数据库写入的配置路径。

### 输出

每项：

```text
name=PASS duration_ms=... evidence=...
```

失败：

```text
name=FAIL reason=... evidence=...
```

总结果：

```text
ROUND1_VERIFICATION=PASS
```

仅在全部通过时 exit 0，否则 exit 7。

### 破坏性测试

自动测试中人为破坏：

- locator。
- review decision。
- FTS。
- manifest hash。
- origin_scope。

verify 对应检查必须失败。

### 验收

```bash
pytest tests/integration/test_verify_round1.py -q
pytest tests/regression/test_verify_real_checks.py -q
evidence-agent verify --round-name round1
```

提交：

```text
fix(verify): execute isolated behavioral hard-gate checks
```

---

## FIX D02：重写 CLI E2E

### 原则

使用 Typer `CliRunner` 或 subprocess，只通过公开 CLI。

E2E：

```text
init
→ db migrate
→ task create
→ ingest
→ analyse
→ run-show
→ review export
→ review apply
→ query
→ source-show
→ claim-show
→ export-source
→ package check
→ rebuild-from-packages
→ db compare
→ verify
```

### 强断言

- source count == 1
- section count > 0
- run count == 1
- claim count >= 3
- locator count == claim count
- packet rows == pending claims
- approved >= 1
- edited >= 1
- rejected >= 1
- query approved > 0
- query rejected == 0
- export 含 approved quote、page 和 source ID
- export 不含 rejected quote
- rebuilt ID sets 完全一致
- verify exit 0

禁止：

```python
assert len(results) >= 0
assert count >= 0
assert isinstance(result, list)
仅检查文件存在
```

### 测试 fixture

英文 PDF 至少含：

- reported result
- interpretation + suggests
- limitation + may
- future work
- figure/table

中文 PDF 至少含：

- 结果
- 作者解释
- 局限
- 后续工作

### 验收

```bash
pytest tests/e2e/test_cli_round1_rc2.py -q
```

提交：

```text
test(e2e): verify the full public CLI and rebuild lifecycle
```

---

## FIX D03：Golden Set 扩充

### 最低规模

至少：

- 2 份英文自制 PDF。
- 2 份中文自制 PDF。
- 24 条 must_extract。
- 8 条 must_not_extract。
- 总计至少 32 条。

覆盖：

- background
- method
- reported observation
- reported result
- interpretation
- conclusion
- hypothesis
- limitation
- future work
- hedging
- scope
- 重复 quote
- 错 page
- 错 figure/table
- 原文不存在
- 相关性写成因果的负例
- 推测写成事实的负例

### Annotation schema

```json
{
  "annotation_id": "GOLD-...",
  "source_file": "...",
  "language": "en",
  "claim_type": "author_interpretation",
  "source_quote": "...",
  "faithful_paraphrase": "...",
  "evidence_basis_description": "...",
  "scope_description": "...",
  "author_hedging": "suggests",
  "page": 1,
  "section": "Results",
  "figure_label": "Figure 1",
  "must_extract": true,
  "reason": "..."
}
```

### Evaluator 修复

当前 evaluator 的问题必须修复：

1. 默认 glob 字符串没有展开。
2. negative example 被当作「已支持 quote」。
3. claim type accuracy 未计算。
4. hedging preservation 未计算。
5. scope preservation 未计算。
6. 没有区分 pending 与 approved。
7. 没有输出逐样本结果。

实现：

- glob expansion。
- positive 和 negative 分开匹配。
- 提取 negative → false positive。
- 自动计算：
  - claim recall
  - false positive rate
  - unsupported accepted claim rate
  - quote match rate
  - locator completeness
  - claim type accuracy
  - hedging preservation
  - scope preservation
- 输出 JSON 和 Markdown 报告。
- 每个失败样本有原因。

### 阈值

```text
unsupported accepted claim rate = 0%
negative extraction rate = 0%
approved quote match rate = 100%
approved locator completeness = 100%
claim recall >= 80%
claim type accuracy >= 85%
hedging preservation >= 95%
scope preservation >= 90%
```

### 验收

```bash
python scripts/evaluate_golden.py \
  --golden tests/golden/annotations.jsonl \
  --claims <generated-jsonl> \
  --json-output artifacts/golden_metrics.json \
  --markdown-output artifacts/golden_report.md
```

提交：

```text
test(golden): add bilingual annotations and automated fidelity metrics
```

---

## FIX D04：真实 DeepSeek API smoke

### 条件

环境变量：

```bash
export EVIDENCE_AGENT_LLM_API_KEY=...
export EVIDENCE_AGENT_LLM_MODEL=deepseek-v4-pro
```

### 测试

使用小型自制 PDF，限制成本。

验证：

- HTTP 请求成功。
- content 可解析。
- 至少一条 claim。
- quote 真实匹配。
- model_name 正确。
- run metadata 正确。
- 不记录 reasoning content。
- 不泄露 Key。

测试标记：

```text
pytest -m live_deepseek
```

普通 CI 不运行。

无 Key 时：

```text
status = blocked_external
```

最终只能 `CONDITIONAL PASS`。

有 Key 且通过：

```text
status = verified
```

提交：

```text
test(deepseek): add opt-in live provider smoke verification
```

---

## Gate D

运行：

```bash
ruff check .
python -m mypy src
pytest -q
python scripts/evaluate_golden.py ...
evidence-agent verify --round-name round1
```

有 API Key：

```bash
pytest -m live_deepseek -q
```

报告：

```text
docs/reviews/round1_rc2/GATE_D_REPORT.md
```

---

# Batch E：CI、文档和最终审计

## FIX E01：GitHub Actions

新增：

```text
.github/workflows/ci.yml
```

触发：

- push
- pull_request

Python：

- 3.11
- 3.12

步骤：

```text
pip install -e .[dev]
ruff check .
python -m mypy src
pytest -q
```

不执行 live DeepSeek。

上传：

- pytest JUnit（如配置）。
- Golden report（可选）。
- verification report（可选）。

确保私人 PDF、workspace、DB 和 Key 不上传。

提交：

```text
ci: run lint type checks tests and offline verification
```

---

## FIX E02：清理执行日志

更新旧：

```text
docs/plans/ROUND1_EXECUTION_LOG.md
```

保留历史，不删除，但增加醒目标记：

```text
Historical Round 1 log — superseded by Review and RC2.
The original completed flags were inaccurate.
```

创建或完成：

```text
docs/plans/ROUND1_1_RC2_EXECUTION_LOG.md
```

每项状态与实际证据一致。

---

## FIX E03：README

README 必须：

- 使用真实命令。
- 明确 `mock` 只用于测试。
- 明确 DeepSeek Key 配置。
- 区分 `db reset` 和 `db rebuild-from-packages`。
- 展示完整流程。
- 说明 review batch。
- 说明 external/unverified。
- 说明当前已知限制。
- 不写固定测试数量，或注明对应 commit。
- 不声称真实 API 已验证，除非 live smoke 通过。

逐条执行 README 命令。

---

## FIX E04：完成报告

创建：

```text
docs/ROUND1_1_RC2_COMPLETION_REPORT.md
```

必须包含：

1. 基线 commit。
2. 目标 commit。
3. 修改文件。
4. 关闭的 Findings。
5. 未关闭的 Findings。
6. 12 个 Hard Gate 表。
7. 全部真实命令和退出码。
8. 单元、集成、E2E 结果。
9. Golden Set 指标。
10. verify 输出。
11. rebuild 前后比较。
12. DeepSeek live smoke 状态。
13. 已知限制。
14. 下一轮建议。
15. 最终结论。

结论严格使用：

```text
PASS
CONDITIONAL PASS
FAIL
```

---

## FIX E05：最终独立 Review

修复完成后，模型必须切换到 Review 模式或新会话，只读审查最终代码。

重新执行原 12 个 Hard Gate。

Review 产物：

```text
docs/reviews/round1_rc2/
├── 00_scope.md
├── 01_clean_environment.md
├── 02_hard_gate_matrix.csv
├── 03_database_rebuild_audit.md
├── 04_review_workflow_audit.md
├── 05_golden_set_report.md
├── 06_findings.csv
└── 07_final_report.md
```

Review Agent 禁止修改业务代码。

发现 P0/P1：

- Final 结论 FAIL。
- 返回对应 Batch 修复。
- 修复后重新独立 Review。

---

# 10. 测试矩阵

| 模块 | 必须测试 | 通过标准 |
|---|---|---|
| IDs | 大量生成、旧格式兼容 | 无碰撞、前缀正确 |
| Provider | mock 相关性、DeepSeek JSON | 不返回无关固定 claim |
| Task | create/show/list/status | 状态真实 |
| Analyse | task/source/provider/深度 | 输入受控 |
| Sections | DB 持久化、幂等 | 非零且稳定 |
| Runs | hashes、commit、错误 | 元数据完整 |
| Claims | ID 回写、事务 | DB/文件一致 |
| Snapshot | atomic write、多个 run | 无覆盖 |
| Review batch | hash、rows、重复 export | 幂等 |
| Review apply | 全量预校验、rollback | 无部分写 |
| Locator | page/section/figure/table | 无绕过 |
| FTS | approve/edit/reject/rebuild | 状态同步 |
| Package | hash、counts、references | 完整 |
| Rebuild | exact IDs/status/history | 完全一致 |
| Verify | 真实行为、破坏性测试 | 破坏后 FAIL |
| E2E | 公共 CLI 完整路径 | 强断言 |
| Golden | 中英文、正负例 | 达阈值 |
| Live API | opt-in | 有 Key 时通过 |
| CI | 3.11/3.12 | 全绿 |

---

# 11. 最终验收脚本

新增：

```text
scripts/verify_round1_rc2.sh
```

脚本必须：

```bash
set -euo pipefail
```

执行：

```bash
python3.11 -m venv .venv-final
source .venv-final/bin/activate
pip install -e ".[dev]"

ruff check .
python -m mypy src
pytest -q

export EVIDENCE_AGENT_WORKSPACE="$(mktemp -d)"
evidence-agent init
evidence-agent db migrate
evidence-agent verify --round-name round1

python scripts/evaluate_golden.py ...
```

如果设置 API Key：

```bash
pytest -m live_deepseek -q
```

生成：

```text
artifacts/round1_rc2/
├── commands.log
├── pytest.log
├── verify.log
├── golden_metrics.json
├── golden_report.md
├── db_compare.json
└── final_summary.json
```

`final_summary.json`：

```json
{
  "result": "PASS",
  "hard_gates": {
    "passed": 12,
    "total": 12
  },
  "live_deepseek": "verified",
  "tests": {
    "ruff": "pass",
    "mypy": "pass",
    "pytest": "pass"
  }
}
```

不得手工填写 PASS；数据必须来自真实命令结果。

---

# 12. Commit 顺序

建议严格使用：

```text
1. test(rc2): capture remaining hard-gate failures
2. fix(cli): remove ambiguous rebuild and harden provider selection
3. fix(ids): use collision-resistant identifiers
4. fix(analyse): validate task source provider and lifecycle
5. feat(storage): persist source sections and bind locators
6. feat(provenance): record complete processing run metadata
7. fix(snapshot): store canonical persisted IDs atomically
8. feat(review): add review batches and contextual packets
9. fix(review): prevalidate edits and apply batches atomically
10. fix(search): synchronize FTS with final review status
11. feat(package): snapshot complete rebuildable source state
12. fix(rebuild): restore exact IDs and audit history
13. feat(database): compare deterministic database snapshots
14. fix(verify): execute behavioral hard-gate checks
15. test(e2e): cover full public CLI lifecycle
16. test(golden): add bilingual fidelity evaluation
17. test(deepseek): add opt-in live API smoke
18. ci: add Python quality and offline verification workflow
19. docs(rc2): update logs README completion and review reports
```

每个 commit 前：

```bash
git diff --check
ruff check .
python -m mypy src
pytest <focused tests> -q
```

每个 Batch 后运行全套：

```bash
pytest -q
```

---

# 13. 失败处理

## 测试失败

- 保留失败输出。
- 不修改测试目标以适配错误实现。
- 定位最小根因。
- 只修改当前 Batch。

## 数据库 migration 失败

- 不编辑已发布 migration。
- 新增 corrective migration。
- 记录升级和空库两条路径。

## DeepSeek API 不可用

- 运行模拟 HTTP 测试。
- 标记 `blocked_external`。
- 不声称 live verified。
- 继续完成内部 Gate。

## 资料包不一致

- rebuild 立即失败。
- 输出具体 package、文件和 hash。
- 不跳过坏 package 后返回 PASS。

## OpenCode 上下文压缩

每个 Batch 完成后，把状态写入执行日志。新会话必须先读取：

```text
AGENTS.md
本计划
RC2 execution log
最近 Gate report
git log
```

不得依赖聊天上下文记忆。

---

# 14. 最终禁止项

DeepSeek 不得：

- 把 `COUNT >= 0` 当验收。
- 只检查表存在。
- 只检查 migration version 代表 rebuild 成功。
- 只检查文件存在，不检查内容。
- 使用空白 PDF。
- 使用固定 Mock 对任意来源返回相同主张。
- 在 source text 缺失时跳过 edit validation。
- 通过 `except Exception: pass` 隐藏错误。
- 覆盖旧 run 的资料包文件。
- 重建时生成新业务 ID。
- 重建时重置审核状态。
- 忽略 review decisions 和 revisions。
- 把 negative annotation 当作支持证据。
- 在没有 live API 结果时写「DeepSeek 已验证」。
- 修改本轮范围以外功能。
- 把 P0/P1 留到下一轮仍声明 PASS。

---

# 15. OpenCode 最终执行指令

将以下内容作为开始执行的最终 prompt：

```text
严格执行：
@AGENTS.md
@plan/ROUND1_1_RC2_OPENCODE_DEEPSEEK_V4_PRO_CODING_PLAN.md

基线必须为：
a93c353800fce4e4680f29e2538ea612f0f66b07

目标分支：
fix/round1.1-rc2-hardening

从 PREP 00 开始，按 Batch A → B → C → D → E 顺序执行。

每个 FIX：
1. 先创建或运行能够复现旧缺陷的失败测试；
2. 确认测试因正确原因失败；
3. 修改实现；
4. 运行 focused tests；
5. 运行 ruff 和 mypy；
6. 更新 RC2 execution log；
7. 检查 git diff；
8. 创建独立 commit。

每个 Gate：
1. 使用新的临时 workspace；
2. 通过公开 CLI 执行；
3. 保存命令、退出码和产物；
4. 生成 Gate report；
5. Gate 未通过时禁止进入下一 Batch。

不要询问局部实现选择，采用最简单、可测试、可审计的方案。
不要开发本计划范围外功能。
不要用表存在、COUNT >= 0、空白 PDF、固定 Mock 或硬编码 PASS 替代验收。

真实 DeepSeek API 无法测试时，标记 blocked_external，最终最多 CONDITIONAL PASS。
所有内部 Hard Gate 和 live API 都通过后，才能写 PASS。
```

---

# 16. 预期最终结果

完成后，仓库应具备：

```text
一篇真实 PDF
→ 正式 task
→ 正式 analyse
→ 持久化 sections/runs/claims/locators
→ 可追溯资料包
→ review batch
→ 严格人工修改校验
→ approved/rejected FTS 隔离
→ 完整导出
→ 删除数据库
→ 从资料包恢复完全相同 ID、状态和历史
→ 独立 verify 真实通过
→ 中英文 Golden Set 达标
→ CI 持续验证
```

最终状态必须以独立 Review 报告为准，而不是 Coding Agent 自己的完成声明。
