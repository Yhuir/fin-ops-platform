# 03 阶段 Codex 执行 Prompt：规范化导出和 staging 导入

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 03：基于阶段 02 已完成的 PostgreSQL schema/migration 基础，从 app Mongo 只读导出规范化数据，生成可审计 export artifact，并将导出结果导入 PostgreSQL `staging` schema。阶段 03 完成后，必须有 manifest/checksum 完整的 export 目录，PostgreSQL `staging.mongo_exports` 与 `staging.mongo_raw_records` 中的数据数量必须与 manifest 一致；但本阶段不把数据转换到正式 `app/read_model/job/audit` 表，不 backfill 正式表，不 dual-write，不 shadow-read，不切换应用读写路径。

你必须遵守以下硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。本阶段不需要连接 OA Mongo；不得读取 OA 业务正文，不得写入、建索引、修复、清洗或备份 OA Mongo。
2. app Mongo `fin_ops_platform_app` 和阶段 01 restore 库只允许只读读取。禁止 insert/update/delete/drop/createIndex/repair/compact。
3. 禁止手写解析 Mongo pickle/Binary payload。必须复用现有 Python `ApplicationStateStore` 或业务 service 的读取/规范化路径。
4. PostgreSQL 本阶段只允许写 `staging.mongo_exports` 和 `staging.mongo_raw_records`，以及必要的导入状态元数据。禁止向 `app/read_model/job/audit` 写业务行。
5. 禁止执行正式 backfill、正式表转换、dual-write、shadow-read、switch-read 或修改生产服务配置。
6. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码或 prompt。
7. 所有服务器操作必须先 dry-run/plan，再执行；任何导出或导入前必须确认目标库、目标目录和目标 schema。
8. 如果发现 export count 与 Mongo 只读统计不一致、manifest checksum 不一致、staging count 与 manifest 不一致、JSON/Decimal/datetime 序列化失败、核心 identity 缺失且无法解释，立即停止并记录 `BLOCKED`。
9. 如果阶段 03 发现阶段 02 schema 无法承接某类数据，只记录待决问题，不得临时向正式表写入或绕过 staging。
10. 不重启服务器服务；不修改前端业务功能；不修改现有 API DTO。

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
- 阶段 02 后验验证：
  - `app/read_model/job/audit/staging` 所有表总行数为 0。
  - 重复 `apply` 全部 skipped。
  - `fin-ops.service` 仍为 active。
- 阶段 02 PostgreSQL DDL 前备份：
  - Dump：`/data/backups/fin_ops/postgres_phase02_20260520024253/fin_ops_pre_phase02_20260520024253.dump`
  - SHA-256：`60d641bde7392ca59b25aef26b46f1aede9daafd293d829ce6ed247501d92319`

阶段 01 已通过的事实：

- app Mongo 生产备份：
  - Archive：`/data/backups/fin_ops/20260520013830/fin_ops_platform_app_20260520013830.archive.gz`
  - SHA-256：`c25d9780fded4c4407c29df16796fec2c99d63d201e24daf53ccab98e23f8b48`
- app Mongo staging restore：
  - Restore DB：`fin_ops_platform_app_restore_20260520013830`
  - collections、objects、GridFS files/chunks/total length 与生产库一致。
- app Mongo 生产只读统计：
  - collections：51
  - objects：14859
  - GridFS files：445
  - GridFS chunks：709
  - GridFS total length：98716321 bytes
- OA Mongo 只读统计完成，未写入。

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
- `docs/database-migration/02-execution-plan.md`
- `docs/database-migration/prompts/00-code-evidence-inventory.prompt.md`
- `docs/database-migration/prompts/01-production-backup-staging.prompt.md`
- `docs/database-migration/prompts/02-postgresql-schema-migration.prompt.md`

必须先读的代码：

- `backend/src/fin_ops_platform/services/state_store.py`
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
- `backend/src/fin_ops_platform/postgres/migrate.py`
- `tests/test_state_store.py`
- `tests/test_postgres_migrations.py`

建议新增/修改路径：

