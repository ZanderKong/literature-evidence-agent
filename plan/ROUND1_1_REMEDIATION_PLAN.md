# Literature Evidence Agent — Round 1.1 详细修补计划

> 建议文件位置：`docs/plans/ROUND1_1_REMEDIATION_PLAN.md`  
> 适用基线：`round1-failed-baseline` 或 Review 对应 commit  
> 目标分支：`fix/round1.1-remediation`  
> 修补目标：将现有工程骨架修复为真实可用、可审核、可恢复、可验收的最小闭环。  
> 核心验收：一篇真实文字型 PDF 通过正式 CLI，生成至少一条可定位、可审核、可入库、可搜索、可从资料包恢复的作者主张。

---

# 0. 总体规则

修补顺序固定为：

```text
真实分析闭环
→ 人工复核与检索
→ 数据恢复与真实验收
→ 文档和完成状态纠正
```

在前三阶段完成前，不开发在线检索、专利、OCR、向量数据库、图数据库、Web 前端、多 Agent、外部数值仓库或自动实验方案。

每个任务必须：

1. 阅读对应 Finding。
2. 只修改当前任务直接涉及的文件。
3. 添加或更新测试。
4. 运行规定命令。
5. 把真实结果写入执行日志。
6. 验收全部通过后再进入下一任务。

禁止通过删除测试、降低断言、空白 PDF、硬编码 PASS、Mock 假闭环或创建空壳模块完成任务。

---

# 1. Round 1.1 Definition of Done

## 1.1 产品闭环

- [ ] `evidence-agent task create` 可创建任务。
- [ ] `evidence-agent analyse` 可执行完整分析。
- [ ] DeepSeek 响应可解析为候选 claims。
- [ ] Mock Provider 返回与 fixture 原文一致的 claims。
- [ ] `processing_runs` 记录 started、completed 或 failed。
- [ ] `source_claims` 有真实记录。
- [ ] `claim_locators` 有对应定位。
- [ ] `review export RUN-ID` 从数据库读取 pending claims。
- [ ] 审核支持批准、编辑、拒绝、待跟进。
- [ ] 编辑后的 quote、locator、claim_type 重新校验。
- [ ] approved claims 可通过 FTS 搜索。
- [ ] pending 和 rejected 默认不可搜索。
- [ ] 单份资料可导出 Markdown 和 JSONL。
- [ ] 删除数据库后可从资料包恢复关键记录。

## 1.2 验收可信度

- [ ] `verify round1` 不含硬编码 PASS。
- [ ] 人为破坏 Hard Gate 后 verify 返回 FAIL 和退出码 7。
- [ ] E2E 使用有真实科学文本的 PDF。
- [ ] E2E 至少产生一条真实主张。
- [ ] E2E 覆盖 review apply、FTS、export 和 rebuild。
- [ ] Golden Set 存在真实标注。
- [ ] 无依据批准主张率为 0。
- [ ] 批准记录 quote 匹配率为 100%。
- [ ] 批准记录定位完整率为 100%。

## 1.3 工程质量

- [ ] `ruff check .` 通过。
- [ ] `python -m mypy src` 通过。
- [ ] `pytest -q` 通过。
- [ ] 数据库 integrity check 通过。
- [ ] foreign key check 无问题。
- [ ] README 命令真实执行成功。
- [ ] 执行日志与代码状态一致。
- [ ] `ROUND1_1_COMPLETION_REPORT.md` 存在。

---

# 2. 分支与提交

建议：

```bash
git checkout main
git pull
git tag round1-failed-baseline <REVIEW_BASELINE_SHA>
git checkout -b fix/round1.1-remediation
```

每个 FIX 一个 commit，复杂任务最多拆成两个。推荐提交：

```text
fix(provider): parse DeepSeek claims response
feat(workflow): add task and analyse commands
feat(persistence): persist runs claims and locators
fix(review): export real pending claims
fix(review): revalidate edits and add batch idempotency
fix(search): make FTS lifecycle deterministic
feat(rebuild): restore database from packages
test(e2e): use real text PDFs
fix(verify): replace hardcoded passes
test(golden): add annotated evaluation set
docs(round1.1): publish honest completion report
```

---

# 3. 目标工作流

