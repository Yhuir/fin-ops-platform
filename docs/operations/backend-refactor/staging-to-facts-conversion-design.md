# Staging 到事实表转换设计草案

本文是 P1-06B 的转换设计草案，只描述从 `staging.mongo_import_rows` 到正式事实表、读模型、任务和审计 schema 的 dry-run 转换边界。本文不授权生产迁移，不包含真实 secret，不访问 OA 源数据库。

## 输入与隔离

每次导入使用同一个 UUID 作为：

- `staging.mongo_export_manifest.id`
- `staging.mongo_import_rows.manifest_id`
- 后续 `staging.legacy_id_map.migration_run_id`

转换任务必须只读取一个 `manifest_id` 范围内的数据。重复执行时，先清理同一 `manifest_id` 的目标 dry-run 输出或使用独立临时库；不得跨批次混写。

## Bronze：staging 原始行

`staging.mongo_import_rows` 保留 06A NDJSON 外层结构：

```text
manifest_id
legacy_collection
legacy_id
row_no
payload
payload_hash
target_table
status
error_code
error_message
```

约束：

- `payload` 必须保留原始规范化 JSON，不在 staging 阶段丢字段。
- 解析失败必须保留在 validation report；有效 JSON 行才能进入 `mongo_import_rows`。
- `payload_hash` 用于重跑对账和变更检测。
- `target_table` 只作为转换建议，不代表已经写入正式表。

## Silver：转换与映射

转换程序按对象类型分批处理：

| 批次 | 来源 `legacy_collection` | 目标 |
| --- | --- | --- |
| 1 | `import_batches` | `app.import_batches` |
| 2 | `file_import_files`, `import_file_blobs.files` | `app.file_objects`, `app.import_files` |
| 3 | `bank_transactions` | `app.bank_transactions` |
| 4 | `invoices` | `app.invoices` |
| 5 | `workbench_row_overrides` | `app.workbench_row_overrides` |
| 6 | `workbench_pair_relations` | `app.reconciliation_cases`, `app.reconciliation_case_rows` |
| 7 | `workbench_candidate_matches` | `read_model.workbench_candidate_matches` 或重建输入 |
| 8 | `background_jobs` | `job.worker_tasks`，历史 attempt 只能作为归档摘要 |

每写入一个目标对象，必须写 `staging.legacy_id_map`：

```text
source_system = app_mongo
legacy_collection
legacy_id
target_schema
target_table
target_id
target_partition_month
payload_hash
migration_run_id
```

映射覆盖率低于 100% 的对象类型必须阻断，除非该对象类型在迁移计划中明确标记为“不迁移/可重建/归档”。

## Gold：事实、审计和重建事件

正式转换时的事务边界：

1. 写正式事实表。
2. 写 `staging.legacy_id_map`。
3. 写 `audit.events`，事件类型建议为 `migration.object_imported`。
4. 对影响页面的对象写 `job.outbox_events` 草案或真实事件，触发 read model/search 重建。
5. 同一批次提交后立刻执行 count/hash/amount/month/status 对账。

在 dry-run 隔离环境中，可以写正式 schema 做转换演练；在生产环境中，未通过 dry-run 对账报告前不得把数据写成生产事实源。

## 阻断规则

以下任一情况必须停止转换：

- `staging.mongo_import_rows.status='failed'` 或 validation report 有 blocking findings。
- 发现未知状态枚举、未知金额格式、无法识别日期或缺失 legacy id。
- 同一 legacy object 映射到多个 active target，且没有明确业务解释。
- count、amount、month、status、file checksum 任一维度出现未解释差异。
- read model 无法从事实表重建。

## 不做事项

- 不访问 OA 源数据库。
- 不直接扫描 OA Mongo 补字段。
- 不把旧 Mongo 全量覆盖已经成为事实源的 PostgreSQL。
- 不物理删除业务事实。
- 不把 GridFS 文件内容 checksum 伪装为已完成；文件内容校验属于 06D。
