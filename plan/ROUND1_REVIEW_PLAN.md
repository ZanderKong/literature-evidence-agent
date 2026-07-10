# Literature Evidence Agent — Round 1 Review 计划

> 建议文件名：`docs/reviews/ROUND1_REVIEW_PLAN.md`  
> Review 对象：`ZanderKong/literature-evidence-agent` 当前 `main` 分支  
> Review 目标：判断 Round 1 是否真正形成「本地 PDF → 作者主张 → 原文定位 → 人工复核 → 数据库存储 → 检索与恢复」闭环。  
> 核心原则：先审查，后修复；没有真实命令、输出和可复现证据，不得标记通过。

---

## 一、Review 结论规则

Review 最终只能给出以下三种结论：

- **PASS**：所有 Hard Gate 通过，主要验收项有真实运行证据。
- **CONDITIONAL PASS**：Hard Gate 全部通过，只剩不影响主闭环的 P2、P3 问题。
- **FAIL**：任一 Hard Gate 失败，或关键结果依赖硬编码、空数据、Mock 假闭环。

当前测试数量、提交信息和执行日志只能作为线索，不能直接作为完成证据。

---

## 二、严重度定义

### P0 — 阻断主闭环

满足任一条件：

- 用户无法完成核心流程。
- 真实模型路径无法产生可用结果。
- 验收脚本硬编码 PASS。
- 数据未真正写入数据库。
- 数据恢复会丢失资料或审核结果。
- 系统宣称完成，但实际关键能力不存在。

### P1 — 数据可信度或审核可信度风险

例如：

- 人工编辑后不重新校验原文。
- 重复应用审核决定产生重复记录。
- 定位信息错误仍可批准。
- FTS 索引与数据库状态不一致。
- 主张 ID 不稳定或可能冲突。

### P2 — 稳定性、易用性和测试覆盖不足

例如：

- CLI 信息不完整。
- 错误被静默吞掉。
- 复核包缺少上下文或链接。
- 复杂 PDF 解析效果较差。
- 测试夹具过于简单。

### P3 — 文档、命名和维护性问题

例如：

- README 与真实命令不一致。
- 完成日志状态虚高。
- 注释过时。
- 文件组织和命名不统一。

---

## 三、Review 产物

在仓库中建立：

```text
docs/reviews/round1/
├── 00_review_scope.md
├── 01_baseline_run.md
├── 02_static_code_review.md
├── 03_runtime_review.md
├── 04_database_audit.md
├── 05_workflow_audit.md
├── 06_scientific_content_review.md
├── 07_test_gap_matrix.csv
├── 08_acceptance_matrix.csv
├── 09_findings.csv
├── 10_final_review_report.md
└── evidence/
    ├── command_logs/
    ├── database_snapshots/
    ├── review_packets/
    ├── exported_records/
    └── screenshots/
```

`09_findings.csv` 至少包含：

```text
finding_id
severity
module
title
expected
actual
reproduction_steps
evidence_path
file_and_line
impact
recommended_fix
verification_method
status
```

---

# 四、Review 执行阶段

## R00：冻结基线

### 目标

确保整个 Review 对应一个明确 commit，避免边审边改导致证据失效。

### 执行方法

1. 记录当前分支和 commit SHA。
2. 确认工作区是否干净。
3. 创建 Review 分支，例如：
   `review/round1-audit`
4. 保存仓库文件清单。
5. 记录 Python、SQLite、操作系统和依赖版本。
6. Review 阶段不修改业务代码，只允许新增 `docs/reviews/` 下的审查文件。

### 命令

```bash
git status --short
git branch --show-current
git rev-parse HEAD
python --version
python -c "import sqlite3; print(sqlite3.sqlite_version)"
find . -maxdepth 3 -type f | sort
```

### 完成判定

- [ ] commit SHA 已记录。
- [ ] Review 分支已创建。
- [ ] 环境版本已记录。
- [ ] 业务代码未被修改。

