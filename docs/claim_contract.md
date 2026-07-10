# Claim Contract — 文献证据主张数据合同

> 版本：v1.0
> 日期：2026-07-10

## 1. 核心概念

### 1.1 主张 (Claim) 的定义

一条主张是来源文献中能够独立表达的陈述，包括但不限于：

| 类型 | 说明 | 示例 |
|------|------|------|
| `background_statement` | 作者引用的背景知识 | "HP-β-CD is widely used as a solubilizing agent" |
| `method_statement` | 作者描述的方法步骤 | "Samples were prepared by solvent evaporation method" |
| `reported_observation` | 作者报告的观察 | "A color change from yellow to red was observed" |
| `reported_result` | 作者报告的实验结果 | "The solubility increased by 3.2-fold" |
| `author_interpretation` | 作者对结果的解释 | "This suggests that the inclusion complex was formed" |
| `author_conclusion` | 作者的结论 | "HP-β-CD significantly enhanced the dissolution rate" |
| `author_hypothesis` | 作者提出的假设 | "The enhanced solubility may be due to hydrogen bonding" |
| `author_limitation` | 作者声明的限制 | "The study was limited to in vitro conditions" |
| `future_work` | 作者建议的后续研究 | "Further in vivo studies are needed" |

### 1.2 外部资料身份

所有文献来源中的主张必须始终保持以下身份标记：

```text
origin_scope = "external"
scientific_verification_status = "unverified"
```

人工审核「批准」只表示记录忠实于来源，不表示科学结论已被内部验证。

---

## 2. 主张数据模型

### 2.1 完整字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `claim_id` | string | ✅ | 唯一标识，格式 `CLM-xxxxxx` |
| `source_id` | string | ✅ | 来源标识 |
| `task_id` | string | ❌ | 关联研究任务 |
| `claim_type` | enum | ✅ | 主张类型（见 1.1） |
| `source_quote` | string | ✅ | 原文中的连续文本 |
| `faithful_paraphrase` | string | ✅ | 忠实转述 |
| `evidence_basis_description` | string | ✅ | 作者依据哪些实验/图/表 |
| `scope_description` | string | ❌ | 适用样品、条件或范围 |
| `author_hedging` | string | ❌ | 作者限定词（suggests, may, possibly...） |
| `origin_scope` | enum | ✅ | 固定为 `external` |
| `record_review_status` | enum | ✅ | pending/approved/approved_with_edits/rejected |
| `scientific_verification_status` | enum | ✅ | 固定为 `unverified` |
| `quote_match_status` | enum | ✅ | exact/normalised/ambiguous/not_found |
| `created_by_run_id` | string | ✅ | 处理运行 ID |
| `created_at` | string | ✅ | ISO 8601 |
| `updated_at` | string | ✅ | ISO 8601 |

### 2.2 定位模型 (Claim Locator)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `locator_id` | string | ✅ | 唯一标识 |
| `claim_id` | string | ✅ | 关联主张 |
| `section_id` | string | ❌ | 关联章节 |
| `page` | int | ❌ | 页码 |
| `paragraph_index` | int | ❌ | 段落索引 |
| `figure_label` | string | ❌ | 图号（如 "Figure 3"） |
| `table_label` | string | ❌ | 表号（如 "Table 2"） |
| `supplementary_label` | string | ❌ | 补充材料标签 |
| `character_start` | int | ❌ | 字符起始位置 |
| `character_end` | int | ❌ | 字符结束位置 |
| `locator_confidence` | enum | ✅ | high/medium/low |

---

## 3. 完整示例（有效主张）

### 3.1 `reported_result`

