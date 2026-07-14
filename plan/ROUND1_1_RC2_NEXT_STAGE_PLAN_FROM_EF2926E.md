# Literature Evidence Agent — Round 1.1 RC2 下一阶段精准 Coding Plan

> 执行工具：OpenCode  
> 执行模型：DeepSeek-V4-Pro  
> 仓库：`ZanderKong/literature-evidence-agent`  
> 唯一工作分支：`fix/round1.1-rc2-hardening`  
> 当前固定基线：`ef2926e7f5f8171048340c7fd29111b776730980`  
> 稳定分支：`main`

---

# 0. 下一阶段目标

当前版本已经完成 RuntimeContext、测试隔离、公开 parse service、source sections 持久化和 Gate A2。当前报告为：

```text
169 passed
3 failed
ruff clean
mypy clean
```

3 个失败均属于 rebuild 范围。

下一阶段只完成：

```text
仓库卫生
→ Review batch / packet / apply 完整闭环
→ FTS 与 task lifecycle
→ 完整 source package snapshot
→ 原子 migration
→ 精确 rebuild
→ DB compare
→ verify 重验
→ 强 CLI E2E
→ 中英文 Golden Set
→ CI / 文档
→ 固定 Review tag
```

---

# 1. 执行纪律

每个 FIX 必须执行：

```text
读取当前实现
→ 建立或运行失败测试
→ 确认旧实现因正确原因失败
→ 修改实现
→ focused tests
→ ruff
→ mypy
→ 更新 execution log
→ git diff --check
→ 独立 commit
→ push 当前工作分支
```

禁止：

- 新建 coding 或 review 分支；
- 修改 `main`；
- 用 `xfail` 隐藏核心缺口；
- 修改核心断言迁就错误实现；
- 使用 `COUNT >= 0` 等永真断言；
- 只检查表或文件存在；
- 使用 `except Exception: pass`；
- rebuild 使用 `INSERT OR IGNORE`；
- rebuild 生成新业务 ID；
- rebuild 重置审核状态；
- rebuild 只读取第一个 run；
- 提交虚拟环境、数据库、Key 或 workspace；
- 在独立 Review 前写 PASS；
- 扩展在线检索、OCR、向量数据库、Web UI、多 Agent。

---

# 2. Phase H — 仓库卫生与执行基线

## H00：冻结当前远程基线

运行：

```bash
git fetch origin
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/fix/round1.1-rc2-hardening
git log -5 --oneline
```

必须确认：

```text
branch = fix/round1.1-rc2-hardening
local HEAD = remote HEAD
HEAD = ef2926e7f5f8171048340c7fd29111b776730980
working tree clean
```

然后运行：

```bash
pytest -q
ruff check .
python -m mypy src
```

把 3 个失败节点完整写入 execution log。

---

## H01：清除误提交的 `.venv-rc2`

当前 HEAD 跟踪了完整 `.venv-rc2/`，必须先清理。

### H01.1 安全点

```bash
git tag rc2-before-venv-cleanup ef2926e
git show --no-patch rc2-before-venv-cleanup
```

### H01.2 确认污染来源

```bash
git log --oneline -- .venv-rc2
git diff --name-status 4c13559..ef2926e -- .venv-rc2
```

若只有 `ef2926e` 引入，使用 amend；若更早 commit 已引入，使用 interactive rebase 从第一个污染 commit 的父提交清理。

### H01.3 更新 `.gitignore`

加入：

```gitignore
.venv*/
venv*/
```

### H01.4 从 index 删除

```bash
git rm -r --cached .venv-rc2
git add .gitignore
git status --short
git diff --cached --stat
```

不得混入业务代码。

### H01.5 修正当前 commit

若仅 HEAD 污染：

```bash
git commit --amend --no-edit
```

记录新 SHA。

### H01.6 验证

```bash
git ls-files | grep '^.venv-rc2/' && exit 1 || true
git ls-tree -r HEAD --name-only | grep '^.venv-rc2/' && exit 1 || true
git check-ignore -v .venv-rc2/pyvenv.cfg
```

### H01.7 回归测试

```bash
ruff check .
python -m mypy src
pytest -q
```

测试结果不得回退。

### H01.8 推送