---

## R01：计划与实现映射

### 目标

逐项核对原 Round 1 Plan 的 TASK 00 至 TASK 16。

### 执行方法

建立 `08_acceptance_matrix.csv`，每个原任务记录：

```text
task_id
planned_output
actual_output
code_exists
test_exists
runtime_verified
documentation_verified
status
evidence
```

状态只能是：

```text
verified
partially_verified
not_verified
missing
misrepresented
```

### 重点检查

- TASK 13「数据库重建」是否从资料包恢复数据。
- TASK 14「Golden Set」是否存在真实标注和指标。
- TASK 15 是否真的走通审核、搜索、导出和重建。
- TASK 16 是否存在诚实的完成报告。

### 完成判定

- [ ] 17 个 TASK 均有独立结论。
- [ ] 「代码存在」和「能力完成」分开判定。
- [ ] 所有完成判断都有文件或运行证据。

---

## R02：干净环境基线运行

### 目标

验证项目不依赖开发机器上的隐式环境。

### 执行方法

1. 在新目录 clone 仓库。
2. 创建全新 Python 3.11 虚拟环境。
3. 安装项目。
4. 运行代码检查、类型检查和测试。
5. 保存完整输出和退出码。
6. 不使用原开发目录的数据库或 workspace。

pytest 官方建议在隔离虚拟环境中安装项目，并让测试针对实际安装的包运行；Review 应采用这一方式，而不是只依赖仓库根目录的 `pythonpath`。

### 命令

```bash
python3.11 -m venv .venv-review
source .venv-review/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

ruff check .
python -m mypy src
pytest -q
evidence-agent --help
```

### 完成判定

- [ ] 安装成功。
- [ ] 所有命令退出码已记录。
- [ ] 测试数量和耗时已记录。
- [ ] 警告没有被忽略。
- [ ] 测试失败未通过修改测试来掩盖。

---

## R03：静态架构审查

### 目标

确认架构是否真的支持端到端流程。

### 检查对象

- CLI
- workflow 或 application service
- Provider
- extraction
- validators
- repositories
- review
- FTS
- rebuild
- migrations

### 必答问题

1. 哪个函数负责完整分析流程？
2. 哪个命令创建研究任务？
3. 哪个命令启动主张提取？
4. 模型响应在哪里解析为 claims？
5. claims 在哪里写入数据库？
6. locators 在哪里写入数据库？
7. processing run 在哪里创建和结束？
8. review export 如何按 run_id 读取真实数据？
9. review apply 后如何更新 FTS？
10. rebuild 如何从资料包恢复数据库？

### 完成判定

- [ ] 画出真实调用图，不依据 README 推测。
- [ ] 每个关键节点有实际代码入口。
- [ ] 找不到入口的能力标为 missing。
- [ ] 不接受「未来可以接入」作为完成证据。

---

## R04：数据库和迁移审查

### 目标

验证数据库约束、事务、幂等性和恢复能力。

### 执行方法

1. 从空库运行全部迁移。
2. 重复运行迁移。
3. 执行：
   - `PRAGMA integrity_check`
   - `PRAGMA foreign_key_check`
4. 尝试写入非法 `origin_scope`。
5. 尝试写入非法审核状态。
6. 测试重复 SHA-256。
7. 测试删除 source 后的级联行为。
8. 测试 review 决定事务回滚。
9. 检查数据库 schema 与文档是否一致。
10. 建立一份含真实 source、claim、locator、review 的数据库快照。

### Hard Gate

- 数据库完整性必须通过。
- 外部身份必须由数据库约束保证。
- 审核状态和科学验证状态必须分离。
- 重建不得只生成空库。

### 完成判定

- [ ] 所有约束均真实触发。
- [ ] 事务失败不会部分写入。
- [ ] 数据库快照可重复创建。
- [ ] 恢复后关键 ID 和状态一致。

---

