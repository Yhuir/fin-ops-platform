# Prompt 06C：数据迁移 Dry-run 和对账执行

```text
/goal
你是 Codex 子代理：数据迁移 dry-run 执行负责人，工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
在不切换生产 API、不冻结 app Mongo、不写 OA 源库的前提下，执行 app Mongo -> PostgreSQL staging -> 目标事实表转换的 dry-run，生成可审计对账报告。该 prompt 只允许在备份、恢复演练、SQL migration 验证完成后执行。

必须读取：
- AGENTS.md
- docs/exec-plans/active/backend-refactor-progress.md
- docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md
- docs/operations/backend-refactor/app-mongo-backup-runbook.md
- docs/operations/backend-refactor/mongo-to-postgresql-migration.md
- docs/architecture/backend-refactor/postgresql-schema-notes.md
- docs/exec-plans/active/backend-refactor-prompts/06a-mongo-export-tooling.md
- docs/exec-plans/active/backend-refactor-prompts/06b-postgres-import-validation-tooling.md
- rust/fin-ops-api/migrations/README.md

前置条件：
- app Mongo 备份和恢复演练已通过。
- PostgreSQL 16/17 空库 migration 验证已通过。
- 已有导出工具或明确导出 runbook。
- 已有 PostgreSQL staging 导入工具或明确导入 runbook。

禁止：
- 不访问、不备份、不导出、不修改 OA 源数据库。
- 不把 dry-run 结果直接作为生产事实源。
- 不把差异标记为通过。
- 不覆盖已有备份。
- 不在报告中记录 secret。

任务拆分：

1. Dry-run 环境确认
   - 确认使用 app Mongo 备份文件、恢复测试库或只读生产 app Mongo。
   - 确认 PostgreSQL 目标是 staging/临时 dry-run 库或 batch_id 隔离的 staging schema。
   - 确认不会写生产 API 当前读写路径。

2. 分区准备
   - 根据 Mongo 数据中的月份范围创建 PostgreSQL 历史分区。
   - 覆盖 `bank_transactions`、`invoices`、`oa_applications`、`workbench_rows`、`search_index_rows`。
   - 分区创建脚本必须可重复执行。

3. app Mongo 导出
   - 运行 06A 工具或按 runbook 导出。
   - 生成 manifest。
   - 生成 collection/object count。
   - 记录 GridFS 文件数量和总字节数。

4. PostgreSQL staging 导入
   - 运行 06B 工具导入 staging。
   - 使用 migration_run_id 或 manifest_id 隔离。
   - 失败记录必须保留，不能静默跳过。

5. staging -> 事实表转换 dry-run
   - 转换 import_batches、file_objects、import_files。
   - 转换 bank_transactions。
   - 转换 invoices。
   - 转换 reconciliation/workbench 相关事实。
   - 转换 job/background task 中仍有效的数据。
   - 生成 legacy_id_map。
   - 生成必要 audit.events 和 read_model rebuild outbox 草案。

6. 对账报告
   - collection/document count 对账。
   - 金额合计对账：银行流水 inflow/outflow、发票 output/input、税额。
   - 月份分布对账。
   - 状态分布对账。
   - legacy id 映射覆盖率。
   - 文件数量、字节数、SHA-256 抽样。
   - 失败、跳过、无法映射记录清单。

7. 阻断规则
   - 任何金额差异必须失败。
   - 任何 count 差异必须解释，不能自动通过。
   - checksum 抽样失败必须失败。
   - 未识别状态值必须失败并回到 mapping 修正。

交付物：
- docs/operations/backend-refactor/data-migration-runbook.md
- docs/operations/backend-refactor/migration-validation-report-template.md
- docs/operations/backend-refactor/migration-dry-run-report-YYYYMMDD.md
- 如实现代码，放在 repo 既有 scripts/tools 约定目录；不要散放临时脚本。

验收：
- dry-run 可重复执行。
- 报告能定位差异到集合、月份、对象类型和 legacy id。
- 不访问 OA 源数据库。
- 不写 secret。
- 不声称生产迁移完成。
```

