# 04 阶段 Codex 执行 Prompt：staging 转正式表和对账

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 04：基于阶段 03 已完成的 production export 和 PostgreSQL staging import，将 `staging.mongo_raw_records` 中的 production export 数据转换到 PostgreSQL 正式 schema `app/read_model/job/audit`，建立稳定旧 ID 到新 UUID 的映射，生成可审计 reconciliation report，证明 Mongo export、staging 数据与正式 PostgreSQL 表在数量、金额、状态、月份、文件和关键样本上可解释一致。阶段 04 完成后，PostgreSQL 正式表应承载 app 业务数据，但本阶段仍不得切换应用读写路径，不得 dual-write，不得 shadow-read，不得修改生产服务配置。

你必须遵守以下硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。本阶段不需要连接 OA Mongo；不得读取 OA 业务正文，不得写入、建索引、修复、清洗或备份 OA Mongo。
2. app Mongo `fin_ops_platform_app` 禁止触碰。本阶段只从 PostgreSQL `staging` 读取阶段 03 已导入的数据；不得从 Mongo 重新导出，不得连接 app Mongo。
3. 禁止手写解析 Mongo pickle/Binary payload。阶段 04 只能使用阶段 03 NDJSON/staging 中已经规范化的 `normalized_payload`、`raw_payload` 和 manifest。
4. PostgreSQL 本阶段允许写：
   - `staging.id_mappings`
   - `app.*`
   - `read_model.*`
   - `job.*`
   - `audit.*`
   - reconciliation report 文件
   禁止写 `staging.mongo_exports` / `staging.mongo_raw_records`，除非是只读验证或明确记录修复阶段 03 的错误且先停止汇报。
5. 禁止执行读写路径切换、dual-write、shadow-read、修改服务配置或重启生产服务。
6. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码或 prompt。
7. 所有服务器操作必须先 dry-run/plan，再执行；任何正式转换前必须确认目标数据库、目标 export、目标 schema 和备份路径。
8. 转换必须可重复执行。重复转换同一 production export 不得重复写业务行，不得改变已建立的 stable UUID mapping。
9. 如果发现 staging count 与 manifest 不一致、stable UUID 映射冲突、核心 identity 缺失且无法解释、金额/日期/status 解析失败、核心对象数量或金额差异无法解释、reconciliation report 为 blocked，立即停止并记录 `BLOCKED`。
10. 如果阶段 04 发现阶段 02 schema 无法承接某类数据，只记录待决问题，不得临时绕过到非目标表，不得静默丢弃事实数据。
11. 不修改前端业务功能，不修改现有 API DTO，不修改运行中的生产服务配置。

阶段 03 已通过的事实：

- 阶段 03 gate：`PASS`。
- production export id：`fin_ops_app_export_20260519235526_5a233544`。
- production export path：`/data/exports/fin_ops/fin_ops_app_export_20260519235526_5a233544`。
- production manifest path：`/data/exports/fin_ops/fin_ops_app_export_20260519235526_5a233544/manifest.json`。
- production manifest file sha256：`924ae80f2d613d8954a875a6a2f4508fcaf940d88085120ab48db72957c09901`。
- production manifest payload sha256：`54d14c2ee2c2f09e7fb7c62bd5a6729fbb7dad075c76180f2be3cf2dbc414152`。
- production total records：`15494`。
- production staging import：`imported`。
- production duplicate import：`skipped`，证明重复导入安全跳过。
- PostgreSQL staging 后验：
  - `staging.mongo_exports=1`
  - `staging.mongo_raw_records=15494`
- GridFS：
  - files：`445`
  - chunks：`709`
  - total bytes：`98716321`
  - sampled checksum count：`5`
- 核心业务事实数量：
  - invoices：`391`
  - bank transactions：`431`
  - import batches：`6`
  - GridFS files：`445`
- 生产与 restore 的差异集中在运行期派生/运维状态：
  - background jobs：restore `111`，production `114`
  - cost statistics read models：restore `30`，production `34`
  - workbench candidate matches：restore `5276`，production `5274`
  - workbench matching dirty scopes：restore `0`，production `2`
  - workbench read models：restore `0`，production `6`
- OA Mongo：未触碰。
- app Mongo：只读导出，未写入、未建索引、未清理。
- `fin-ops.service`：执行前后均为 `active`，未重启。

阶段 02 已通过的事实：