## R05：PDF 导入和解析审查

### 测试资料

至少准备：

1. 一篇正常英文文字型论文。
2. 一篇正常中文文字型论文。
3. 一篇双栏论文。
4. 一篇文本密度低或扫描版 PDF。
5. 一篇包含连字符断行、图表编号和上下标的论文。

### 检查项

- 文件哈希和重复导入。
- 页码映射。
- 章节识别。
- 双栏阅读顺序。
- 图表编号识别。
- 低文本密度阻断。
- 解析结果是否写入数据库或资料包。
- 解析器版本是否动态记录，不能硬编码错误版本。

### 完成判定

- [ ] 重复导入不产生重复 source。
- [ ] 页码抽查正确。
- [ ] 扫描版不会进入主张提取。
- [ ] 解析限制被明确报告。
- [ ] 解析结果可被后续 workflow 读取。

---

## R06：真实模型和主张提取审查

### 目标

证明真实 Provider 能将模型输出转换为候选主张。

### 两条路径

#### A. Mock 路径

用于稳定回归测试，但 fixture 必须包含与 PDF 原文一致的真实主张。

#### B. DeepSeek 路径

有 API Key 时必须执行。没有 Key 时只能标记 `blocked_external`，不能标记通过。

### 检查项

- 请求 payload 与官方思考模式要求一致。
- JSON 输出被解析为 `claims`。
- 顶层结构错误时执行一次修复。
- 修复失败后明确失败。
- 原始响应、模型名、Prompt 版本、输入输出哈希被保存。
- 真实 Provider 不能返回固定空 claims。
- `task_focused` 和 `source_complete` 有实际差异。

### Hard Gate

真实或可验证的 Provider 路径必须产生至少一条与测试 PDF 对应的候选主张。

### 完成判定

- [ ] 真实响应成功解析。
- [ ] 非法 JSON 测试通过。
- [ ] 无 API Key 行为明确。
- [ ] Provider 失败不会被当作零主张成功。
- [ ] 模型输出可追溯。

---

## R07：原文、定位和科学边界审查

### 目标

确认主张记录忠实于来源。

### 测试场景

- 精确匹配。
- PDF 换行。
- 连字符断行。
- Unicode 差异。
- 同一句在多页重复。
- quote 完全不存在。
- 作者使用 `may`、`suggests`、`possibly`。
- 作者观察与作者解释同时存在。
- Agent 擅自补充机理或条件。

### 检查项

- quote 匹配状态真实。
- 规范化后的字符位置能否回映到原文。
- 多处匹配是否标为 ambiguous。
- 页码错误能否被修正或阻断。
- 作者限定词是否保留。
- 外部主张不会升级为内部事实。
- claim ID 是否跨来源、跨运行唯一稳定。

### Hard Gate

所有进入复核包的普通记录必须：

- quote 匹配通过；
- 有页码或章节；
- 外部身份明确；
- 科学状态为 unverified。

---

## R08：主工作流和持久化审查

### 目标

证明用户可以通过公开入口完成完整分析。

### 应存在的流程

```text
create task
→ ingest
→ parse
→ analyse
→ extract
→ validate
→ persist claims and locators
→ create processing run
→ generate review packet
```

### 执行方法

只使用 CLI 或正式应用入口，不允许在测试中手工逐个调用内部函数代替产品流程。

### 数据库检查

流程结束后验证：

```text
research_tasks > 0
processing_runs > 0
sources > 0
source_sections > 0
source_claims > 0
claim_locators > 0
```

### Hard Gate

- 存在正式 `analyse` 或等价入口。
- 主张和定位真正写入数据库。
- processing run 状态完整。
- 复核包不是由空列表生成。

---

## R09：人工复核流程审查

### 检查项