```text
task create
→ ingest PDF
→ parse PDF
→ analyse source
    → processing_run: started
    → load sections
    → call Provider
    → parse claims
    → validate
    → persist claims and locators
    → save analysis files
    → processing_run: completed
→ review export RUN-ID
→ human review
→ review apply
    → revalidate edits
    → persist decisions and revisions
    → update FTS
→ query
→ export source
→ rebuild from packages
→ verify round1
```

---

# 4. 数据模型增量

## 4.1 审核批次

新增 migration：`004_review_batches.sql`

```sql
CREATE TABLE review_batches (
    review_batch_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    packet_sha256 TEXT NOT NULL,
    exported_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('exported', 'partially_applied', 'applied', 'invalid')
    ),
    FOREIGN KEY (run_id) REFERENCES processing_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE,
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
    UNIQUE (review_batch_id, claim_id)
);
```

为 `review_decisions` 增加 `review_batch_id` 和 `review_row_id`，并建立：

```text
UNIQUE(review_batch_id, review_row_id)
```

同一批次同一行只能应用一次；新批次仍可重新审核同一 claim。

## 4.2 稳定 ID

统一由 `ids.py` 生成：

```text
TASK-<ULID>
SRC-<ULID>
RUN-<ULID>
CLM-<ULID>
LOC-<ULID>
RVB-<ULID>
RVR-<ULID>
REV-<ULID>
```

不得使用列表长度生成 ID。测试可注入固定 ID factory。

---

# 5. 修补任务

## FIX 00：修正 Review 基线文档

### 目标

先让审查基线准确，再开始业务修复。

### 修改

1. 新增 F018：DeepSeek 响应未解析为 claims。
2. 新增 F019：FTS 在只读连接中写入并吞掉异常。
3. Hard Gate 1、6 改为明确 FAIL。
4. TASK 06 改为 `partially_verified`。
5. Findings 更新为 P0 10、P1 3、P2 4、P3 2。
6. 将「R00–R15 全部完成」改为「工程 Review 完成，科学内容 Review 待补」。
7. F010 改用 review batch 幂等方案。
8. F017 改为「计划与实际架构缺少映射」。

### 验收

- [ ] 报告与 Findings 数量一致。
- [ ] F018、F019 有代码证据。
- [ ] 不修改业务代码。

---

# 阶段 A：真实分析闭环

## FIX 01：修复 DeepSeek Provider 响应解析

### 对应

F018，Hard Gate 1。

### 文件

```text
src/evidence_agent/extraction/provider.py
src/evidence_agent/extraction/response_parser.py
src/evidence_agent/extraction/prompts/
tests/unit/test_deepseek_response_parser.py
tests/unit/test_provider.py
```

### 执行

1. 新建 `parse_claim_response(raw_response)`。
2. 接受顶层 `{"claims": [...]}`。
3. 校验 claims 为数组，每项为对象。
4. 使用 Pydantic schema 校验每项。
5. 支持移除 Markdown JSON fence。
6. 非法 JSON 只执行一次结构修复。
7. 修复不得改变语义。
8. 修复失败返回 `INVALID_MODEL_JSON`。
9. 保存原始响应。
10. 成功时把解析结果写入 `ExtractionResponse.claims`。
11. 移除思考模式下无意义的 `temperature`。
12. 增加可配置 `reasoning_effort=max`。
13. API 路径、模型名和 Key 均由环境变量覆盖。

### 测试

- 合法空 claims。
- 合法非空 claims。
- 顶层数组。
- claims 非数组。
- Markdown fence。
- 截断 JSON。
- 字段缺失。
- 非法 claim type。
- 空 content。
- 无 API Key。
- 网络错误。
- 模拟 HTTP 返回非空 claims。

### 验收

```bash
pytest tests/unit/test_deepseek_response_parser.py -q
pytest tests/unit/test_provider.py -q
ruff check .
python -m mypy src
```

- [ ] 真实响应路径不再固定空 claims。
- [ ] 非法 JSON 不会当作成功。
- [ ] Provider 失败不会变成零主张成功。

---

## FIX 02：实现研究任务 CLI

### 对应

F002。

### 命令

```bash
evidence-agent task create
evidence-agent task show TASK-ID
evidence-agent task list
```

### 参数

```text
--title
--request
--background
--mode
--depth
```

默认：

```text
mode = analyse_uploaded
depth = task_focused
status = created
```