- `backend/src/fin_ops_platform/tools/__init__.py`
- `backend/src/fin_ops_platform/tools/export_app_mongo.py`
- `backend/src/fin_ops_platform/tools/import_postgres_staging.py`
- `backend/src/fin_ops_platform/tools/export_manifest.py`
- `backend/src/fin_ops_platform/tools/exporters/__init__.py`
- `backend/src/fin_ops_platform/tools/exporters/core.py`
- `backend/src/fin_ops_platform/tools/exporters/workbench.py`
- `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py`
- `backend/src/fin_ops_platform/tools/exporters/read_models.py`
- `tests/test_mongo_export_manifest.py`
- `tests/test_export_app_mongo.py`
- `tests/test_import_postgres_staging.py`
- `docs/database-migration/03-normalized-export-staging-import.md`
- 必要时更新 `docs/database-migration/README.md`、`docs/index.md`

执行方式：

- 必须使用子代理并行完成可并行任务。
- 子代理可以读代码并在明确独立文件范围内写代码，但不得连接服务器、不得执行数据库命令。
- 所有服务器连接、Mongo 只读导出、PostgreSQL staging 导入、文档最终汇总必须由主线程串行完成。
- 多个子代理写文件时必须分配不重叠所有权，避免同一文件并发编辑。
- 主线程负责 review、合并、运行测试、服务器执行和最终文档。

串行步骤：

Step 0：建立工作基线

- 运行 `git status --short`。
- 确认当前分支已包含阶段 02 结果。
- 读取所有参考文档和关键代码。
- 确认阶段 02 gate 是 `PASS`。
- 记录当前已有未提交变更；不得回滚用户或上一阶段改动。
- 确认本阶段允许修改 backend tools、tests、数据库迁移文档；不修改前端业务功能，不修改 API DTO。

Step 1：并行设计复核和任务拆分

可并行任务 1A：导出框架复核

- 读取 `state_store.py`、`code-evidence-index.md`、`03-normalized-export-staging-import.md`。
- 输出建议：
  - 如何初始化 `ApplicationStateStore` 但保证只读。
  - 如何实现 manifest、NDJSON writer、checksum。
  - 如何处理 Decimal/datetime/Enum/Path/Binary。
  - 如何避免打印 Mongo URI 或密码。
  - 如何设计 fake store 测试。

可并行任务 1B：核心事实和文件 exporter 复核

- 读取 `domain/models.py`、`imports.py`、`import_file_service.py`、`invoice_identity_service.py`、`bank_transaction_identity_service.py`、`state_store.py`。
- 输出：
  - import_batches/import_batch_rows/invoices/bank_transactions/import_files/file_objects/gridfs_files_manifest 字段清单。
  - 必须导出的 identity、amount、date、status、raw_payload 字段。
  - GridFS manifest 和抽样 checksum 方案。
  - 可能的旧 payload 形态风险。

可并行任务 1C：工作台、设置、税金、ETC、read model exporter 复核

- 读取 workbench/no OA/bank category/tax/ETC/turnover/background/app health/read model 相关 service。
- 输出：
  - 所有需要导出的 NDJSON 文件和字段。
  - 哪些是事实，哪些是 read model/reference/rebuildable。
  - 哪些 collection 当前可能为空但仍需要 manifest 标记。
  - 旧 shape 或 schema version 兼容风险。

可并行任务 1D：staging importer 和测试策略复核

- 读取阶段 02 SQL migration、`migrate.py`、`tests/test_postgres_migrations.py`、`docs/dev/testing.md`。
- 输出：
  - import_postgres_staging CLI 方案。
  - `staging.mongo_exports` / `staging.mongo_raw_records` 写入策略。
  - dry-run、幂等、checksum drift、事务 rollback 测试方案。
  - 无 PostgreSQL 环境时的 skip/降级方式。

主线程汇总后，确定文件所有权和 implementation plan。

Step 2：建立导出基础设施

实现：

- `backend/src/fin_ops_platform/tools/__init__.py`
- `backend/src/fin_ops_platform/tools/export_manifest.py`
- `backend/src/fin_ops_platform/tools/export_app_mongo.py`

要求：

- 支持命令：
  - `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.export_app_mongo --output <dir> --source restore`
  - `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.export_app_mongo --output <dir> --source production`
  - `--dry-run`
  - `--data-dir`
  - `--force`，仅允许覆盖 failed/incomplete export 目录，不允许覆盖 completed export。