- 阶段 02 gate：`PASS`。
- PostgreSQL database：`fin_ops`。
- PostgreSQL version：16.12。
- `public.schema_migrations` 0001-0007 已 applied。
- extensions：`btree_gin`、`pg_trgm`、`pgcrypto`、`plpgsql`。
- schema/table：
  - `app`：41 张表。
  - `audit`：2 张表。
  - `job`：3 张表。
  - `read_model`：6 张表。
  - `staging`：3 张表。
- 阶段 02 PostgreSQL DDL 前备份：
  - Dump：`/data/backups/fin_ops/postgres_phase02_20260520024253/fin_ops_pre_phase02_20260520024253.dump`
  - SHA-256：`60d641bde7392ca59b25aef26b46f1aede9daafd293d829ce6ed247501d92319`

服务器连接信息：

- 主机 IP：`139.155.5.132`
- 用户：`root`
- 协议：SSH
- 密码不写入 prompt 或文档；执行时由用户安全提供或使用已有 SSH 凭据。

必须先读的文档：

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `backend/README.md`
- `docs/index.md`
- `docs/dev/backend.md`
- `docs/dev/testing.md`
- `docs/database-migration/README.md`
- `docs/database-migration/00-current-state-inventory.md`
- `docs/database-migration/code-evidence-index.md`
- `docs/database-migration/01-production-backup-staging.md`
- `docs/database-migration/01-target-postgresql-design.md`
- `docs/database-migration/02-postgresql-schema-migration.md`
- `docs/database-migration/03-normalized-export-staging-import.md`
- `docs/database-migration/04-staging-transform-reconciliation.md`
- `docs/database-migration/02-execution-plan.md`
- `docs/database-migration/prompts/00-code-evidence-inventory.prompt.md`
- `docs/database-migration/prompts/01-production-backup-staging.prompt.md`
- `docs/database-migration/prompts/02-postgresql-schema-migration.prompt.md`
- `docs/database-migration/prompts/03-normalized-export-staging-import.prompt.md`

必须先读的代码：