```bash
git push --force-with-lease origin fix/round1.1-rc2-hardening
```

禁止普通 `--force`。

### H01.9 远程复核

```bash
git fetch origin
git rev-parse HEAD
git rev-parse origin/fix/round1.1-rc2-hardening
git ls-tree -r origin/fix/round1.1-rc2-hardening --name-only \
  | grep '^.venv-rc2/' && exit 1 || true
```

确认后删除本地 tag：

```bash
git tag -d rc2-before-venv-cleanup
```

---

## H02：扫描其他污染

```bash
git ls-files | grep -E '(^|/)(\.venv[^/]*|venv[^/]*|env[^/]*)/' && exit 1 || true
git ls-files | grep -E '\.(sqlite|db|pyc|pyo|dylib|so)$' && exit 1 || true
```

扫描大文件：

```bash
python - <<'PY'
import os, subprocess
paths = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
bad = []
for raw in paths:
    if not raw:
        continue
    p = raw.decode()
    if os.path.isfile(p) and os.path.getsize(p) > 5 * 1024 * 1024:
        bad.append((os.path.getsize(p), p))
for size, p in sorted(bad, reverse=True):
    print(f"{size / 1024 / 1024:.2f} MB\t{p}")
raise SystemExit(1 if bad else 0)
PY
```

扫描秘密：

```bash
git grep -n -I -E '(sk-[A-Za-z0-9]{20,}|api[_-]?key\s*[:=]|Authorization:\s*Bearer)' \
  -- . ':!tests/fixtures' && exit 1 || true
```

---

## H03：安装本阶段 Plan

把本文件加入：

```text
plan/ROUND1_1_RC2_NEXT_STAGE_PLAN_FROM_EF2926E.md
```

更新 `AGENTS.md`：

```text
当前唯一执行计划：
plan/ROUND1_1_RC2_NEXT_STAGE_PLAN_FROM_EF2926E.md

当前唯一工作分支：
fix/round1.1-rc2-hardening

禁止建立额外 coding/review 分支。
Review 使用固定 tag。
每个 FIX 更新 execution log。
```

创建或更新 `opencode.json`：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": [
    "AGENTS.md",
    "plan/ROUND1_1_RC2_NEXT_STAGE_PLAN_FROM_EF2926E.md",
    "docs/plans/ROUND1_1_RC2_EXECUTION_LOG.md"
  ],
  "snapshot": true,
  "autoupdate": "notify"
}
```

更新 Execution Log：

```text
Tests: 169 passing / 3 rebuild failing
A04: verified
A07: verified
B01: provisional
B03: provisional
D01: provisional
```

旧 147/7 状态标记为 `Superseded`。

提交：

```bash
git add AGENTS.md opencode.json \
  plan/ROUND1_1_RC2_NEXT_STAGE_PLAN_FROM_EF2926E.md \
  docs/plans/ROUND1_1_RC2_EXECUTION_LOG.md

git diff --cached --check
git commit -m "docs(rc2): install next-stage execution plan"
git push origin fix/round1.1-rc2-hardening
```

---

# 3. Phase B — Review、FTS、Task Lifecycle

## B00：固定当前 3 个失败

运行完整测试并逐个运行失败节点：

```bash
pytest -q
pytest <node-1> -q -vv
pytest <node-2> -q -vv
pytest <node-3> -q -vv
```

每个失败记录：

```text
test node
expected
actual
root cause
mapped FIX
```

必须全部映射到 Phase C。

---

## B01：Review Batch 稳定身份

先新增失败测试：

```text
test_same_packet_reuses_batch_id
test_same_packet_reuses_row_ids
test_changed_claim_creates_new_batch
test_packet_order_is_deterministic
test_csv_contains_batch_row_hashes
test_decision_batch_row_unique_constraint
```

新增 migration：

```text
migrations/005_review_integrity.sql
```

至少增加：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_review_decisions_batch_row
ON review_decisions(review_batch_id, review_row_id)
WHERE review_batch_id IS NOT NULL
AND review_row_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_review_batch_rows_claim
ON review_batch_rows(claim_id);

CREATE INDEX IF NOT EXISTS idx_review_batches_run_status
ON review_batches(run_id, status);
```