- review export 按 run_id 读取真实 pending claims。
- CSV 包含足够的审查信息。
- HTML 包含原文上下文。
- 原始 PDF 路径和页码可访问。
- approve_with_edits 后重新校验 quote、locator 和 claim type。
- 缺少 claim_id 时整批失败或明确阻断。
- 重复应用同一审核文件保持幂等。
- rejected 记录保留。
- revision 历史完整。
- 只有 approved 记录进入正式搜索。

### Hard Gate

人工编辑后的 quote 如果不存在于来源中，必须拒绝应用。

---

## R10：FTS、查询和导出审查

SQLite FTS5 是独立的全文索引机制；Review 要验证索引与正式表状态同步，而不能只验证 FTS 表存在。

### 检查项

- 查询路径没有在只读连接中执行写操作。
- approve 后可检索。
- pending 和 rejected 默认不可检索。
- approved_with_edits 使用编辑后内容。
- reject 已批准记录后，旧索引被移除。
- FTS rebuild 前后结果一致。
- 中文和英文查询。
- 特殊字符和非法 FTS 表达式。
- 查询异常不能被空结果静默吞掉。
- 导出默认只包含已批准记录。
- 导出包含来源身份、页码和科学状态。

### Hard Gate

查询批准记录必须真实返回结果，且数据库异常不能伪装成「No results」。

---

## R11：数据库恢复审查

### 目标

验证资料包是可恢复的事实来源。

### 执行方法

1. 完成一篇论文的完整分析和审核。
2. 保存原数据库摘要：
   - source IDs
   - claim IDs
   - review statuses
   - search results
3. 将原数据库移走。
4. 从资料包创建全新数据库。
5. 比较恢复前后结果。

### Hard Gate

以下集合必须一致：

- source_id
- approved claim_id
- locator
- review status
- FTS 关键查询结果

单纯删除表并重新执行 migration 只能称为「重置数据库」，不能称为「重建数据库」。

---

## R12：测试质量和 Golden Set 审查

### 目标

判断测试是否证明产品能力，而不只是函数不会报错。

### 检查项

- E2E fixture 不能是空白 PDF。
- E2E 必须产生至少一条真实主张。
- E2E 必须覆盖：
  - persistence
  - review apply
  - FTS
  - export
  - rebuild
- 断言不能只检查 `isinstance(list)`。
- `blocks_processed >= 0` 等无意义断言应删除。
- 错误路径必须测试。
- 真实完成项与测试覆盖建立映射。
- Golden Set 至少包含中英文、限定词、解释、局限和重复 quote。

### Golden Set 指标

- 无依据批准主张率：0%
- 批准主张 quote 匹配率：100%
- 批准主张定位完整率：100%
- 限定词保留率：不低于 95%
- 核心主张召回率：建议不低于 80%
- 主张类型准确率：建议不低于 85%

### 完成判定

- [ ] Golden Set 有真实标注。
- [ ] 指标由脚本计算。
- [ ] 每个失败样本有归因。
- [ ] 测试数量不作为主要质量指标。

---

## R13：`verify round1` 真实性审查

### 目标

清除所有硬编码 PASS。

### 检查方法

逐条追踪每个输出：

```text
database_integrity
ingest_idempotency
quote_traceability
review_workflow
fts_search
database_rebuild
external_data_isolation
```

每一项必须：

1. 调用实际验证函数；
2. 产生真实输入；
3. 检查真实输出；
4. 失败时返回退出码 7；
5. 保存详细错误。

### Hard Gate

源码中不得存在没有对应检查的：

```python
print("xxx=PASS")
```

### 完成判定

- [ ] 人为破坏任一模块后，verify 会 FAIL。
- [ ] 恢复模块后，verify 才会 PASS。
- [ ] verify 在空数据库中不会虚假通过。

---

## R14：安全、隐私和鲁棒性审查

### 检查项