- `backend/src/fin_ops_platform/postgres/migrate.py`
- `backend/src/fin_ops_platform/postgres/migrations/0001_extensions_and_schemas.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0002_core_imports_invoices_bank.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0003_workbench_relations_exceptions.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0004_oa_projection_sync.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0005_tax_etc_turnover_settings_jobs.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0006_read_models.sql`
- `backend/src/fin_ops_platform/tools/export_manifest.py`
- `backend/src/fin_ops_platform/tools/export_app_mongo.py`
- `backend/src/fin_ops_platform/tools/import_postgres_staging.py`
- `backend/src/fin_ops_platform/tools/exporters/core.py`
- `backend/src/fin_ops_platform/tools/exporters/workbench.py`
- `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py`
- `backend/src/fin_ops_platform/tools/exporters/read_models.py`
- `backend/src/fin_ops_platform/domain/models.py`
- `backend/src/fin_ops_platform/domain/enums.py`
- `backend/src/fin_ops_platform/services/imports.py`
- `backend/src/fin_ops_platform/services/import_file_service.py`
- `backend/src/fin_ops_platform/services/invoice_identity_service.py`
- `backend/src/fin_ops_platform/services/bank_transaction_identity_service.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `backend/src/fin_ops_platform/services/workbench_exception_case_service.py`
- `backend/src/fin_ops_platform/services/workbench_read_model_service.py`
- `backend/src/fin_ops_platform/services/workbench_candidate_match_service.py`
- `backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_service.py`
- `backend/src/fin_ops_platform/services/etc_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_models.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `backend/src/fin_ops_platform/services/historical_etc_repair_service.py`
- `backend/src/fin_ops_platform/services/turnover_relation_service.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_extra_service.py`
- `backend/src/fin_ops_platform/services/background_job_service.py`
- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/services/app_health_alert_service.py`
- `backend/src/fin_ops_platform/services/search_service.py`
- `tests/test_postgres_migrations.py`
- `tests/test_import_postgres_staging.py`
- `tests/test_mongo_export_manifest.py`
- `tests/test_export_app_mongo.py`

建议新增/修改路径：

- `backend/src/fin_ops_platform/tools/transform_staging_to_postgres.py`
- `backend/src/fin_ops_platform/tools/reconcile_postgres_migration.py`
- `backend/src/fin_ops_platform/tools/reconciliation_report.py`
- `backend/src/fin_ops_platform/tools/transformers/__init__.py`
- `backend/src/fin_ops_platform/tools/transformers/ids.py`
- `backend/src/fin_ops_platform/tools/transformers/core.py`
- `backend/src/fin_ops_platform/tools/transformers/workbench.py`
- `backend/src/fin_ops_platform/tools/transformers/ops_tax_etc.py`
- `backend/src/fin_ops_platform/tools/transformers/read_models.py`
- `tests/test_postgres_transform_ids.py`
- `tests/test_transform_staging_to_postgres.py`
- `tests/test_reconcile_postgres_migration.py`
- `docs/database-migration/04-staging-transform-reconciliation.md`
- 必要时更新 `docs/database-migration/README.md`、`docs/index.md`

执行方式：

- 必须使用子代理并行完成可并行任务。
- 子代理可以读代码并在明确独立文件范围内写代码，但不得连接服务器、不得执行数据库命令。
- 所有服务器连接、PostgreSQL 备份、正式表转换、reconciliation report 服务器执行、文档最终汇总必须由主线程串行完成。
- 多个子代理写文件时必须分配不重叠所有权，避免同一文件并发编辑。
- 主线程负责 review、合并、运行测试、服务器执行和最终文档。

串行步骤：

Step 0：建立工作基线

- 运行 `git status --short`。
- 确认当前分支已包含阶段 02 和阶段 03 结果。
- 读取所有参考文档和关键代码。
- 确认阶段 03 gate 是 `PASS`。
- 记录当前已有未提交变更；不得回滚用户或上一阶段改动。
- 确认本阶段允许修改 backend tools、tests、数据库迁移文档；不修改前端业务功能，不修改 API DTO。
- 确认阶段 03 production export：
  - export id：`fin_ops_app_export_20260519235526_5a233544`
  - staging raw rows：`15494`
  - source database：`fin_ops_platform_app`

Step 1：并行设计复核和任务拆分

可并行任务 1A：stable ID、transform runner 和幂等策略复核

- 读取：
  - `0001_extensions_and_schemas.sql`
  - `migrate.py`
  - `03-normalized-export-staging-import.md`
  - `04-staging-transform-reconciliation.md`
- 输出：
  - `staging.id_mappings` 写入策略。
  - deterministic UUID 方案。
  - transform CLI 参数和事务边界。
  - dry-run/plan 输出格式。
  - 重跑同一 export 的幂等策略。
  - 如果正式表已有数据，本阶段如何安全判断是 empty、same export、还是 conflicting existing data。

可并行任务 1B：核心事实 transformer 复核

- 读取：
  - `0002_core_imports_invoices_bank.sql`
  - `tools/exporters/core.py`
  - `domain/models.py`
  - `imports.py`
  - identity services
- 输出：
  - `app.import_batches`、`app.import_batch_rows`、`app.file_objects`、`app.import_files`、`app.invoices`、`app.bank_transactions` 字段映射。
  - 必须 fail-fast 的 identity、amount、date、status 字段。
  - import rows 从 `source_collection='import_batches:row_results'` 的转换策略。
  - GridFS file objects 转换策略。
  - 单元测试和聚合对账 SQL。

可并行任务 1C：工作台、异常、免 OA、分类 transformer 复核

- 读取：
  - `0003_workbench_relations_exceptions.sql`
  - `0004_oa_projection_sync.sql`
  - `tools/exporters/workbench.py`
  - workbench/no OA/bank category services
- 输出：
  - `app.matching_runs`、`app.matching_results`、`app.workbench_*`、`app.no_oa_bank_*`、`app.bank_transaction_*`、`job.workbench_matching_dirty_scopes` 字段映射。
  - relation/case/batch/event 的 identity 和状态转换规则。
  - 哪些旧 meta snapshot 只能保留 raw/reference，不能作为事实拆列。
  - 单元测试和对账指标。

可并行任务 1D：设置、任务、税金、ETC、往来 transformer 复核

- 读取：
  - `0005_tax_etc_turnover_settings_jobs.sql`
  - `tools/exporters/ops_tax_etc.py`
  - settings/jobs/health/tax/ETC/turnover services
- 输出：
  - `app.app_settings`、`job.background_jobs`、`audit.app_health_alerts`、tax/ETC/turnover 目标表字段映射。
  - ETC state snapshot 是否需要拆多表或先 raw/reference 落表。
  - 空集合处理策略。
  - 关键 amount/status/version 字段对账指标。

可并行任务 1E：read model 和 reconciliation report 复核

- 读取：
  - `0006_read_models.sql`
  - `tools/exporters/read_models.py`
  - `search_service.py`
  - read model services
- 输出：
  - read model 是导入 reference、重建，还是两者并行。
  - `read_model.search_index_rows` 生成策略。
  - reconciliation report JSON/Markdown schema。
  - counts、amounts、status/month distribution、sample diff、GridFS checksum 的 SQL 查询设计。

主线程汇总后，确定文件所有权和 implementation plan。

Step 2：建立 stable ID 和 transform runner 基础设施

新增：

- `backend/src/fin_ops_platform/tools/transformers/__init__.py`
- `backend/src/fin_ops_platform/tools/transformers/ids.py`
- `backend/src/fin_ops_platform/tools/transform_staging_to_postgres.py`

要求：

- `ids.py` 实现 deterministic UUID：
  - 使用固定 namespace UUID，写在代码中。
  - 输入至少包含 `source_collection`、`legacy_mongo_id`、`target_schema`、`target_table`。
  - 同一输入多次生成同一 UUID。
  - 不同 target table 即使 legacy id 相同也生成不同 UUID。
- `ids.py` 实现 `staging.id_mappings` upsert/verify：
  - 已存在且 target_id 一致：复用。
  - 已存在但 target_id 不一致：fail fast。
  - 可 dry-run 输出将创建/复用/冲突的 mapping count。
- `transform_staging_to_postgres.py` CLI 支持：
  - `--export-id`
  - `--database-url`
  - `--dry-run`
  - `--only-domain core|workbench|ops_tax_etc|read_models`
  - `--skip-domain`
  - `--fail-on-warning`
  - `--replace-existing-target`，仅当确认目标正式表为空或为同一 export 可重建数据时允许。
  - `--report-dir`
- transform 前必须验证：
  - migrations 0001-0007 applied。
  - `staging.mongo_exports.export_id` 存在且 `status='imported'`。
  - `staging.mongo_raw_records` count 等于 manifest `total_records`。
  - 当前目标正式表状态。
- dry-run 不写正式表，不写 `staging.id_mappings`，只输出 plan JSON。
- 正式执行必须事务化；任一 transformer 失败 rollback。
- 不打印完整 DB URI 或密码。

测试：

- `tests/test_postgres_transform_ids.py`
- `tests/test_transform_staging_to_postgres.py`

必须覆盖：

- 同一 legacy id 生成稳定 UUID。
- 不同 target table 生成不同 UUID。
- mapping 冲突 fail fast。
- dry-run 不调用写 SQL。
- 缺少 export 或 staging count mismatch fail fast。

Step 3：实现核心事实转换

新增：

- `backend/src/fin_ops_platform/tools/transformers/core.py`

目标表：

- `app.import_batches`
- `app.import_batch_rows`
- `app.file_objects`
- `app.import_files`
- `app.invoices`
- `app.bank_transactions`

要求：

- 从 `staging.mongo_raw_records` 读取：
  - `import_batches`
  - `import_batches:row_results`
  - `file_import_files`
  - `file_import_sessions`
  - `file_objects`
  - `gridfs_files_manifest`
  - `invoices`
  - `bank_transactions`
- import batch：
  - 转换 `legacy_mongo_id`、`batch_type`、`source_name`、`imported_by`、`row_count`、`success_count`、`error_count`、`duplicate_count`、`suspected_duplicate_count`、`updated_count`、`status`、`imported_at`、`raw_payload`。
- import row：
  - 转换 `legacy_mongo_id`、`import_batch_id`、`legacy_batch_id`、`row_no`、`source_record_type`、`source_unique_key`、`data_fingerprint`、`decision`、`decision_reason`、`linked_object_type`、`linked_object_id`、identity fields、raw payload。
  - `import_batch_id` 必须通过 `staging.id_mappings` 找到对应 `app.import_batches.id`。
- invoice：
  - 转换 `legacy_mongo_id`、`invoice_type`、`invoice_no`、`invoice_code`、`digital_invoice_no`、`source_unique_key`、`data_fingerprint`、counterparty、seller/buyer、amount、signed_amount、written_off_amount、tax_rate、tax_amount、total_with_tax、currency、source batch、OA/ETC references、visibility/status/tags/source_links/raw_payload。
  - 金额必须使用 Decimal，不得通过 float。
  - `invoice_month` 由 payload 或 `invoice_date` 取当月第一天。
- bank transaction：
  - 转换 `legacy_mongo_id`、account、direction、counterparty、amount、signed_amount、written_off_amount、txn_date、txn_month、trade_time、bank serial、source unique/fingerprint、source batch、project/currency/balance/summary/remark/text fields/status/raw_payload。
  - `txn_month` 由 payload 或 `txn_date/trade_time` 取当月第一天。
- file object：
  - 转换 GridFS legacy id、storage backend、storage uri、bucket name、object key、filename、size bytes、content type、metadata/raw_payload。
  - 本阶段不迁移文件内容。
- import file：
  - 转换 `legacy_mongo_id`、session、stored_file_path、original filename、template kind、status、uploaded_by、uploaded_at、raw_payload。
  - 如果能可靠关联 `file_object_id`，必须关联；不能关联则 raw 保留并记录 warning。
- 目标表必须使用 deterministic UUID。
- source_unique_key/data_fingerprint 唯一冲突必须 fail fast。

测试：

- fake staging rows 转换到 SQL plan。
- Decimal 不经 float。
- invoice/bank amount totals。
- import rows count 和 row_no。
- FK mapping：invoice/bank source batch -> import batch。
- GridFS file_objects count。

Step 4：实现工作台、异常、matching、免 OA、银行分类转换

新增：

- `backend/src/fin_ops_platform/tools/transformers/workbench.py`

目标表：

- `app.matching_runs`
- `app.matching_results`
- `app.workbench_pair_relations`
- `app.workbench_pair_relation_history`
- `app.workbench_row_overrides`
- `app.workbench_exception_cases`
- `app.workbench_exception_case_events`
- `app.no_oa_bank_batches`
- `app.no_oa_bank_batch_events`
- `app.bank_transaction_categories`
- `app.bank_transaction_category_events`
- `job.workbench_matching_dirty_scopes`

要求：

- 读取对应 `source_collection`：
  - `matching_runs`
  - `matching_results`
  - `workbench_pair_relations`
  - `workbench_pair_relations_meta`
  - `workbench_row_overrides`
  - `workbench_exception_cases`
  - `workbench_exception_cases_meta`
  - `no_oa_bank_batches`
  - `no_oa_bank_batch_audit_log`
  - `bank_transaction_categories`
  - `bank_transaction_categories_meta`
  - `workbench_matching_dirty_scopes`
- relation：
  - 保留 `case_id`、`relation_mode`、`status`、`version`、`month_scope`、row ids/types、amount_check、special_metadata、source_versions、raw_payload。
- relation history/event：
  - meta snapshot 中可以拆出的 event 必须落 `app.workbench_pair_relation_history`。
  - 无法安全拆列的旧 meta snapshot 保留 raw/reference，记录 warning，不得静默丢弃。
- exception case/events：
  - 保留 case_id、status、business_line、scenario、resolution、candidate ids、history/audit。
- no OA batches/events：
  - 保留 batch_id、status/status_bucket、version、scope_month、account_key、total_amount、submitted/withdrawn、event log。
- bank categories/events：
  - 保留 manual/auto、version、actor/audit。
- dirty scopes：
  - 写 `job.workbench_matching_dirty_scopes`，保留 scope、reason、attempt/error、raw_payload。
- 对引用 invoice/bank row 的字段：
  - 如果已有正式表 mapping，可转换为 target UUID。
  - 如果暂时不能可靠转换，保留 legacy row ids 和 raw_payload，并在 report 中标记 unresolved reference count。

测试：

- relation count、active/reverted status distribution。
- no OA batch count 和 total_amount。
- category version preserved。
- dirty scopes count。
- meta snapshot warning 可见。

Step 5：实现设置、任务、健康、税金、ETC、往来转换

新增：

- `backend/src/fin_ops_platform/tools/transformers/ops_tax_etc.py`

目标表：

- `app.app_settings`
- `job.background_jobs`
- `audit.app_health_alerts`
- `app.tax_certified_import_sessions`
- `app.tax_certified_import_batches`
- `app.tax_certified_import_records`
- `app.etc_import_sessions`
- `app.etc_import_batches`
- `app.etc_invoices`
- `app.etc_submission_batches`
- `app.etc_business_batches`
- `app.etc_reconciliation_tasks`
- `app.etc_reconciliation_files`
- `app.historical_etc_repair_bundles`
- `app.historical_etc_repair_parsed_seeds`
- `app.historical_etc_repair_states`
- `app.turnover_relations`
- `app.turnover_relation_events`
- `app.turnover_ledger_extras`

要求：

- app settings：
  - 写 singleton，保留配置 payload、版本/更新时间、raw_payload。
- background jobs：
  - 保留 job id/type/status/owner/visibility/source/affected_months/progress/result_summary/error/attention/supersede/ack fields/raw_payload。
- app health alerts：
  - 保留 alert id/kind/scope/severity/status/active/recovered timestamps/raw_payload。
- tax certified：
  - sessions/batches/records 均转换；空集合安全处理。
  - certified unique key、invoice identity、tax amount、scope month、matched plan id 必须保留。
- ETC：
  - 如果 stage 03 的 ETC 文件是 `etc_state` / `etc_reconciliation_state` snapshot，需要在 transformer 中拆出 invoices/import sessions/import batches/submission batches/business batches/tasks/files。
  - 不能可靠拆出的旧 shape 必须 raw/reference 落到最接近的表并记录 warning，不得丢弃。
  - 保留 invoice number、dates、amounts、status、batch ids、task id、business batch id、version、OA detection fields、file paths/hash。
- historical ETC repair：
  - 保留 bundle/seed/state ids、file refs、status/result/error。
- turnover：
  - 保留 relation id、bank transaction id、status、scope month、counterparty、amount、events、extras。
- 空集合必须生成 0 count result，不应失败。

测试：

- singleton app_settings。
- background jobs count/status。
- app health alerts count/status。
- tax empty collections。
- ETC snapshot split/legacy shape。
- turnover empty collections。

Step 6：实现 read model/reference 和 search index 转换

新增：

- `backend/src/fin_ops_platform/tools/transformers/read_models.py`

目标表：

- `read_model.workbench_rows`
- `read_model.workbench_snapshots`
- `read_model.workbench_candidate_matches`
- `read_model.search_index_rows`
- `read_model.cost_statistics_read_models`
- `read_model.tax_offset_read_models`

要求：

- 对阶段 03 已导出的旧 read model：
  - 写入 reference/imported payload，标记 `cache_status='imported_reference'` 或等价状态。
  - 不把旧 read model 当作事实源覆盖事实表。
- `read_model.search_index_rows`：
  - 从正式 facts 表生成 invoice/bank/ETC/turnover/searchable text。
  - 不连接 OA Mongo；如需要 OA-side text，只使用阶段 03 已导出的 app-side cache/manual import。
- workbench read model：
  - 如果可以只依赖 PostgreSQL facts 重建，则重建。
  - 如果当前 service 仍强依赖 Mongo/OA adapter，则本阶段导入 reference payload，并在 report 中标记 `rebuild_deferred_to_phase05`。
- candidate matches：
  - 转换 candidate key、scope month、row ids、confidence、status、source_versions、payload。
- cost/tax read models：
  - 导入 reference payload，并保留 source scope keys、generated_at、cache_status。

测试：

- search index 生成覆盖 invoice/bank/file/ETC 文本字段。
- read model reference count。
- candidate matches count/status。
- rebuild deferred warning 可见且不导致 core gate 失败。

Step 7：实现 reconciliation report

新增：

- `backend/src/fin_ops_platform/tools/reconciliation_report.py`
- `backend/src/fin_ops_platform/tools/reconcile_postgres_migration.py`

输出：

```text
<report-dir>/migration_reconciliation_report_<export_id>.json
<report-dir>/migration_reconciliation_report_<export_id>.md
```

CLI 支持：

- `--export-id`
- `--database-url`
- `--output`
- `--fail-on-warning`

报告必须包含：

- export identity、source_database、manifest sha256、code commit。
- staging count 与 manifest total。
- source_collection counts。
- formal table counts。
- `staging.id_mappings` counts by target table。
- 核心对象 count：
  - import_batches
  - import_batch_rows
  - file_objects
  - import_files
  - invoices
  - bank_transactions
  - workbench/no OA/category/ETC/tax/turnover/read_model
- 金额合计：
  - invoices amount/signed_amount/tax_amount/total_with_tax/written_off_amount
  - bank transactions amount/signed_amount/written_off_amount/balance where meaningful
  - tax certified tax amounts
  - ETC totals
  - turnover amounts
- 状态分布：
  - invoices
  - bank transactions
  - pair relations
  - exception cases
  - no OA batches
  - ETC objects
  - jobs/alerts
- 月份分布：
  - invoice_month
  - txn_month
  - scope_month
- GridFS：
  - files count
  - chunks count
  - total bytes
  - sampled checksums from manifest
- sample diff：
  - 每类核心对象至少抽样 5 个或全部不足 5 个。
  - 输出 `source_collection`、`legacy_mongo_id`、`target_table`、`target_id`、字段差异。
- warnings/errors/blockers。

状态规则：

- `status='pass'`：
  - staging count 与 manifest 一致。
  - core facts count 与 expected 一致或有明确 skipped/rebuildable 解释。
  - 核心金额合计差异为 0。
  - stable ID mapping 无冲突。
  - GridFS manifest 与阶段 03 结果一致。
- `status='blocked'`：
  - 任一核心 count/amount/status/month 差异无法解释。
  - 任一 stable mapping 冲突。
  - 任一核心 identity 缺失。
  - 任一 checksum mismatch。

测试：

- report pass case。
- report blocked amount diff case。
- report blocked count mismatch case。
- Markdown 输出包含 export id、counts、amounts、warnings。

Step 8：本地测试

必须新增/更新测试：

- `tests/test_postgres_transform_ids.py`
- `tests/test_transform_staging_to_postgres.py`
- `tests/test_reconcile_postgres_migration.py`

必须运行：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_transform_ids tests.test_transform_staging_to_postgres tests.test_reconcile_postgres_migration -v
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

如无本地 PostgreSQL，使用 fake psql/SQL builder 单元测试覆盖；服务器阶段必须执行真实 PostgreSQL dry-run 和正式转换。

Step 9：服务器 PostgreSQL 备份

主线程串行执行，子代理不得执行服务器命令。

- SSH 登录服务器。
- 不输出或记录密码。
- 确认 `fin-ops.service` active。
- 确认 `public.schema_migrations` 0001-0007 applied。
- 确认 staging 当前是阶段 03 production export：
  - `staging.mongo_exports=1`
  - `staging.mongo_raw_records=15494`
  - export id：`fin_ops_app_export_20260519235526_5a233544`
- 对 PostgreSQL `fin_ops` 做阶段 04 前备份：

```bash
pg_dump -Fc fin_ops > /data/backups/fin_ops/postgres_phase04_<timestamp>/fin_ops_pre_phase04_<timestamp>.dump
sha256sum /data/backups/fin_ops/postgres_phase04_<timestamp>/fin_ops_pre_phase04_<timestamp>.dump
```

- 记录 dump path 和 sha256 到 `docs/database-migration/04-staging-transform-reconciliation.md`。
- 若备份失败，停止并记录 `BLOCKED`。

Step 10：服务器 dry-run transform

- 将当前 worktree 的阶段 04 tools 上传到服务器临时目录执行，不覆盖生产应用代码。
- 执行 dry-run：

```bash
PYTHONPATH=<uploaded>/backend/src:/opt/fin-ops/current/backend/src \
python -m fin_ops_platform.tools.transform_staging_to_postgres \
  --export-id fin_ops_app_export_20260519235526_5a233544 \
  --dry-run
