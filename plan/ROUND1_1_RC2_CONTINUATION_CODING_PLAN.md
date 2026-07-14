# Literature Evidence Agent — Round 1.1 RC2 后续 Coding Plan

> 执行工具：OpenCode  
> 执行模型：DeepSeek-V4-Pro  
> 仓库：`ZanderKong/literature-evidence-agent`  
> 分支：`fix/round1.1-rc2-hardening`  
> 续跑基线：`d25750891400acde9259dafe514b408d2ae017d7`  
> 计划定位：从当前 14 个 commits 继续，只完成尚未验证的 A04/A06/A07、Batch B 剩余、Batch C、Batch D 剩余和 Batch E。

---

# 1. 当前状态

## 已有成果

```text
PREP 01：回归测试
A01：CLI 与 Provider 显式选择
A02：32 位 UUID 和可注入 ID factory
A03：analyse 输入校验与 task 生命周期初版
A04：source_sections 持久化初版
A05：processing run 元数据
A06：per-run 原子 snapshot 初版
A07：RuntimeContext 初版
B01：review batch 初版
B03：review apply 两阶段校验初版
D01：verify 行为检查初版
```

## 当前不能标记完成的内容

1. `tests/conftest.py` 仍使用 `importlib.reload`。
2. 仍有 ingest 间歇性数据库泄漏。
3. 公开 `parse` 后不保证 `source_sections > 0`。
4. claim persistence 失败尚未证明是 fixture 问题。
5. rebuild identity、review decision、revision 恢复仍失败。
6. `rebuild.py` 仍有：
   - 默认删除目标 DB；
   - 手工按分号拆 migration；
   - `except Exception: pass`；
   - `INSERT OR IGNORE` 静默冲突；
   - 只取第一个 run snapshot；
   - 不完整恢复。
7. D01 必须在 Batch C 完成后重新验收。
8. B02、B04、B05、D02-D04、E01-E05 尚未完成。

## 当前状态标记

```text
A01 verified
A02 verified
A03 verified
A04 in_progress
A05 verified
A06 in_progress
A07 in_progress

B01 provisional_verified
B02 not_started
B03 provisional_verified
B04 not_started
B05 not_started

C01-C03 not_started
D01 provisional
D02-D04 not_started
E01-E05 not_started
```

---

# 2. 执行规则

每个任务必须：

1. 先复现现有失败。
2. 保存完整测试节点和错误。
3. 判断属于实现、fixture 或后续功能缺失。
4. 只有证明实现正确后才能修改 fixture。
5. 运行 focused tests。
6. 运行 `ruff check .`。
7. 运行 `python -m mypy src`。
8. 更新 `docs/plans/ROUND1_1_RC2_EXECUTION_LOG.md`。
9. 执行 `git diff --check`。
10. 创建独立 commit。

禁止：

- 用 `xfail` 隐藏核心缺口。
- 用测试顺序解决共享状态。
- 继续使用 `importlib.reload` 做依赖注入。
- 将间歇性泄漏称为测试数据问题。
- 使用永真断言。
- rebuild 吞掉异常。
- rebuild 生成新业务 ID。
- rebuild 重置审核状态。
- 提前宣布 PASS。
- 扩展在线检索、OCR、向量库、多 Agent、Web UI。

---

# 3. CONT 00：冻结续跑基线

执行：

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log --oneline a93c353..HEAD
pytest -q
ruff check .
python -m mypy src
```

必须确认：

```text
branch = fix/round1.1-rc2-hardening
HEAD = d257508... 或其后由本计划产生的提交
```

将全部失败测试的完整名称写入执行日志。

---

# Batch A2：彻底完成 RuntimeContext、Parse、Snapshot

## FIX A07.1：移除测试中的 module reload

### 修改 `runtime.py`

新增：

```python
def get_explicit_context() -> RuntimeContext | None
def clear_current_context() -> None
```

修正 `use_context()`。

当前逻辑：

```python
old = get_current_context()
```

会在没有显式 context 时创建环境变量 context，并在退出时写入 thread-local。

正确逻辑：

```python
old = get_explicit_context()
set_current_context(ctx)
try:
    yield ctx
finally:
    if old is None:
        clear_current_context()
    else:
        set_current_context(old)