- 每次导出创建不可变目录：`fin_ops_app_export_<timestamp>/`。
- 生成：
  - `manifest.json`
  - `counts.json`
  - `checksums.sha256`
  - 所有 NDJSON 文件。
- manifest 至少包含：
  - export_id
  - created_at
  - source_database
  - source_mode
  - app_backup_archive
  - app_backup_sha256
  - code_git_commit
  - schema_migration_versions
  - 每个文件 record_count/sha256/bytes
  - GridFS files/chunks/total bytes/抽样 checksum
  - warnings/errors
- 实现 safe JSON 转换：
  - Decimal 输出 string。
  - date 输出 `YYYY-MM-DD`。
  - datetime 输出 ISO 8601。
  - Enum 输出 value。
  - Path 输出 string。
  - bytes/Binary 不允许直接序列化；必须转为明确 metadata 或 fail fast。
- NDJSON writer 必须：
  - 单行 UTF-8 JSON。
  - 写临时文件。
  - close 后计算 sha256。
  - 原子 rename。
- 无 Mongo 配置时报清晰错误。
- 输出不得包含完整 URI 或密码。

Step 3：实现核心事实 exporter

新增：

- `backend/src/fin_ops_platform/tools/exporters/__init__.py`
- `backend/src/fin_ops_platform/tools/exporters/core.py`

输出文件：

- `import_batches.ndjson`
- `import_batch_rows.ndjson`
- `invoices.ndjson`
- `bank_transactions.ndjson`
- `import_files.ndjson`
- `file_objects.ndjson`
- `gridfs_files_manifest.ndjson`

要求：

- 每条记录包含：
  - export_id
  - source_collection
  - legacy_mongo_id 或 legacy_key
  - record_type
  - normalized_payload
  - raw_payload
  - source_versions 可选
  - exported_at
- invoice 必须保留：
  - invoice_no、invoice_code、digital_invoice_no、source_unique_key、data_fingerprint
  - counterparty、seller/buyer、amount、signed_amount、tax_amount、total_with_tax
  - invoice_date、invoice_month、status、source_batch_id
- bank transaction 必须保留：
  - account_no、account_name、txn_direction、counterparty_name_raw
  - amount、signed_amount、written_off_amount
  - txn_date、txn_month、trade_time、bank_serial_no
  - source_unique_key、data_fingerprint、status、source_batch_id
- import batch/row 必须保留：
  - row_count、success_count、error_count、duplicate_count、status、imported_at
  - row_no、decision、decision_reason、linked_object_type/id、identity fields、raw row payload
- files/GridFS：
  - 本阶段只导出 manifest，不迁移文件内容。
  - manifest 包含 gridfs id、filename、length、uploadDate、metadata、content_type。
  - 抽样至少 5 个 GridFS 文件计算 checksum；文件少于 5 时全部抽样。
- 不允许金额通过 float 转换。

Step 4：实现工作台、异常、matching、免 OA exporter

新增：

- `backend/src/fin_ops_platform/tools/exporters/workbench.py`

输出文件：

- `matching_runs.ndjson`
- `matching_results.ndjson`
- `workbench_pair_relations.ndjson`
- `workbench_pair_relation_history.ndjson`
- `workbench_row_overrides.ndjson`
- `workbench_exception_cases.ndjson`
- `workbench_exception_case_events.ndjson`
- `no_oa_bank_batches.ndjson`
- `no_oa_bank_batch_events.ndjson`
- `bank_transaction_categories.ndjson`
- `bank_transaction_category_events.ndjson`

要求：

- relation 保留 case_id、relation_mode、status、version、month_scope、row_ids、row_types、amount_check、special_metadata、source_versions。
- history/event 保留 actor、event_type、occurred_at、before/after payload。
- row override 保留 projection_version、changed_row_ids、override_payload。
- exception case 保留 case_id、status、business_line、scenario、resolution、candidate_ids、history/audit。
- no OA batch 保留 batch_id、status/status_bucket、version、scope_month、account_key、total_amount、submitted/withdrawn。
- bank category 保留 manual/auto、version、actor/audit。
- matching run/result 保留历史兼容信息。