```

- dry-run 必须输出：
  - export id
  - source database
  - staging raw count
  - 每个 domain 计划写入的 target table/count
  - 将创建/复用的 `staging.id_mappings` count
  - warnings
  - 是否需要 `--replace-existing-target`
- 如果目标正式表已有数据：
  - 若为空：继续。
  - 若为同一 export 且幂等可验证：继续并记录。
  - 若存在未知来源数据：停止并记录 `BLOCKED`，不得覆盖。

Step 11：服务器正式 transform

只有 Step 10 dry-run 通过后才能执行。

- 执行正式 transform：

```bash
PYTHONPATH=<uploaded>/backend/src:/opt/fin-ops/current/backend/src \
python -m fin_ops_platform.tools.transform_staging_to_postgres \
  --export-id fin_ops_app_export_20260519235526_5a233544 \
  --fail-on-warning
```

- 如果当前实现需要对同一 export 重跑或清理同一 export 旧正式表数据，必须只在 dry-run 明确证明安全后使用 `--replace-existing-target`。
- 正式 transform 完成后验证：
  - `staging.id_mappings` count by target table。
  - 核心正式表 count。
  - 关键 FK not null/valid。
  - `fin-ops.service` 仍为 active。
- 重复执行同一 transform dry-run 或正式命令，必须安全跳过或证明幂等。

Step 12：服务器 reconciliation report

- 执行 report：

```bash
PYTHONPATH=<uploaded>/backend/src:/opt/fin-ops/current/backend/src \
python -m fin_ops_platform.tools.reconcile_postgres_migration \
  --export-id fin_ops_app_export_20260519235526_5a233544 \
  --output /data/exports/fin_ops/reports