### 验收

- [ ] 创建后 `research_tasks` 有记录。
- [ ] show 返回完整内容。
- [ ] 非法 mode 和 depth 被拒绝。
- [ ] list 可按 status 过滤。
- [ ] CLI 输出 task_id。

---

## FIX 03：实现统一 analyse 工作流

### 对应

F002、F013，Hard Gate 2。

### 命令

```bash
evidence-agent analyse SRC-ID   --task TASK-ID   --provider mock|deepseek
```

### 建议模块

```text
src/evidence_agent/application/analyse.py
src/evidence_agent/workflow.py
src/evidence_agent/state.py
```

若采用其他结构，必须在架构文档中说明职责映射。

### 工作流

1. 校验 task 和 source。
2. 检查解析结果。
3. 检查低文本密度。
4. 创建 processing_run，状态 started。
5. 读取 sections 和 pages。
6. 调用 Provider。
7. 保存 raw response。
8. 执行确定性校验。
9. 调用持久化层。
10. 保存资料包分析文件。
11. 更新 run 为 completed。
12. 输出 run_id、候选数、通过数、失败数和下一步。
13. 任何错误都更新 run 为 failed，并返回非零退出码。

### 验收

- [ ] 单一命令执行完整分析。
- [ ] run 状态真实。
- [ ] 缺少 parse 结果时失败。
- [ ] 扫描版阻断。
- [ ] Provider 错误不会标 completed。
- [ ] CLI 不直接承载底层业务逻辑。

---

## FIX 04：持久化 claims、locators 和 entities

### 对应

F003、F013，Hard Gate 3。

### 文件

```text
src/evidence_agent/database/repositories.py
src/evidence_agent/database/unit_of_work.py
src/evidence_agent/application/analyse.py
tests/integration/test_claim_persistence.py
```

### 执行

1. 单一事务写入：
   - source_claims
   - claim_locators
   - entities
   - claim_entity_links
2. 每条 claim 使用全局唯一 ID。
3. `created_by_run_id` 指向 run。
4. 只持久化 exact 或 normalised。
5. ambiguous、not_found 写入 unresolved。
6. 保存：
   - `claims.raw.jsonl`
   - `claims.validated.jsonl`
   - `claims.persisted.jsonl`
   - `unresolved_items.jsonl`
   - `processing_runs.jsonl`
7. 任一写入失败整批回滚。

### 验收

analyse 后：

```sql
SELECT COUNT(*) FROM processing_runs;
SELECT COUNT(*) FROM source_claims;
SELECT COUNT(*) FROM claim_locators;
```

均大于 0。

测试：

- 多条写入。
- locator 失败回滚。
- ID 不重复。
- 重跑产生新 run。
- 同一 run 不重复持久化。
- entities 规范化去重。

---

## FIX 05：补全 locator 校验

### 对应

F011。

### 规则

1. claimed page 必须存在。
2. quote 必须位于该页，或被确定性修正到唯一页面。
3. section 必须属于该 source。
4. quote 必须位于 section 文本。
5. figure 和 table 标签必须在同页或邻近上下文存在。
6. 重复 quote 使用 page、section 消歧。
7. 无法消歧则 ambiguous。
8. normalised match 不得伪装成原始字符 offset。
9. locator confidence：
   - high：page + exact
   - medium：page + normalised
   - low：只定位到 section
10. pending claim 至少有 page 或 section_id。

### 验收

- [ ] 错页被修正或拒绝。
- [ ] 不存在图表编号被标记。
- [ ] 重复 quote 无法消歧时不进入普通复核。
- [ ] 中英文与断行测试通过。

---

# 阶段 B：人工复核与检索

## FIX 06：review export 读取真实 pending claims

### 对应

F004，Hard Gate 4。

### 命令

```bash
evidence-agent review export RUN-ID
```

### 执行

1. 查询 run。
2. 查询该 run 创建且状态为 pending 的 claims。
3. JOIN locator、source、entities。
4. 读取原文上下文。
5. 创建 review_batch 和 rows。
6. 生成非空 packet。
7. 无 pending claims 时返回 `NO_PENDING_CLAIMS`，不生成伪空包。

### CSV 字段

```text
review_batch_id
review_row_id
claim_id
source_id
source_title
claim_type
source_quote
faithful_paraphrase
evidence_basis_description
page
section
figure
table
quote_match_status
locator_confidence
decision
edited_*
review_reason
reviewer
```