```json
{
  "claim_type": "reported_result",
  "source_quote": "The solubility of curcumin increased from 0.6 μg/mL to 3.2 mg/mL upon complexation with HP-β-CD at a 1:2 molar ratio.",
  "faithful_paraphrase": "姜黄素与 HP-β-CD 以 1:2 摩尔比络合后，溶解度从 0.6 μg/mL 增加至 3.2 mg/mL。",
  "evidence_basis_description": "作者通过相溶解度实验测量，数据见 Table 1 和 Figure 2A。",
  "scope_description": "适用于姜黄素与 HP-β-CD 在水溶液体系中 25°C 条件下的络合。",
  "author_hedging": null,
  "locator_hint": {
    "page": 5,
    "section_heading": "Results and Discussion",
    "figure_label": "Figure 2A",
    "table_label": "Table 1"
  },
  "entities": [
    {"entity_type": "material", "display_name": "curcumin", "role": "subject"},
    {"entity_type": "material", "display_name": "HP-β-CD", "role": "material"},
    {"entity_type": "property", "display_name": "solubility", "role": "property"}
  ]
}
```

### 3.2 `author_interpretation`

```json
{
  "claim_type": "author_interpretation",
  "source_quote": "This suggests that the aromatic ring of curcumin is deeply inserted into the hydrophobic cavity of HP-β-CD, while the phenolic groups form hydrogen bonds with the rim hydroxyls.",
  "faithful_paraphrase": "作者提出姜黄素芳香环深深插入 HP-β-CD 疏水空腔，同时酚羟基与环糊精边缘羟基形成氢键。",
  "evidence_basis_description": "基于 FT-IR 光谱（Figure 3）、1H NMR 化学位移变化（Figure 4）和分子对接模拟（Figure 5）推断。",
  "scope_description": "适用于水溶液中的 HP-β-CD/姜黄素包含物体系。",
  "author_hedging": "suggests",
  "locator_hint": {"page": 7, "section_heading": "Results and Discussion"},
  "entities": [
    {"entity_type": "material", "display_name": "curcumin", "role": "subject"},
    {"entity_type": "material", "display_name": "HP-β-CD", "role": "material"},
    {"entity_type": "method", "display_name": "FT-IR", "role": "method"},
    {"entity_type": "method", "display_name": "1H NMR", "role": "method"}
  ]
}
```

### 3.3 `author_limitation`

```json
{
  "claim_type": "author_limitation",
  "source_quote": "However, the in vitro dissolution results may not directly predict in vivo performance, and further pharmacokinetic studies are warranted.",
  "faithful_paraphrase": "作者指出体外溶出结果可能无法直接预测体内表现，需要进一步的药代动力学研究。",
  "evidence_basis_description": "作者基于常规认知提出的谨慎说明，无特定实验支持。",
  "scope_description": null,
  "author_hedging": "may not",
  "locator_hint": {"page": 12, "section_heading": "Conclusion"},
  "entities": [
    {"entity_type": "property", "display_name": "dissolution", "role": "property"}
  ]
}
```

---

## 4. 无效示例

### 4.1 缺少原文引用（❌ source_quote 为空）

### 4.2 原文不在资料中（❌ quote_match_status = not_found）

### 4.3 把推测改写为确定事实

原文: "The data may indicate an entropic contribution to the binding."

错误转述: "结合过程由熵驱动。"

❌ **失败原因**: 丢失 author_hedging "may indicate"

---

## 5. 忠实转述规则

1. 保留限定语气：suggests、may、possibly 等不得删除
2. 保留不确定性："may be due to" ≠ "is caused by"
3. 保留条件范围：in vitro、at pH 7.4 等
4. 区分类别：观察/结果/解释/结论 不得混淆
5. 不补充信息：不得添加原文不存在的实验条件
6. 不越界推断：综述转述 ≠ 原始实验
7. 不编造数据：不得写入图表未明确报告的数值

---

## 6. 原文匹配等级

| 等级 | 可否复核 |
|------|----------|
| `exact` | ✅ |
| `normalised` | ✅ |
| `ambiguous` | ❌ |
| `not_found` | ❌ |

---

## 7. 进入正式查询的要求

- `record_review_status ∈ {approved, approved_with_edits}`
- `quote_match_status ∈ {exact, normalised}`
- 定位中 page 非空或 section_id 非空
- `origin_scope = "external"`
- `scientific_verification_status = "unverified"`