新增 helper：

```python
canonical_review_row()
hash_review_row()
hash_review_packet()
```

Canonical JSON 必须：

```python
json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

查询排序：

```sql
ORDER BY COALESCE(l.page, 2147483647), c.claim_type, c.claim_id
```

生成 packet 后：

```text
相同 run + 相同 packet hash → 复用 batch/row IDs
内容变化 → 新 batch
```

CSV/JSONL/MD/HTML 每行加入：

```text
review_batch_id
review_row_id
row_input_sha256
packet_sha256
run_id
```

验收：

```bash
pytest tests/integration/test_review_batches.py tests/integration/test_review_export.py -q
ruff check .
python -m mypy src
```

提交：

```bash
git commit -am "fix(review): make batch and row identities reproducible"
git push
```

---

## B02：Review Packet 上下文与安全

Review export JOIN：

```text
source_claims
claim_locators
sources
source_assets
source_sections
processing_runs
```

输出必须包含：

```text
relative path
section ID / heading
context before / after
page
model / mode
prompt version
parser version
code commit
review/scientific status
```

新增：

```python
extract_quote_context(text, quote, radius=240)
```

规则：

- exact 优先；
- normalised 保留状态；
- 多次出现用 locator 消歧；
- 无法消歧标 ambiguous；
- 不跨 source/section。

所有 HTML 内容必须 `html.escape`。

只输出 source relative path，禁止绝对路径。

CSV、JSONL、MD、HTML 使用原子写：

```text
tmp → flush → fsync → os.replace
```

测试：

```text
context correct
requested run only
absolute path absent
script escaped
provenance present
```

验收：

```bash
pytest tests/unit/test_review_packet.py tests/integration/test_review_export.py -q
ruff check .
python -m mypy src
```

提交：

```bash
git commit -am "feat(review): export contextual and safe review packets"
git push
```

---

## B03：Review Apply 批次校验

新增失败测试：

```text
missing batch ID
missing row ID
row not in batch
row hash mismatch
claim mismatch
one invalid row rolls back all
same row second apply idempotent
new batch can re-review claim
empty decision leaves partial
```

每个非空 decision 行必须包含：

```text
review_batch_id
review_row_id
row_input_sha256
claim_id
```

同一 CSV 的有效 decision 必须属于同一 batch。

一次性 preload：

```text
batches
rows
claims
locators
sections
```

验证：

```text
batch exists
row exists
row belongs to batch
claim matches
hash matches
```

`approve_with_edits` 必须验证：

```text
quote/paraphrase/basis nonempty
claim type valid
section belongs to source
page exists
quote in section
quote in page
figure/table exists
origin external
scientific status unverified
```

禁止把全部 sections 拼成一段后只做全局匹配。

事务前生成 Application Plan；任一错误必须 DB/FTS 不变。

事务内：

```text
insert decision with batch/row
insert revision
update claim
update locator
update FTS
set row.applied_at
update batch status/completed_at
```

幂等键：

```text
review_batch_id + review_row_id
```

验收：

```bash
pytest tests/integration/test_review_apply.py \
  tests/regression/test_review_edit_revalidation.py \
  tests/integration/test_review_batches.py -q
