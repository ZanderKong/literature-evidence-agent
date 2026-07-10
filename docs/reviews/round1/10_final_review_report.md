# Round 1 Final Review Report

> **结论：FAIL**  
> **审查日期：2026-07-10 11:11–11:30 GMT+8**  
> **审查基线：** `6f216aa` (review/round1-audit)

---

## 1. 审查基线

| Item | Value |
|------|-------|
| Commit | `6f216aaa3886d31c4f5a345f65ecb0a22f26ea38` |
| Branch | `review/round1-audit` |
| Python | 3.11.15 |
| SQLite | 3.50.4 |
| OS | macOS 14.5 arm64 |

---

## 2. Hard Gate 结果

| # | Hard Gate | 结果 | 证据 |
|---|-----------|------|------|
| 1 | 真实 Provider 无法产生 claims | **⚠️ 未验证** | 无 API Key，DeepSeekProvider 未测试 |
| 2 | 没有正式 analyse 工作流入口 | **❌ FAIL** | CLI 无 `analyse` 命令 (F002) |
| 3 | claims 和 locators 没有写入数据库 | **❌ FAIL** | 0 个 `INSERT INTO source_claims` (F003) |
| 4 | review export 生成空包 | **❌ FAIL** | 传入 `validated_claims=[]` (F004) |
| 5 | 人工编辑后不重新校验 quote | **❌ FAIL** | `apply_review_csv` 无重新匹配 (F009) |
| 6 | FTS 查询异常被静默吞掉 | **⚠️ 可疑** | `search_claims` 用 `except: pass` |
| 7 | rebuild 无法从资料包恢复记录 | **❌ FAIL** | 仅 drop + re-migrate (F005) |
| 8 | verify 含硬编码 PASS | **❌ FAIL** | 5/7 项硬编码 (F001) |
| 9 | E2E 使用空白 PDF | **❌ FAIL** | 空白页，无真实主张 (F006) |
| 10 | Golden Set 不存在 | **❌ FAIL** | 无标注/脚本 (F007) |
| 11 | 外部主张可写入内部结构 | **✅ PASS** | CHECK 约束有效 |
| 12 | 完成报告虚高 | **❌ FAIL** | 执行日志标记全完成 (F008) |

**Hard Gate 通过率：1/12**

---

## 3. 执行命令记录

### 干净环境安装 ✅

```bash
$ git clone ... && cd repo
$ python3.11 -m venv .venv-review && source .venv-review/bin/activate
$ pip install -e ".[dev]"
# ✅ 安装成功
```

### 代码质量 ✅

```bash
$ ruff check .        # ✅ All checks passed!
$ python -m mypy src  # ✅ Success, no issues
$ pytest -q           # ✅ 106 passed
```

### 数据库审计 ✅

```bash
$ evidence-agent db migrate   # ✅ 3 migrations applied
$ evidence-agent db migrate   # ✅ 幂等: No pending migrations
$ PRAGMA integrity_check      # ✅ ok
$ PRAGMA foreign_key_check    # ✅ empty (no violations)
# SQL: origin_scope='internal' → ✅ CHECK constraint failed (正确拒绝)
```

### verify round1 — 硬编码 PASS ❌

```bash
$ evidence-agent verify --round-name round1
database_integrity=PASS     # ✅ 实际检查
ingest_idempotency=PASS     # ⚠️ 仅检查表存在
quote_traceability=PASS     # ❌ 硬编码
review_workflow=PASS        # ❌ 硬编码
fts_search=PASS             # ❌ 硬编码
database_rebuild=PASS       # ❌ 硬编码
external_data_isolation=PASS # ❌ 硬编码
ROUND1_VERIFICATION=PASS    # ❌ 基于硬编码
Exit: 0
```

---

## 4. P0 Findings（阻断主闭环）

| ID | 标题 | 影响 |
|----|------|------|
| F001 | verify 含 5 个硬编码 PASS | 验收不可信 |
| F002 | 缺少 analyse 命令 | 没有完整工作流入口 |
| F003 | 主张从未写入数据库 | 核心闭环断裂 |
| F004 | review export 传入空列表 | 复核包无内容 |
| F005 | 重建仅 drop + re-migrate | 无法恢复数据 |
| F006 | E2E 使用空白 PDF | 虚假闭环 |
| F007 | Golden Set 不存在 | 无法评估忠实度 |
| F008 | 执行日志虚高 | 虚假完成报告 |

---

## 5. P1 Findings（数据可信度风险）

| ID | 标题 |
|----|------|
| F009 | 编辑后不重新校验 quote |
| F010 | 重复应用幂等性未验证 |
| F011 | locator 校验不完整 |

---

## 6. P2 Findings（稳定性与覆盖）

| ID | 标题 |
|----|------|
| F012 | 缺少 source show/claim show |
| F013 | 无 processing_run 记录 |
| F014 | review/search/export 无测试 |
| F015 | PDF fixture 无真实内容 |

---

## 7. P3 Findings（文档与维护）

| ID | 标题 |
|----|------|
| F016 | README 与真实命令不一致 |
| F017 | 12 个计划模块缺失 |

---

## 8. 总结

**最终结论：FAIL**

Round 1 项目骨架和基础模块（数据库、PDF 解析、Provider）已具备，但存在 8 个 P0 阻断问题：

1. **verify 硬编码 PASS** — 最关键问题，验收基础不可信
2. **analyse 工作流不存在** — 用户无法通过单一命令完成完整流程
3. **claims 不持久化** — 提取结果丢失
4. **review export 空数据** — 人工复核链路断裂
5. **rebuild 不恢复数据** — 无法灾难恢复
6. **E2E 空白 PDF** — 测试不证明能力
7. **Golden Set 缺失** — 无法评估提取质量
8. **执行日志虚高** — 完成报告不诚实

**代码质量（ruff/mypy）和测试数量（106 passed）不应被视为完成证据。**

---

## 9. 修复优先级建议

```
P0-1: 实现 analyse 工作流 + claims 持久化 (F002 + F003)
P0-2: 修复 verify 假闭环 (F001)
P0-3: review export 连接数据库 (F004)
P0-4: 实现真实数据库重建 (F005)
P0-5: 替换 E2E 为真实内容 PDF (F006)
P0-6: review 编辑后重新校验 (F009)
P0-7: 创建 Golden Set (F007)
P0-8: 更新执行日志为真实状态 (F008)
P1-P3: 补全校验/测试/文档
```

---

*审查由 Craft Agent 于 2026-07-10 执行*  
*不修改业务代码，仅生成审查产物*