- 仓库无 API Key。
- 日志不打印密钥。
- HTML 对作者原文进行转义，防止文献文本注入 HTML。
- 文件路径不能越过 workspace。
- SQL 查询参数化。
- FTS 输入异常受控。
- 损坏 PDF 不造成残留半成品。
- 模型超时、429 和网络错误有明确状态。
- 用户文献和数据库不应默认提交 Git。
- `.gitignore` 覆盖 workspace、数据库 WAL、日志和私人 PDF。

---

## R15：科学内容人工 Review

### 样本量

第一轮建议人工精审 3 至 5 篇资料，每篇抽查：

- 5 条 reported result
- 5 条 author interpretation
- 2 条 limitation 或 future work
- 所有带强因果措辞的主张
- 所有人工编辑后的主张

### 每条记录判定

```text
quote_correct
paraphrase_faithful
claim_type_correct
hedging_preserved
scope_preserved
evidence_basis_supported
locator_correct
agent_added_analysis
```

### 拒绝条件

- 把作者推测写成确定结论。
- 把相关性写成因果。
- 补充原文未提供的实验条件。
- 证据依据与作者实际论证无关。
- 引用位置错误。
- 把外部主张写成内部事实。

---

# 五、Round 1 Hard Gate

以下任一项失败，最终结论必须为 FAIL：

1. 真实 Provider 无法产生 claims。
2. 没有正式 analyse 工作流入口。
3. claims 和 locators 没有写入数据库。
4. review export 生成空包或不读取 run 数据。
5. 人工编辑后不重新校验 quote。
6. FTS 查询存在只读写入错误或异常被静默吞掉。
7. rebuild 无法从资料包恢复记录。
8. verify 含硬编码 PASS。
9. E2E 使用空白 PDF 且没有真实主张。
10. Golden Set 没有真实数据却被标记完成。
11. 外部主张可能写入内部实验数据结构。
12. 完成报告宣称了没有验证的功能。

---

# 六、最终报告结构

`10_final_review_report.md` 应包含：

```text
1. Review 基线
2. Review 范围
3. 实际执行命令
4. 环境信息
5. 原计划完成度矩阵
6. Hard Gate 结果
7. P0 Findings
8. P1 Findings
9. P2 与 P3 Findings
10. 数据库审查
11. 主工作流审查
12. 科学内容审查
13. 测试可信度审查
14. 文档真实性审查
15. 最终结论
16. Round 1.1 修复优先级
```

每项 Finding 必须包含：

- 可复现步骤。
- 预期结果。
- 实际结果。
- 文件和行号。
- 命令输出或数据库证据。
- 严重度。
- 修复后验收方法。

---

# 七、Review 后的修复顺序

Review 报告确认后再创建 `ROUND1_1_REMEDIATION_PLAN.md`，按以下顺序修复：

```text
P0：真实 Provider 和 analyse 闭环
→ P0：主张持久化和 review export
→ P0：FTS 与 verify
→ P0：资料包恢复数据库
→ P1：人工编辑重新校验和幂等
→ P1：稳定 ID 与 processing run
→ P2：真实 E2E 和 Golden Set
→ P2：复核界面可用性
→ P3：README、执行日志和完成报告
```

每修完一组问题，都必须重新执行对应 Review 用例。不得一次性修完后只运行全部测试。

---

# 八、交给 Review Agent 的执行指令

```text
严格按照 docs/reviews/ROUND1_REVIEW_PLAN.md 审查当前仓库。

第一阶段只做 Review，不修改业务代码。
允许新增 docs/reviews/round1/ 下的审查产物和测试运行证据。

不要相信 README、commit message、执行日志和测试数量本身。
每个完成判断必须来自：
1. 真实代码入口；
2. 真实运行命令；
3. 可复现输出；
4. 数据库或文件产物。

发现问题时写入 09_findings.csv，并按 P0、P1、P2、P3 分类。
任何 Hard Gate 失败，最终结论必须为 FAIL。

Review 完成后生成 10_final_review_report.md。
在报告获得确认前，不要修改业务代码，也不要开始下一轮功能开发。
```