Step 5：实现设置、任务、税金、ETC、往来 exporter

新增：

- `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py`

输出文件：

- `app_settings.ndjson`
- `background_jobs.ndjson`
- `app_health_alerts.ndjson`
- `tax_certified_import_sessions.ndjson`
- `tax_certified_import_batches.ndjson`
- `tax_certified_import_records.ndjson`
- `etc_invoices.ndjson`
- `etc_import_sessions.ndjson`
- `etc_import_batches.ndjson`
- `etc_submission_batches.ndjson`
- `etc_business_batches.ndjson`
- `etc_reconciliation_tasks.ndjson`
- `etc_reconciliation_files.ndjson`
- `historical_etc_repair_bundles.ndjson`
- `historical_etc_repair_parsed_seeds.ndjson`
- `historical_etc_repair_states.ndjson`
- `turnover_relations.ndjson`
- `turnover_relation_events.ndjson`
- `turnover_ledger_extras.ndjson`

要求：

- settings 保留 singleton key、version、settings payload。
- background jobs 保留 job id、type、status、owner、visibility、source、affected_months、progress、result_summary、error、attention。
- app health alerts 保留 alert id、kind、scope、severity、status、active/recovered timestamps。
- tax certified records 保留 certified unique key、invoice identity、tax amount、scope month、matched plan id。
- ETC 保留 invoice number、dates、amounts、status、batch ids、task id、business batch id、version、OA detection fields、file paths/hash。
- turnover 保留 relation id、bank transaction id、status、scope month、counterparty、amount、audit payload。
- historical ETC repair 保留 bundle/seed/state ids 和 file references。

Step 6：实现 read model exporter

新增：

- `backend/src/fin_ops_platform/tools/exporters/read_models.py`

输出文件：

- `workbench_read_models.ndjson`
- `workbench_candidate_matches.ndjson`
- `cost_statistics_read_models.ndjson`
- `tax_offset_read_models.ndjson`

要求：

- read model 标记 `rebuildable=true`。
- 保留 scope key、scope month、source_versions、generated_at、cache_status、payload。
- candidate matches 保留 candidate key、row ids、confidence、status。
- 本阶段不要求重建 read model，但要为阶段 04 对账保留 reference payload。

Step 7：实现 staging importer

新增：

- `backend/src/fin_ops_platform/tools/import_postgres_staging.py`

要求：

- 支持命令：
  - `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.import_postgres_staging --export-dir <export-dir> --dry-run`
  - `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.import_postgres_staging --export-dir <export-dir>`
- 读取 manifest 并校验每个文件 sha256。
- 验证 `public.schema_migrations` 包含 0001-0007 且 checksum 匹配阶段 02。
- 写入 `staging.mongo_exports`：
  - export_id
  - source_database
  - source_backup_archive
  - source_backup_sha256
  - status
  - manifest
  - raw_payload
- 将每条 NDJSON 写入 `staging.mongo_raw_records`：
  - export_id
  - source_collection
  - legacy_mongo_id
  - record_type
  - normalized_payload
  - raw_payload
- `--dry-run` 只校验文件和输出计划，不写 DB。
- 重复导入同一 export：
  - 已导入且 checksum 一致则跳过。
  - checksum 不一致则失败。
- 使用事务；任一文件失败时 rollback。
- 不打印完整 DB URI。

Step 8：测试

新增/更新测试：

- `tests/test_mongo_export_manifest.py`
- `tests/test_export_app_mongo.py`
- `tests/test_import_postgres_staging.py`

测试要求：

- manifest checksum、NDJSON 单行、目录覆盖保护。
- Decimal/datetime/Enum/Path 序列化。
- bytes/Binary 直接序列化阻断。
- fake store 下所有 exporter 能生成文件和 manifest。
- 核心对象 count 与 fake store 一致。
- 金额不输出 float。
- 空集合仍生成文件或 manifest 标记。
- staging importer dry-run 不写 DB。
- staging importer 校验 checksum drift。
- staging importer 重复导入幂等。
- 缺少 DATABASE_URL 或 PostgreSQL 连接配置时报清晰错误。
- 不泄漏完整 URI 或密码。