### HTML

必须包含：

- 前后文。
- quote 高亮。
- PDF 路径和页码。
- 模型和 Prompt 版本。
- 外部、未经内部验证提示。
- 所有来源文本 HTML escaping。

### 验收

- [ ] packet 行数与 pending 数一致。
- [ ] 空 run 不伪装成功。
- [ ] packet_sha256 写入批次表。
- [ ] HTML 不执行来源脚本。

---

## FIX 07：review apply 重校验和幂等

### 对应

F009、F010，Hard Gate 5。

### 执行

1. 校验 review_batch_id、review_row_id。
2. 校验文件或行哈希。
3. 检查是否已应用。
4. approve 使用原内容。
5. approve_with_edits 重新执行：
   - schema
   - quote match
   - locator
   - claim type
6. reject 保留记录。
7. needs_followup 保持不可搜索。
8. mark_missing 记录 batch issue。
9. 严重错误整批回滚。
10. 成功后更新 batch 状态。
11. 同一批次同一行第二次应用返回 `already_applied`。

### 验收

- [ ] 不存在的编辑 quote 被拒绝。
- [ ] 非法页码被拒绝。
- [ ] 非法 claim type 被拒绝。
- [ ] 重复应用不增加记录。
- [ ] 失败时无部分写入。
- [ ] revision 保存前后内容。

---

## FIX 08：重构 FTS 生命周期

### 对应

F019、F014，Hard Gate 6。

### 规则

1. `search_claims()` 只读。
2. 查询时禁止 INSERT。
3. review apply 后显式同步：
   - approve → upsert
   - approve_with_edits → replace
   - reject → remove
4. `rebuild_fts()` 从 approved claims 重建。
5. 禁止 `except Exception: pass`。
6. 所有异常明确报告。

### 验收

- [ ] approve 后可搜索。
- [ ] reject 后不可搜索。
- [ ] 编辑后搜索结果更新。
- [ ] FTS rebuild 前后结果一致。
- [ ] 中文和英文查询通过。
- [ ] 语法错误不被伪装为空结果。

---

## FIX 09：补充查看命令

### 对应

F012。

### 命令

```bash
evidence-agent source show SRC-ID
evidence-agent claim show CLM-ID
evidence-agent run show RUN-ID
```

### 验收

- [ ] source show 返回元数据、路径、解析状态和 claim 数。
- [ ] claim show 返回 quote、转述、定位、审核和科学状态。
- [ ] run show 返回模型、Prompt、状态、错误和产物。

---

# 阶段 C：恢复、E2E 与真实验收

## FIX 10：资料包写全恢复数据

### 对应

F005。

### 资料包至少包含

```text
manifest.json
parsed/pages.jsonl
parsed/sections.jsonl
analysis/claims.raw.jsonl
analysis/claims.validated.jsonl
analysis/claims.persisted.jsonl
analysis/unresolved_items.jsonl
analysis/review_batches.jsonl
analysis/review_decisions.jsonl
analysis/claim_revisions.jsonl
provenance/processing_runs.jsonl
```

### 规则

- 数据库提交后再写 persisted snapshot。
- 使用临时文件加 atomic rename。
- 每条记录带 schema_version。
- 每个文件保存 SHA-256。
- manifest 保存资源清单。

### 验收

- [ ] 数据库与 JSONL ID 一致。
- [ ] 写文件失败明确报告。
- [ ] 原始 PDF 不修改。

---

## FIX 11：真正从资料包重建数据库

### 对应

F005，Hard Gate 7。

### 命令

```bash
evidence-agent db rebuild-from-packages   --source workspace/external_evidence/sources   --target /tmp/evidence-rebuilt.sqlite
```

现有 drop + migrate 应改名为：

```bash
evidence-agent db reset
```

### 恢复内容

- sources
- assets
- sections
- runs
- claims
- locators
- entities
- links
- review batches
- decisions
- revisions
- FTS

### 验收对比

```text
source IDs
run IDs
claim IDs
locator IDs
review statuses
decision count
revision count
FTS results
```

- [ ] 不覆盖原数据库。
- [ ] 集合和状态一致。
- [ ] foreign key check 通过。
- [ ] 哈希错误明确失败。

