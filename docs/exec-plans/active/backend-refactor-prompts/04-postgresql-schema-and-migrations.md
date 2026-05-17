# Prompt 04：PostgreSQL Schema、分区、索引与 SQLx Migration

```text
/goal
你是 Codex 子代理：PostgreSQL schema 和 migration 负责人。工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
把财务核心事实源设计为 PostgreSQL schema，并建立可运行、可演进、低耦合的 SQLx migration。不要实现所有业务逻辑，只完成 schema/migration 的生产级基础。

必须读取：
- AGENTS.md
- docs/architecture/backend-refactor/data-model-and-read-models.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/exec-plans/active/backend-refactor-inventory.md，如果存在
- backend/src/fin_ops_platform/domain/
- backend/src/fin_ops_platform/services/state_store.py

设计原则：
- app schema 保存核心事实。
- read_model schema 保存可重建读模型。
- job schema 保存 outbox、任务和 worker 状态。
- audit schema 保存审计事件。
- staging schema 保存迁移和导入中间结果。
- 金额必须用 numeric，不用 float。
- 常用筛选字段必须拆列，不把核心查询字段只塞进 jsonb。
- migration 只前进，不修改已经发布的 migration。

任务拆分：
1. Rust/SQLx migration 结构
   - 检查是否已有 Rust workspace。
   - 若无，和 Axum skeleton 模块协调，不冲突。
   - 建立 migrations 目录或 Axum crate 下的 migrations。

2. 基础 schema migration
   - 创建 schema app/read_model/job/audit/staging。
   - 创建扩展 pgcrypto、pg_trgm、btree_gin。

3. 核心事实表 migration
   - import_batches、import_files、file_objects。
   - bank_transactions。
   - invoices。
   - oa_applications、oa_application_items、oa_attachments。
   - reconciliation_cases、reconciliation_case_rows。
   - workbench_row_overrides、workbench_exception_cases。
   - no_oa_bank_batches、turnover_relations。

4. job/audit/read model migration
   - job.outbox_events、worker_tasks、worker_attempts、dead_letters。
   - audit.events。
   - read_model.workbench_rows、workbench_snapshots。
   - read_model.search_index_rows。
   - read_model.cost_statistics_read_models、tax_offset_read_models。

5. 分区和索引
   - bank_transactions 按 txn_month。
   - invoices 按 invoice_month。
   - oa_applications 按 approved_month 或 source_updated_month。
   - workbench_rows/search_index_rows 按 scope_month。
   - pg_trgm/GIN 只用于搜索字段。
   - 组合索引贴近实际查询。

6. 文档
   - 新建 docs/architecture/backend-refactor/postgresql-schema-notes.md。
   - 说明每张表归属、约束、索引、分区、迁移顺序。

验收：
- 空库可以执行 migration。
- migration 不依赖生产数据。
- 表边界清楚，没有把所有模块揉成一个大表。
- 有唯一约束、外键或业务约束说明。
- 有关键查询 EXPLAIN 验证计划说明。
- 如无法执行空库 migration，明确阻塞原因。
```

