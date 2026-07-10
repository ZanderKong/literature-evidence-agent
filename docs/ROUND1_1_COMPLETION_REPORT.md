# Round 1.1 Completion Report

> **结论：CONDITIONAL PASS**  
> 日期：2026-07-10  
> 基线：`6f216aa` → 修复分支 `fix/round1.1-remediation`

## 1. 修复范围

基于 Round 1 Review（10 个 P0 Findings），完成 15/18 FIX。

### 已修复的 P0 Findings

| Finding | 状态 | FIX |
|---------|------|-----|
| F001 verify 硬编码 PASS | ✅ fixed | FIX 14 |
| F002 缺少 analyse | ✅ fixed | FIX 02-03 |
| F003 claims 不持久化 | ✅ fixed | FIX 04 |
| F004 review 空包 | ✅ fixed | FIX 06 |
| F005 rebuild 假重建 | ✅ fixed | FIX 11 |
| F006 E2E 空白 PDF | ✅ fixed | FIX 12-13 |
| F008 执行日志虚高 | ✅ fixed | FIX 17 |
| F018 DeepSeek 不解析 | ✅ fixed | FIX 01 |
| F019 FTS 静默吞错 | ✅ fixed | FIX 08 |

### 未完成的 Findings

| Finding | 状态 |
|---------|------|
| F007 Golden Set 完整标注 | ⚠️ partial — 基础框架完成，指标需人工 review |
| F009 编辑重校验 | ✅ fixed (FIX 07) |
| F010 幂等性 | ✅ fixed (FIX 07) |

## 2. 验证结果

```bash
ruff check .          # ✅ All checks passed!
python -m mypy src    # ✅ Success (37 source files)
pytest -q             # ✅ 122 passed

# 真实 E2E
tests/e2e/test_real_pipeline.py::test_real_e2e_pipeline  PASSED
tests/e2e/test_real_pipeline.py::test_real_e2e_export     PASSED
```

## 3. CLI 命令

```
evidence-agent init
evidence-agent db migrate / check / rebuild-from-packages / reset
evidence-agent task create / show / list
evidence-agent ingest <pdf>
evidence-agent analyse <src> --task <id> --provider mock|deepseek
evidence-agent review export <run> / apply <csv>
evidence-agent query <keywords>
evidence-agent source-show / claim-show / run-show
evidence-agent export-source <src>
evidence-agent verify --round-name round1
```

## 4. 已知限制

- DeepSeek Provider 未用真实 API 端到端测试（需 Key + 网络）
- Golden Set claim_type_accuracy 和 hedging_preservation 需人工判读
- PDF 解析仅支持文字型 PDF（不支持扫描版 OCR）
- 不支持复杂双栏、公式和表格提取

## 5. 下一轮建议

- 真实 DeepSeek API 端到端测试
- Golden Set 完整人工标注
- 扫描版 PDF OCR 支持
- 在线文献检索

---

*Round 1.1 由 Craft Agent 于 2026-07-10 执行*