---

## FIX 12：替换空白 PDF fixture

### 对应

F006、F015，Hard Gate 9。

### 自制 PDF 要求

至少两页，包含：

- Title
- Abstract
- Materials and Methods
- Results and Discussion
- Conclusion
- reported result
- 带 `suggests` 的 interpretation
- limitation
- Figure 1
- Table 1

建议全部使用自制科学文本，避免版权问题。

至少准备：

- 英文 fixture
- 中文 fixture

Mock claims 必须逐字来自 PDF。

---

## FIX 13：重写真实 E2E

### 对应

F006、F014。

### 正式流程

```text
init
→ db migrate
→ task create
→ ingest
→ parse
→ analyse --provider mock
→ review export
→ review apply
→ query
→ export
→ rebuild-from-packages
→ compare
```

### 强断言

- source count = 1。
- run count ≥ 1。
- claim count ≥ 3。
- locator count > 0。
- review packet rows ≥ 1。
- approved ≥ 1。
- rejected ≥ 1。
- query 返回 approved。
- query 不返回 rejected。
- 导出含 quote 和页码。
- rebuilt DB 的 approved IDs 一致。

删除 `>= 0`、只判断 list 类型、只检查空文件存在等弱断言。

---

## FIX 14：重写 verify round1

### 对应

F001，Hard Gate 8。

### 每项真实检查

`database_integrity`

- integrity_check
- foreign_key_check
- migration version

`ingest_idempotency`

- 同一 fixture 导入两次
- ID 相同
- 行数不增加

`quote_traceability`

- analyse 后 quote 能在页面定位

`review_workflow`

- export 非空
- apply 成功
- decisions 和 revisions 正确

`fts_search`

- approved 可搜
- rejected 不可搜

`database_rebuild`

- 从资料包恢复
- 关键集合一致

`external_data_isolation`

- origin_scope 全部 external
- 科学状态未自动升级
- 无内部数据写入路径

### 行为

任一失败：

```text
xxx=FAIL
ROUND1_VERIFICATION=FAIL
exit 7
```

全部真实通过后才输出 PASS。

测试必须人为破坏至少三项，例如删除 locator、清空 FTS、篡改 manifest 哈希，verify 必须失败。

---

## FIX 15：建立 Golden Set

### 对应

F007，Hard Gate 10。

### 目录

```text
tests/golden/
├── sources/
├── annotations.jsonl
├── expected_metrics.json
└── README.md
scripts/evaluate_golden.py
```

### 最小规模

至少两份自制资料、20 条标注，覆盖：

- 中英文
- reported result
- interpretation
- conclusion
- limitation
- future work
- hedging
- 重复 quote
- 错 locator 负例
- 不存在 quote 负例

### 指标门槛

```text
unsupported accepted claim rate = 0%
approved quote match rate = 100%
approved locator completeness = 100%
hedging preservation ≥ 95%
claim recall ≥ 80%
claim type accuracy ≥ 85%
```

Golden Set 评价记录忠实度，不评价作者观点是否科学正确。

---

# 阶段 D：文档与完成状态

## FIX 16：更新 README 与架构映射

README 必须真实展示：

```bash
evidence-agent init
evidence-agent db migrate
evidence-agent task create ...
evidence-agent ingest ...
evidence-agent parse ...
evidence-agent analyse ...
evidence-agent review export ...
evidence-agent review apply ...
evidence-agent query ...
evidence-agent source show ...
evidence-agent claim show ...
evidence-agent export-source ...
evidence-agent db rebuild-from-packages ...
evidence-agent verify round1
```

增加「计划职责 → 实际模块 → 合并理由 → 测试位置」映射。职责已合理合并时补文档，不创建空壳模块。

---

## FIX 17：重写执行日志

状态只允许：

```text
verified
partial
missing
blocked_external
failed
```

每项记录：

- 实际产物
- 实际命令
- 退出码
- 测试结果
- 已知限制
- commit
- Finding
- 状态

删除无证据的 completed 和「测试数量等于完成度」表述。

---

## FIX 18：生成 Round 1.1 完成报告

文件：

```text
docs/ROUND1_1_COMPLETION_REPORT.md
```

包含：

