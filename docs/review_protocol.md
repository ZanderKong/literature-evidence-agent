# Review Protocol — 人工复核协议

> 版本：v1.0 | 日期：2026-07-10

## 1. 复核目标

人工复核只验证两个问题：
1. **忠实性**：LLM 提取的主张是否忠实于原文？
2. **定位正确性**：页码、章节、图号是否正确？

**不验证**：作者主张的科学正确性、实验可复现性、统计方法合理性。

## 2. 复核决策

| 决策 | 含义 | 后续行为 |
|------|------|----------|
| `approve` | 忠实 + 定位正确 | 进入证据库，可检索 |
| `approve_with_edits` | 基本正确，需修正 | 编辑后进入证据库 |
| `reject` | 不忠实或不应提取 | 保留但不检索 |
| `mark_missing` | 遗漏重要主张 | 记录供补充 |
| `needs_followup` | 需进一步确认 | 暂时搁置 |

## 3. 复核包文件

```text
workspace/external_evidence/review/RUN-xxxxxx/
├── review_packet.md
├── review_packet.html
├── claims_for_review.csv
├── claims_for_review.jsonl
├── failed_locators.jsonl
└── review_instructions.md
```

## 4. CSV 列定义

```csv
claim_id,decision,edited_source_quote,edited_faithful_paraphrase,
edited_evidence_basis_description,edited_claim_type,edited_page,
edited_section,review_reason,reviewer
```

## 5. 应用复核决定流程

1. 读取复核 CSV → 校验
2. 对 `approve_with_edits`：重新匹配 quote + 重校验定位
3. 写入 `review_decisions` + `claim_revisions`
4. 更新 `source_claims.record_review_status`
5. 批准记录 → FTS 索引
6. 全程事务保护

## 6. 重要警告

> ⚠️ **"approved" ≠ "科学验证"**
>
> 批准只表示记录忠实反映作者陈述，科学性未经内部验证。
> 所有查询结果和导出必须标注："外部来源，科学状态：未经内部验证"
