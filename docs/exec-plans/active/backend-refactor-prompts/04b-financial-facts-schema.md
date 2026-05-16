# Prompt 04B：财务核心事实表 Schema

```text
你是 Codex 子代理：财务核心事实表负责人。

目标：
在 04A 基础上创建 app schema 下的核心事实表，覆盖导入、文件、银行流水、发票、OA 归一化结果、核销和异常。不要创建 read model 逻辑。

必须读取：
- docs/architecture/backend-refactor/data-model-and-read-models.md
- docs/exec-plans/active/backend-refactor-inventory.md，如果存在
- backend/src/fin_ops_platform/domain/
- backend/src/fin_ops_platform/services/state_store.py

范围：
- app.import_batches
- app.import_files
- app.file_objects
- app.bank_transactions
- app.invoices
- app.oa_applications
- app.oa_application_items
- app.oa_attachments
- app.reconciliation_cases
- app.reconciliation_case_rows
- app.workbench_row_overrides
- app.workbench_exception_cases
- app.no_oa_bank_batches
- app.turnover_relations

关键要求：
- 金额 numeric。
- 日期和月份字段可支持分区。
- 保留 source id 和 migration legacy id 映射。
- 写状态字段时用明确 check constraint 或 reference table。
- 核销关系要支持撤销和审计，不物理删除。

不做：
- 不访问 Mongo。
- 不迁移数据。
- 不建 read model 重建器。

交付物：
- 业务事实表 migration。
- 表字段说明。
- 初版索引和唯一约束。

验收：
- migration 可在 04A 后执行。
- 每张表有归属模块。
- 关键唯一约束和索引有业务解释。
```