```

- 校验 report 文件存在：
  - `/data/exports/fin_ops/reports/migration_reconciliation_report_fin_ops_app_export_20260519235526_5a233544.json`
  - `/data/exports/fin_ops/reports/migration_reconciliation_report_fin_ops_app_export_20260519235526_5a233544.md`
- 读取 report summary，确认 `status=pass`。
- 如果 `status=blocked`，停止，不进入阶段 05。

Step 13：更新文档和 gate

更新 `docs/database-migration/04-staging-transform-reconciliation.md`：

- 执行摘要。
- 子代理并行复核结果。
- 新增/修改文件。
- 本地测试命令和结果。
- PostgreSQL phase04 pre-backup：
  - dump path
  - sha256
- production export：
  - export id
  - manifest path
  - manifest sha256
  - staging raw count
- transform 结果：
  - dry-run plan summary
  - 正式 transform status
  - `staging.id_mappings` count by target table
  - formal table counts
  - 重复执行幂等结果
- reconciliation report：
  - JSON path
  - Markdown path
  - status
  - key counts
  - key amount totals
  - warnings/errors/blockers
- GridFS reconciliation result。
- 是否触碰 OA Mongo：必须为未触碰。
- 是否触碰 app Mongo：必须为未触碰。
- 是否修改服务配置/重启服务：必须为否。
- 阶段 04 gate：
  - `PASS`
  - `BLOCKED`
  - `READY_NOT_TRANSFORMED`，仅当代码和本地测试完成但服务器未执行时使用。

必要时更新：

- `docs/database-migration/README.md`
- `docs/index.md`

阶段 04 Gate：

`PASS` 条件：

- 阶段 03 gate 是 `PASS`。
- PostgreSQL phase04 pre-backup 完成并记录 sha256。
- transform dry-run 通过。
- transform 正式执行通过。
- transform 可重复执行或安全跳过，不重复写数据。
- `staging.id_mappings` 稳定且无冲突。
- 核心对象数量一致或报告中有明确、可接受的 skipped/rebuildable 解释。
- 发票、流水、税金、ETC、往来关键金额合计差异为 0。
- 状态和月份分布差异为 0 或有逐项解释。
- GridFS files/chunks/total bytes 和 sampled checksum 与阶段 03 manifest 一致。
- reconciliation report `status=pass`。
- 后端全量单测通过。
- `fin-ops.service` 保持 active。
- 文档记录 export id、backup path、report path、关键 count、checksum、差异结论。
- 没有密码、token 或完整 URI 写入代码、文档或日志。
- OA Mongo 未触碰。
- app Mongo 未触碰。

`BLOCKED` 条件：

- PostgreSQL 备份失败。
- staging count 与 manifest 不一致。
- stable UUID 映射冲突。
- source identity 缺失且无法解释。
- 金额/日期/status 解析失败。
- 任何核心对象数量差异无法解释。
- 任何核心金额差异不为 0。
- reconciliation report `status=blocked`。
- 任何命令输出或文档包含密码、token 或完整 URI。
- 任何步骤需要连接 OA Mongo 或 app Mongo。
- 任何步骤需要修改生产服务配置、重启服务或切换读写路径。

最终答复必须包含：

- 阶段 04 gate 状态。
- 修改的文件列表。
- 本地测试结果。
- 服务器是否执行 PostgreSQL backup、dry-run transform、正式 transform、reconciliation report。
- backup path 和 sha256。
- export id。
- `staging.id_mappings` count。
- formal table 关键 counts。
- report path、report status、关键金额/数量结论。
- `fin-ops.service` 是否保持 active。
- 是否触碰 OA Mongo：必须明确说明未触碰。
- 是否触碰 app Mongo：必须明确说明未触碰。
- 若未能完成，说明 BLOCKED 原因和下一步最小修复。
```
```