ruff check .
python -m mypy src
```

提交：

```bash
git commit -am "fix(review): apply verified review batches atomically"
git push
```

---

## B04：FTS 生命周期与安全查询

拆分或集中实现：

```python
index_claim()
replace_claim()
remove_claim()
rebuild_fts()
compile_safe_query()
search_claims()
```

规则：

```text
pending → no index
approved → index
approved_with_edits → current edited content
rejected → remove
needs_followup → no index
```

禁止直接将原始用户输入传给 `MATCH`。

结果从 DB 返回：

```text
origin_scope
relative path
section ID/heading
page
review status
scientific status
```

测试：

```text
approved searchable
pending/rejected not searchable
old edited text removed
new edited text searchable
rebuild same IDs
invalid query explicit error
Chinese/English query
```

验收：

```bash
pytest tests/integration/test_fts.py -q
ruff check .
python -m mypy src
```

提交：

```bash
git commit -am "fix(search): enforce review-aware FTS and safe queries"
git push
```

---

## B05：Task Lifecycle

集中实现：

```python
derive_task_status()
refresh_task_status()
```

规则：

```text
created
running
review
completed
failed
```

调用于 analyse start/complete/fail 和 review apply complete。

多 source：

- 任一 pending / needs_followup → review；
- 所有成功 claims 终态 → completed；
- 所有 runs failed → failed；
- 部分成功、部分失败 → 根据成功 claims 状态，warning 记录失败 source；
- 成功但 0 claims → completed + NO_CLAIMS_FOUND warning。

验收：

```bash
pytest tests/integration/test_task_lifecycle.py -q
ruff check .
python -m mypy src
```

提交：

```bash
git commit -am "feat(tasks): derive lifecycle from analysis and review state"
git push
```

---

## Gate B

运行完整测试，允许失败仅限 3 个 rebuild tests。

新临时 workspace 执行：

```text
init → migrate → task → ingest → parse → analyse mock
→ review export → approve/edit/reject → apply → query
```

验证：

```text
batch/rows/decisions/revision present
invalid edit rollback
repeat apply idempotent
approved searchable
rejected and old edit not searchable
new edit searchable
task status correct
```

生成：

```text
docs/rounds/round1_1_rc2/gates/GATE_B_REPORT.md
```

提交并 push。

---

# 4. Phase C — 完整 Snapshot 与精确 Rebuild

## C01：不可变 Source State Snapshot

新增模块：

```text
src/evidence_agent/source_package/
  canonical.py
  schemas.py
  snapshot.py
  integrity.py