必须运行：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_mongo_export_manifest tests.test_export_app_mongo tests.test_import_postgres_staging -v`
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`

Step 9：服务器 restore 库 dry-run 和导出

主线程串行执行，子代理不得执行服务器命令。

- SSH 登录服务器。
- 不输出或记录密码。
- 确认 `fin-ops.service` active。
- 确认 PostgreSQL `fin_ops` 中 0001-0007 applied。
- 确认 `staging.mongo_exports` 和 `staging.mongo_raw_records` 当前状态。
- 先针对阶段 01 restore DB `fin_ops_platform_app_restore_20260520013830` 执行 export dry-run。
- 对 restore DB 执行正式 export。
- 校验 restore export manifest/checksums/counts。
- 对 restore export 执行 staging importer dry-run。
- 对 restore export 执行 staging import。
- 校验 staging count 与 restore export manifest 一致。
- 如果 restore gate 失败，停止并记录 `BLOCKED`，不要对生产 app Mongo 导出。

Step 10：服务器生产 app Mongo 只读导出和 staging 导入

只有 Step 9 restore gate 通过后才能执行。

- 对生产 app Mongo `fin_ops_platform_app` 执行 export dry-run。
- 对生产 app Mongo 执行正式 export。
- 校验 production export manifest/checksums/counts。
- GridFS count/chunks/total length 与阶段 01 记录比对；如生产期间数据有新增，必须记录差异原因和当前只读统计。
- 对 production export 执行 staging importer dry-run。
- 对 production export 执行 staging import。
- 校验 `staging.mongo_exports` 有 production export 记录。
- 校验 `staging.mongo_raw_records` count 与 production manifest 总 NDJSON count 一致。
- 重复导入同一 production export，必须安全跳过或明确返回已导入。

Step 11：更新文档和 gate

更新 `docs/database-migration/03-normalized-export-staging-import.md`：

- 执行摘要。
- 子代理并行复核结果。
- 新增/修改文件。
- 本地测试命令和结果。
- restore export：
  - export_id
  - export path
  - manifest path
  - checksums
  - counts
  - staging import result
- production export：
  - export_id
  - export path
  - manifest path
  - checksums
  - counts
  - staging import result
- GridFS 抽样 checksum。
- `staging.mongo_exports` 和 `staging.mongo_raw_records` 后验 count。
- 是否触碰 OA Mongo：必须为未触碰。
- 阶段 03 gate：
  - `PASS`
  - `BLOCKED`
  - `READY_NOT_IMPORTED`，仅当代码和本地测试完成但服务器未执行时使用。

必要时更新：

- `docs/database-migration/README.md`
- `docs/index.md`

阶段 03 Gate：

`PASS` 条件：

- 阶段 02 gate 是 `PASS`。
- 导出命令不写 Mongo。
- restore export manifest/checksum/count 通过。
- restore staging import count 与 manifest 一致。
- production export manifest/checksum/count 通过。
- production staging import count 与 manifest 一致。
- 重复导入同一 export 安全跳过。
- GridFS manifest 和抽样 checksum 通过。
- 后端全量单测通过。
- 文档记录 export id、路径、counts、checksum、staging import result。
- 没有密码、token 或完整 URI 写入代码、文档或日志。

`BLOCKED` 条件：

- 发现导出需要写 Mongo 或修改索引。
- 任何连接尝试会触碰 OA Mongo。
- JSON/Decimal/datetime 序列化失败。
- manifest checksum 不一致。
- staging count 与 manifest 不一致。
- export 中出现不可解释的缺失核心 identity。
- GridFS count 或抽样 checksum 出现不可解释差异。
- 任何命令输出或文档包含密码、token 或完整 URI。

最终答复必须包含：

- 阶段 03 gate 状态。
- 修改的文件列表。
- 本地测试结果。
- 服务器是否执行 restore/production export 与 staging import。
- export path、manifest path、关键 counts 和 checksums。
- 是否触碰 OA Mongo：必须明确说明未触碰。
- 若未能完成，说明 BLOCKED 原因和下一步最小修复。
```
```
