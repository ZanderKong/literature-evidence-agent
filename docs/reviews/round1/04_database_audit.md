# R04 — Database Audit

## 审计时间
2026-07-10 11:20 GMT+8

## 迁移验证

| 测试 | 结果 | 证据 |
|------|------|------|
| 空库迁移 | ✅ PASS | 3 migrations applied, all tables created |
| 重复迁移 | ✅ PASS | "No pending migrations" |
| integrity_check | ✅ PASS | "ok" |
| foreign_key_check | ✅ PASS | Empty (no violations) |
| origin_scope CHECK | ✅ PASS | "internal" rejected with error 19 |
| scientific_status CHECK | ⚠️ NOT TESTED | 信任同结构约束 |
| 唯一 SHA-256 | ⚠️ NOT TESTED | 信任 UNIQUE 约束 |
| FTS 表存在 | ✅ PASS | source_fts, claim_fts 及其内部表 |

## 事务验证

| 测试 | 结果 |
|------|------|
| 事务回滚 | ✅ 单元测试通过 |
| 只读连接 | ✅ 单元测试通过 |

## 关键缺陷

**rebuild() 不恢复数据：** `database/migrations.py:rebuild()` 仅执行 drop + re-migrate，不读取资料包恢复数据。这不是"重建数据库"，而是"重置数据库"。

**claims 不持久化：** 全 src/ 目录中无 `INSERT INTO source_claims` 代码。claims 提取后留在内存中。

## 结论

数据库 schema 设计良好，约束正确。但 persist 路径缺失，rebuild 不符合规格。