```

新结构：

```text
SRC-ID/state/current.json
SRC-ID/state/snapshots/SNP-ID/manifest.json
SRC-ID/state/snapshots/SNP-ID/records/*.jsonl
```

records 必须包含：

```text
research_tasks
sources
assets
sections
all runs
claims
locators
entities
links
batches
rows
decisions
revisions
```

Snapshot 使用 canonical JSON，按 primary key 排序。

写入流程：

```text
.tmp-SNP → write/fsync → validate → rename snapshot
→ atomic current.json pointer
```

失败不改变旧 snapshot。

新增 CLI：

```bash
evidence-agent package sync SRC-ID
evidence-agent package check SRC-ID
evidence-agent package list SRC-ID
```

自动同步点：analyse complete、review apply complete。

测试：

```text
all runs
review history
entities
manifest counts/hashes
atomic pointer
failed sync preserves old
hash tamper
missing file
dangling ID
```

验收：

```bash
pytest tests/integration/test_package_snapshot.py \
  tests/integration/test_package_integrity.py -q
ruff check .
python -m mypy src
```

提交：

```bash
git commit -am "feat(package): persist immutable complete source snapshots"
git push
```

---

## C02：原子 Migration Runner

统一接口：

```python
migrate(db_path=None, *, conn=None)
```

删除：

```text
sql.split(';')
except Exception: pass
```

使用事务执行 migration；失败 rollback、抛 `MigrationError`、不写 version、不继续。

测试：

```text
failure no version
failure rollback
explicit target DB
repeated migrate no-op
```

验收：

```bash
pytest tests/integration/test_migrations.py \
  tests/regression/test_migration_atomicity.py -q
ruff check .
python -m mypy src
```

提交：

```bash
git commit -am "fix(migrations): apply migrations atomically"
git push
```

---

## C03：精确 Rebuild

接口：

```python
rebuild_from_packages(source_dir, target_db, replace=False)
```

目标保护：

- target 存在且 replace=False → fail；
- replace=True → 先备份；
- 在同目录 temp DB 恢复；
- 全部验收后 atomic replace；
- 失败保留原 DB。

Preflight：

```text
scan packages
load current snapshot
check manifest/hash/count/schema
build global restore plan
detect ID conflicts
```

共享记录：

```text
same ID + same hash = duplicate_identical
same ID + different hash = RESTORE_CONFLICT
```

禁止 `INSERT OR IGNORE`。

恢复顺序：

```text
tasks → sources → assets → sections → runs → claims → locators
→ entities → links → batches → rows → decisions → revisions → FTS
```

保持全部 ID、timestamps、statuses、current edited content、history。

在 temp DB 执行：

```text
integrity_check=ok
foreign_key_check empty
expected counts/IDs/hashes/statuses match
```

转绿当前 3 个失败测试，禁止改核心断言。

新增：

```text
target exists
replace backup
bad hash
two runs
two batches
entities
conflicting shared task
no silent errors
```

验收：

```bash
pytest tests/integration/test_rebuild_complete_state.py \
  tests/regression/test_rebuild_identity.py \
  tests/integration/test_package_integrity.py -q
ruff check .
python -m mypy src
```

提交：

```bash
git commit -am "fix(rebuild): restore exact reviewed evidence state"
git push
```

---

## C04：DB Summary 与 Compare

新增：

```text
src/evidence_agent/database/state_compare.py
```

每张核心表计算：

```text
count
ID set hash
canonical row hash
```

附：schema、status distributions、decision/revision hashes、FTS、integrity、FK。

CLI：

```bash
evidence-agent db snapshot-summary --database DB --output FILE
evidence-agent db compare DB_A DB_B --output FILE
```

exit：equal=0，different=7，invalid=3。

验收：

```bash
pytest tests/integration/test_database_compare.py -q
ruff check .
python -m mypy src
```

提交：

```bash
git commit -am "feat(database): compare canonical database states"
git push
```

---

## Gate C

必须 `pytest -q` 0 failed。

临时 workspace 建立英文/中文 source、2 runs、approve/edit/reject、revision、entity link。

执行：

```text
package sync/check
snapshot-summary original
rebuild
db compare
```

必须：

```text
IDs exact
content exact
statuses exact
history exact
FTS exact
integrity ok
FK empty
```

生成 `GATE_C_REPORT.md`，提交并 push。

---

# 5. Phase D — Verify、E2E、Golden Set

## D01：Verify 重验

Verify 创建独立 TemporaryDirectory 和 RuntimeContext，不污染用户 DB。

七项真实检查：

```text
database_integrity
ingest_idempotency
quote_traceability
review_workflow
fts_search
database_rebuild
external_data_isolation
```

必须真实执行 review、search、package、rebuild、compare。

破坏 locator、FTS、manifest、decision、origin_scope 时对应检查必须 FAIL。

验收：

```bash
pytest tests/integration/test_verify_round1.py \
  tests/regression/test_verify_real_checks.py -q
ruff check .
python -m mypy src
```

提交：

```bash
git commit -am "fix(verify): execute isolated behavioral checks"
git push
```

---

## D02：强 CLI E2E

只使用公开 CLI：

```text
init → migrate → task → ingest → parse → analyse
→ review export/apply → query/show/export
→ package sync/check → rebuild → compare → verify
```

强断言：

```text
source == 1
sections > 0
runs == 1
claims >= 3
locators == claims
packet == pending
approved/edit/reject >= 1
approved search > 0
rejected and old edit == 0
new edit > 0
export includes approved/page/source
export excludes rejected
compare exit 0
verify exit 0
```

验收：

```bash
pytest tests/e2e/test_cli_round1_rc2.py -q
ruff check .
python -m mypy src
```

提交：

```bash
git commit -am "test(e2e): enforce complete public CLI lifecycle"
git push
```

---

## D03：中英文 Golden Set

最低：

```text
2 English PDFs
2 Chinese PDFs
24 positive
8 negative
32 total
```

覆盖 9 claim types、hedging、scope、错误 locator、因果夸大和推测事实化。

Evaluator 计算：

```text
recall
negative extraction
unsupported accepted
quote match
locator completeness
type accuracy
hedging preservation
scope preservation
```

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

验收：

```bash
pytest tests/golden tests/unit/test_golden_evaluator.py -q
python scripts/evaluate_golden.py ...
```

提交：

```bash
git commit -am "test(golden): add bilingual fidelity evaluation"
git push
```

---

## D04：DeepSeek Live Smoke

新增 `live_deepseek` marker，普通 CI 不执行。

有 Key：

```bash
pytest -m live_deepseek -q
```

验证 HTTP、claims、quote、model/prompt metadata、无 Key 泄漏。

无 Key：标记 `blocked_external`，最终最多 Conditional Pass。

---

## Gate D

执行：

```bash
ruff check .
python -m mypy src
pytest -q
pytest -q
pytest -q
pytest -q --randomly-seed=1
pytest -q --randomly-seed=2
pytest -q --randomly-seed=3
evidence-agent verify --round-name round1
python scripts/evaluate_golden.py ...
```

要求：0 failed、0 core xfail、随机顺序稳定、Verify PASS、Golden 达标。

---

# 6. Phase E — CI、文档与 Review Candidate

## E01：GitHub Actions

创建 `.github/workflows/ci.yml`，Python 3.11/3.12，执行：

```text
ruff
mypy
pytest
offline verify
Golden evaluator
```

不运行 live DeepSeek，不上传 workspace/DB/Key。

## E02：README

逐条验证 setup、provider、task、ingest、parse、analyse、review、query、package、rebuild、compare、verify 命令。

明确 mock 仅测试、external/unverified 边界和已知 PDF 限制。

## E03：Execution Log

更新全部 FIX status、commit、tests、Gate report、external block、NEXT_TASK/NEXT_COMMAND。

## E04：Completion Report

创建：

```text
docs/rounds/round1_1_rc2/reports/COMPLETION_REPORT.md
```

Review 前结论只能：

```text
PENDING INDEPENDENT REVIEW
```

## E05：仓库卫生

```bash
git status --short
git diff --check
git ls-files | grep -E '(^|/)\.venv|\.sqlite$|\.db$|\.dylib$|\.so$' \
  && exit 1 || true
```

## E06：冻结 Review Candidate

```bash
git tag -a round1.1-rc2-review-01 \
  -m "Round 1.1 RC2 review candidate 01"
git push origin round1.1-rc2-review-01
```

Review 必须基于固定 tag/commit，不基于移动 branch HEAD。

---

# 7. 推荐 commit 顺序

```text
1. docs(rc2): install next-stage execution plan
2. fix(review): make batch and row identities reproducible
3. feat(review): export contextual and safe review packets
4. fix(review): apply verified review batches atomically
5. fix(search): enforce review-aware FTS and safe queries
6. feat(tasks): derive lifecycle from analysis and review state
7. docs(gate): record RC2 Gate B
8. feat(package): persist immutable complete source snapshots
9. fix(migrations): apply migrations atomically
10. fix(rebuild): restore exact reviewed evidence state
11. feat(database): compare canonical database states
12. docs(gate): record RC2 Gate C
13. fix(verify): execute isolated behavioral checks
14. test(e2e): enforce complete public CLI lifecycle
15. test(golden): add bilingual fidelity evaluation
16. test(deepseek): add opt-in live smoke
17. docs(gate): record RC2 Gate D
18. ci: add quality and offline verification workflow
19. docs(rc2): update README execution log and completion report
```

仓库卫生通过 amend 清理当前 HEAD，不制造一个包含数万个虚拟环境删除记录的普通 commit。

---

# 8. OpenCode 启动 Prompt

```text
严格执行：

@AGENTS.md
@plan/ROUND1_1_RC2_NEXT_STAGE_PLAN_FROM_EF2926E.md
@docs/plans/ROUND1_1_RC2_EXECUTION_LOG.md

唯一工作分支：
fix/round1.1-rc2-hardening

当前起点：
ef2926e7f5f8171048340c7fd29111b776730980

先执行 H00-H03。
第一优先级是清除误提交的 .venv-rc2，amend 当前 HEAD，
使用 force-with-lease 更新远程并验证远程不再跟踪虚拟环境。

然后严格执行：
B00-B05 → Gate B
C01-C04 → Gate C
D01-D04 → Gate D
E01-E06

不得新建 coding/review 分支。
Review 使用固定 tag。
所有 plan、log、review 资料和整改继续放在当前工作分支。

每个 FIX：
失败测试 → 修改实现 → focused tests → ruff → mypy
→ execution log → git diff → commit → push。

不得修改核心断言迁就实现。
不得吞掉 migration/rebuild 异常。
不得使用 INSERT OR IGNORE 恢复状态。
不得生成新业务 ID。
不得提前宣布 PASS。

OpenCode step limit 停止前必须更新：
NEXT_TASK
NEXT_COMMAND
当前 commit
测试结果
剩余失败节点。
```