1. 修补基线。
2. commit 范围。
3. 已关闭和未关闭 Findings。
4. 完整闭环演示。
5. 真实命令和退出码。
6. 数据库统计。
7. E2E 结果。
8. Golden Set 指标。
9. verify 输出。
10. 恢复前后对比。
11. 已知限制。
12. 下一轮建议。

结论只能为 PASS、CONDITIONAL PASS 或 FAIL。任一 Hard Gate 失败必须为 FAIL。

---

# 6. 阶段 Gate

## Gate A：分析闭环

必须完成 FIX 01–05。

验证：

```bash
evidence-agent analyse SRC-ID --task TASK-ID --provider mock
```

数据库中 runs、claims、locators 均非零。

## Gate B：审核与检索

必须完成 FIX 06–09。

验证：

```bash
evidence-agent review export RUN-ID
evidence-agent review apply review_decisions.csv
evidence-agent query "suggests"
```

## Gate C：恢复和验收

必须完成 FIX 10–15：

- 真实 E2E
- verify 无硬编码
- rebuild 可恢复
- Golden Set 达标

## Gate D：文档真实性

必须完成 FIX 16–18：

- README 命令可执行
- 日志真实
- Completion Report 有证据

---

# 7. 建议执行批次

## Batch 1：核心闭环

```text
FIX 01
FIX 02
FIX 03
FIX 04
FIX 05
```

完成后暂停编码，执行 Gate A Review。

## Batch 2：审核和检索

```text
FIX 06
FIX 07
FIX 08
FIX 09
```

完成后执行 Gate B Review。

## Batch 3：恢复和验收

```text
FIX 10
FIX 11
FIX 12
FIX 13
FIX 14
FIX 15
```

完成后执行 Gate C Review。

## Batch 4：文档和报告

```text
FIX 16
FIX 17
FIX 18
```

完成后执行最终验收。

---

# 8. 最终验收命令

```bash
python3.11 -m venv .venv-round11
source .venv-round11/bin/activate
pip install -e ".[dev]"

ruff check .
python -m mypy src
pytest -q

export EVIDENCE_AGENT_WORKSPACE=/tmp/evidence-round11
evidence-agent init
evidence-agent db migrate
evidence-agent db check

evidence-agent task create   --title "Round 1.1 acceptance"   --request "提取测试资料中的作者主张"   --mode analyse_uploaded   --depth source_complete

evidence-agent ingest tests/fixtures/real_scientific_article_en.pdf
evidence-agent parse SRC-ID
evidence-agent analyse SRC-ID --task TASK-ID --provider mock

evidence-agent run show RUN-ID
evidence-agent review export RUN-ID
evidence-agent review apply /path/to/review_decisions.csv

evidence-agent query "solubility"
evidence-agent source show SRC-ID
evidence-agent claim show CLM-ID
evidence-agent export-source SRC-ID

evidence-agent db rebuild-from-packages   --source /tmp/evidence-round11/external_evidence/sources   --target /tmp/evidence-round11-rebuilt.sqlite

python scripts/evaluate_golden.py
evidence-agent verify round1
```

最终输出必须由真实检查产生：

```text
database_integrity=PASS
ingest_idempotency=PASS
quote_traceability=PASS
review_workflow=PASS
fts_search=PASS
database_rebuild=PASS
external_data_isolation=PASS
ROUND1_VERIFICATION=PASS
```

---

# 9. 交给 Coding Agent 的执行指令

```text
严格按照 docs/plans/ROUND1_1_REMEDIATION_PLAN.md 执行。

从 FIX 00 开始，按 Batch 顺序推进。
不得并行开发下一轮功能，也不得一次性修改全部模块。

每完成一个 FIX：
1. 运行该 FIX 的全部测试；
2. 更新 Round 1.1 执行日志；
3. 记录修改文件、命令、退出码和真实结果；
4. 检查 git diff；
5. 验收全部满足后才能进入下一 FIX。

每个 Batch 完成后停止业务代码修改，执行对应 Gate Review。
Gate 未通过时，只修复当前 Batch 内问题。

真实 DeepSeek API 因无 Key 无法运行时：
- Provider parser 和模拟 HTTP 响应测试必须完成；
- 状态写为 blocked_external；
- 不得声称真实 API 已验证。

只有 verify 的全部真实检查通过、Golden Set 达标、数据库恢复一致，
才能将 Round 1.1 标记为 PASS。
```