```

### 修改 `tests/conftest.py`

删除：

```text
importlib
_reload_config
_cleanup_config
所有 importlib.reload
```

建立：

```python
@pytest.fixture
def runtime_context(tmp_path):
    ctx = RuntimeContext(tmp_path)
    ctx.ensure_directories()
    with use_context(ctx):
        migrate(ctx.db_path)
        yield ctx
```

旧测试需要 `migrated_workspace` 时，仅返回：

```python
runtime_context.workspace_path
```

### 新增测试

```text
tests/unit/test_runtime_context.py
tests/integration/test_runtime_context_isolation.py
```

覆盖：

- context 退出清理；
- 嵌套恢复；
- A/B DB 隔离；
- 显式 ctx 优先 env；
- env fallback 动态读取；
- 两线程隔离；
- 测试路径无 `importlib.reload`。

### 自检

```bash
grep -R "importlib.reload" tests src/evidence_agent
```

运行时和 fixture 中必须为 0。

### Commit

```text
fix(runtime): make context injection deterministic and reload-free
```

---

## FIX A07.2：修复 ingest DB 泄漏

新增：

```text
test_ingest_isolated_between_contexts
test_ingest_isolation_reverse_order
test_ingest_isolation_repeated_switch
```

场景：

```text
ctx A import PDF
ctx B source count == 0
ctx B import PDF
ctx A source count remains 1
A→B→A
B→A→B
```

所有 ingest 文件和 DB 操作必须使用同一个局部变量：

```python
runtime = ctx or get_current_context()
```

后续只使用 `runtime`，不得混用：

```text
ctx
get_current_context()
旧 config
```

压力测试：

```bash
for i in $(seq 1 20); do
  pytest tests/integration/test_runtime_context_isolation.py -q || exit 1
done
```

### 完成标准

- 20 次无泄漏；
- 顺序互换一致；
- ctx A 不影响 ctx B；
- 去重只在当前 DB 生效。

### Commit

```text
fix(ingest): bind file and database writes to one context
```

---

## FIX A04.1：建立 Parse Application Service

新增：

```text
src/evidence_agent/application/parse.py
```

接口：

```python
def parse_source(
    source_id: str,
    *,
    ctx: RuntimeContext | None = None,
    force: bool = False,
) -> ParseSourceResult
```

流程：

```text
validate source
→ locate PDF
→ parse_pdf
→ allocate/preserve section IDs
→ persist source_sections transactionally
→ atomically write parsed artifacts
→ update manifest
→ return result
```

CLI `evidence-agent parse` 必须调用 `parse_source()`，不得直接调用 parser。

analyse：

- 有有效 parse snapshot 和 DB sections 时复用；
- 缺失时调用 `parse_source()`；
- 删除 analyse 内重复 sections 持久化代码。

相同 source hash、parser version、text hash 重跑时幂等。

删除 parser sections 相关 `xfail`。

测试：

```text
tests/integration/test_parse_service.py
tests/integration/test_parse_cli.py
```

必须检查：

```sql
SELECT COUNT(*) FROM source_sections WHERE source_id = ?
```

结果大于 0。

### Commit

```text
feat(parse): persist sections through a public application service
```

---

## FIX A06.1：判定 claim persistence 失败

在修改 fixture 前生成对比：

```text
DB claim_id vs snapshot claim_id
DB locator_id vs snapshot locator_id
DB created_by_run_id vs snapshot run_id
DB section_id vs snapshot section_id
DB canonical hash vs snapshot canonical hash
```

正确的 persisted record 至少包含：

```text
schema_version
record_type
claim_id
locator_id
section_id
source_id
task_id
run_id
claim fields
locator fields
review status
scientific status
created_at
updated_at
```

只有同时满足：

- DB 与 snapshot ID 一致；
- canonical content 一致；
- fixture 使用旧 `_claim_id` 或旧 schema；

才允许修改 fixture。判断依据写入执行日志。

测试：

- DB/snapshot exact match；
- 多 claims；
- 多 runs 不覆盖；
- 文件失败不提交 DB；
- DB 失败不 finalize；
- 无残留 `.tmp`。

### Commit

```text
fix(snapshot): align persisted records with committed database state
```

---

## Gate A2

Focused：

```bash
pytest   tests/unit/test_runtime_context.py   tests/integration/test_runtime_context_isolation.py   tests/integration/test_parse_service.py   tests/integration/test_parse_cli.py   tests/integration/test_sections_persistence.py   tests/integration/test_claim_persistence.py   -q
```

完整测试连续三次：

```bash
pytest -q
pytest -q
pytest -q
```

加入 `pytest-randomly`：

```bash
pytest -q --randomly-seed=1
pytest -q --randomly-seed=2
pytest -q --randomly-seed=3
```

允许失败的只能是明确依赖 Batch C 的 rebuild tests。

不允许：

- ingest 隔离失败；
- section 失败；
- claim persistence 失败；
- xfail；
- seed 相关变化。

产物：

```text
docs/reviews/round1_rc2/GATE_A2_REPORT.md
```

Gate A2 未通过禁止进入 Batch B2。

---

# Batch B2：完成 Review、FTS 和 Task 生命周期

## FIX B01.1：Review Batch 幂等

确认：

```text
review_batch_id
review_row_id
packet_sha256
row_input_sha256
```

写入 DB、CSV、JSONL 和 package。

重复 export：

- 内容不变 → 同一 batch；
- 内容变化 → 新 batch；
- row 顺序稳定；
- packet hash 与文件一致。

若 migration 004 不足，新增 migration 005，禁止修改已发布 migration。

### Commit

```text
fix(review): make packet identities reproducible
```

---

## FIX B02：复核包上下文与安全

CSV 必须包含：

```text
review_batch_id
review_row_id
run_id
claim_id
source_id
source_title
source_relative_path
claim_type
source_quote
context_before
context_after
paraphrase
evidence basis
scope
hedging
page
section_id
section_heading
figure/table
match/confidence
model/prompt
review/scientific status
decision and edited fields
```

HTML/Markdown：

- HTML escape；
- quote 高亮；
- 前后文；
- PDF 相对路径；
- 页码；
- batch/row/run；
- model/prompt；
- external/unverified 提示；
- 不暴露 Key、绝对私人路径。

测试：

- script injection；
- 上下文正确；
- 仅当前 run；
- pending claims 数量一致；
- CSV row hash 一致。

### Commit

```text
feat(review): export contextual and safe adjudication packets
```

---

## FIX B03.1：补全 Review Apply

流程必须为：

```text
read
→ prevalidate every nonblank row
→ build apply plan
→ if fatal error: write nothing
→ one transaction
→ FTS sync
→ package snapshot
```

任一情况整批失败：

- batch/row 不存在；
- row 不属于 batch；
- hash 不一致；
- claim 不存在；
- source sections 不存在；
- edited quote 不存在；
- page/section 错误；
- quote 不在 page/section；
- figure/table 不存在；
- claim type 非法；
- paraphrase/basis 为空。

空 decision 允许跳过，batch 为 `partially_applied`。

幂等键：

```text
review_batch_id + review_row_id
```

第二次返回 `already_applied`，不得新增 decision/revision。

成功后 snapshot：

```text
review/batches/RVB-ID/batch.json
rows.jsonl
decisions.jsonl
revisions.jsonl
```

### Commit

```text
fix(review): apply complete batches atomically and snapshot outcomes
```

---

## FIX B04：FTS 生命周期

实现：

```python
index_claim
replace_claim
remove_claim
rebuild_fts
```

规则：

```text
pending → no index
approved → index
approved_with_edits → edited index
rejected → remove
needs_followup → no index
```

强断言：

- approved > 0；
- rejected == 0；
- pending == 0；
- old edited quote == 0；
- new edited quote > 0；
- rebuild 前后 IDs 相同；
- 中英文查询。

无效 FTS 输入不得静默返回空结果。

### Commit

```text
fix(search): enforce review-aware FTS lifecycle and safe queries
```

---

## FIX B05：Task 生命周期

```text
created
→ running
→ review when pending claims exist
→ completed when all claims have terminal decisions
→ failed when analyse fails
```

多 source task：

- 任一 pending → review；
- 全部终态 → completed；
- analyse failure 有明确状态和 warning。

测试：

- 单 claim；
- approve/reject；
- needs_followup；
- 多 source；
- analyse failure；
- 重复 apply。

### Commit

```text
feat(tasks): derive lifecycle from analysis and review state
```

---

## Gate B2

公开 CLI 完成：

```text
task create
ingest
parse
analyse
review export
review apply
query
```

必须包含 approve、approve_with_edits、reject。

验证：

- invalid edit 整批回滚；
- approved 可搜；
- rejected 不可搜；
- old edited 不可搜；
- task 状态正确。

产物：

```text
docs/reviews/round1_rc2/GATE_B2_REPORT.md
```

---

# Batch C：完整 Package 与精确 Rebuild

## FIX C01：完整 Package Snapshot

manifest schema version 2，保存每个 artifact：

```text
path
sha256
record_type
record_count
```

必须 snapshot：

```text
research_tasks
sources
assets
sections
all processing_runs
claims
locators
entities
links
review_batches
review_rows
review_decisions
revisions
```

必须读取所有：

```text
analysis/runs/RUN-*/
```

禁止当前“只取第一个 run”行为。

新增：

```bash
evidence-agent package sync SRC-ID
evidence-agent package check SRC-ID
```

check 验证：

- 文件；
- hash；
- count；
- 引用完整；
- 无 tmp；
- schema 支持。

sync 使用 staging + atomic replace，失败不破坏旧 snapshot。

### Commit

```text
feat(package): persist complete versioned source state
```

---

## FIX C02.1：重构 Migration Runner

彻底删除：

```python
sql.split(";")
except Exception:
    pass
```

migration service 接受显式 `db_path` 或 connection，使用 `executescript` 或等价原子执行。

失败时：

- rollback；
- 不写 schema version；
- 输出 migration name 和错误；
- rebuild 失败。

### Commit

```text
fix(migrations): apply target migrations atomically and visibly
```

---

## FIX C02.2：精确 Rebuild

接口：

```python
rebuild_from_packages(
    source_dir,
    target_db,
    *,
    replace=False,
)
```

规则：

- target 存在且无 replace → 失败；
- replace 时先备份；
- 禁止默认 unlink；
- 全部 package check 通过后才导入；
- 任一 fatal error → 整体失败；
- 禁止 `INSERT OR IGNORE` 静默冲突。

恢复顺序：

```text
tasks
sources
assets
sections
runs
claims
locators
entities
links
batches
rows
decisions
revisions
FTS
```

保持原始：

```text
所有 ID
timestamps
review status
scientific status
created_by_run_id
edited content
decision/revision history
```

冲突返回：

```text
RESTORE_CONFLICT
```

现有三个 rebuild 失败测试必须转绿。

### Commit

```text
fix(rebuild): restore exact complete state without silent conflicts
```

---

## FIX C03：DB Snapshot 与 Compare

新增：

```bash
evidence-agent db snapshot-summary --database PATH
evidence-agent db compare DB_A DB_B
```

比较：

- schema；
- counts；
- ID sets；
- canonical hashes；
- review distribution；
- decisions/revisions；
- FTS；
- integrity；
- foreign keys。

不同 exit 7，相同 exit 0。

### Commit

```text
feat(database): compare canonical original and rebuilt state
```

---

## Gate C

至少：

- 英文和中文 PDF；
- 两个 runs；
- approve；
- approve_with_edits；
- reject；
- revision；
- package sync/check；
- rebuild；
- db compare。

要求：

```text
ID exact
content exact
review exact
history exact
FTS exact
FK ok
```

产物：

```text
docs/reviews/round1_rc2/GATE_C_REPORT.md
```

---

# Batch D2：Verify、强 E2E、Golden Set

## FIX D01.1：重新验收 Verify

Batch C 完成后重新检查七项：

1. database integrity；
2. ingest idempotency；
3. quote traceability；
4. review workflow；
5. FTS；
6. real rebuild + compare；
7. external isolation。

Verify 必须创建独立 RuntimeContext，不污染用户 DB。

破坏性测试：

- 删除 locator；
- 清空 FTS；
- 篡改 manifest；
- 删除 decision；
- 破坏 origin scope。

对应 check 必须 FAIL。

### Commit

```text
fix(verify): validate all behavioral hard gates against restored state
```

---

## FIX D02：强 CLI E2E

只使用公开 CLI：

```text
init
migrate
task create
ingest
parse
analyse
run-show
review export
review apply
query
source-show
claim-show
export
package sync/check
rebuild
db compare
verify
```

强断言：

```text
sections > 0
claims >= 3
locators == claims
packet rows == pending
approved >= 1
edited >= 1
rejected >= 1
approved query > 0
rejected query == 0
old edited == 0
new edited > 0
export contains source/page/approved
export excludes rejected
db compare exit 0
verify exit 0
```

删除所有弱断言。

### Commit

```text
test(e2e): enforce complete public CLI and restoration lifecycle
```

---

## FIX D03：中英文 Golden Set

最低：

```text
2 英文 PDF
2 中文 PDF
24 正例
8 负例
总计 >= 32
```

覆盖九种 claim type、hedging、scope、错误 locator、因果夸大、推测写成事实。

Evaluator 必须计算：

```text
recall
negative extraction
unsupported accepted
quote match
locator completeness
claim type accuracy
hedging preservation
scope preservation
```

修复：

- glob；
- negative 不作为支持；
- approved/pending 区分；
- 逐样本输出；
- JSON + Markdown。

阈值：

```text
unsupported = 0%
negative extraction = 0%
quote = 100%
locator = 100%
recall >= 80%
type >= 85%
hedging >= 95%
scope >= 90%
```

### Commit

```text
test(golden): evaluate bilingual fidelity with positive and negative cases
```

---

## FIX D04：DeepSeek Live Smoke

有 Key：

```bash
pytest -m live_deepseek -q
```

验证 API、非空 claims、quote、model/run metadata、Key 不泄漏。

无 Key：

```text
blocked_external
```

最终最多 CONDITIONAL PASS。

---

## Gate D

```bash
ruff check .
python -m mypy src
pytest -q
python scripts/evaluate_golden.py ...
evidence-agent verify --round-name round1
```

要求：

- 0 failed；
- 无核心 xfail；
- Golden 达标；
- Verify 全 PASS。

---

# Batch E：CI、文档、独立 Review

## E01 GitHub Actions

Python 3.11/3.12：

```text
ruff
mypy
pytest
offline verify
golden
```

不运行 live API。

## E02 Execution Log

真实更新所有任务状态、commit、命令和退出码。

## E03 README

展示真实 provider、parse、review batch、package、rebuild、compare、verify 和限制。

## E04 Completion Report

包含：

- 基线/final commit；
- 12 Hard Gates；
- 重复/随机测试；
- E2E；
- Golden；
- rebuild compare；
- Verify；
- live status；
- PASS/CONDITIONAL PASS/FAIL。

## E05 独立只读 Review

新 session，不修改业务代码。

产物：

```text
00_scope.md
01_clean_environment.md
02_hard_gate_matrix.csv
03_runtime_isolation_audit.md
04_review_audit.md
05_rebuild_audit.md
06_golden_report.md
07_findings.csv
08_final_report.md
```

P0/P1 存在则 FAIL，返回对应 Batch 修复。

---

# 4. 允许停止条件

DeepSeek 只能在以下情况停止：

1. OpenCode step limit 强制结束；
2. live API 缺 Key；
3. 外部权限/工具不可用；
4. 存在可能破坏用户数据的未决风险；
5. 全部任务完成。

测试失败、fixture 更新、rebuild 复杂、需要重构均不属于停止理由。

---

# 5. 继续执行 Prompt

```text
继续执行：

@AGENTS.md
@plan/ROUND1_1_RC2_CONTINUATION_CODING_PLAN.md
@docs/plans/ROUND1_1_RC2_EXECUTION_LOG.md

分支必须为 fix/round1.1-rc2-hardening。
从 CONT 00 开始。

先完成 Batch A2：
- 移除 tests/conftest.py 的 importlib.reload；
- 修正 RuntimeContext 清理；
- 修复 ingest 泄漏；
- 建立 parse application service；
- 对 claim persistence 先比较 DB/snapshot，再决定修改 fixture；
- 删除相关 xfail；
- 完成三次 pytest 和三个随机 seed。

除明确依赖 Batch C 的 rebuild tests 外，不得剩余失败。

然后严格按：
Batch B2 → Batch C → Batch D2 → Batch E。

每个任务：
先复现 → 修实现 → focused tests → ruff → mypy → execution log → git diff → commit。

不得把测试数据问题作为无证据结论。
不得在 rebuild 中吞异常、生成新 ID、重置审核状态。
不得提前声明 PASS。
最终以独立只读 Review 为准。
```
