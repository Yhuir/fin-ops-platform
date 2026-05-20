# 06 阶段 Codex 执行 Prompt：真实 PostgreSQL integration 和 repository 缺口闭合

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 06：基于阶段 05 已完成的 PostgreSQL 接入骨架，在真实 disposable PostgreSQL test DB 上验证 app 的 PostgreSQL mode，并闭合 repository 正式表写路径、事务边界、JSONB/domain mapper、文件兼容和关键 API smoke 缺口。阶段 06 完成后，默认 local/Mongo 模式必须全量测试通过；PostgreSQL mode 必须在真实测试库上通过 migrations、state store contract、repository integration 和关键 API smoke；生产服务仍不得切换，不得重启，不得写生产业务表，只允许生产只读 smoke。

你必须遵守以下硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. OA Mongo 只能作为现有 `MongoOAAdapter` 的只读源；阶段 06 不实现 OA 数据写回。
3. app Mongo `fin_ops_platform_app` 不得写入。可以作为只读兼容源或 fallback 验证源，但不得重导出、清理、建索引或改 schema。
4. 生产 PostgreSQL `fin_ops` 只能做只读 smoke/count/schema/readiness 检查；不得在生产库做 destructive truncate、seed、contract write、API write smoke。
5. 所有 destructive integration test 必须使用 disposable PostgreSQL test DB。DB 名必须包含 `test`，否则必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；如果无法证明是 test DB，立即停止并记录 `BLOCKED`。
6. 禁止修改或重启生产 `fin-ops.service`；禁止修改生产运行配置；禁止切换生产 backend；禁止 shadow-read/dual-write/生产 cutover。这些属于阶段 07。
7. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码或 prompt。所有 URI 输出必须脱敏。
8. 不得把业务 SQL 散落到 service 业务逻辑里。service 层继续通过 state store/repository 边界访问数据。
9. 默认 local/Mongo 模式必须保持现有行为。未配置 PostgreSQL 时，不得读取 `DATABASE_URL`，不得初始化 Postgres connection，不得影响 `python -m pytest -q` 和 `app.main --check`。
10. PostgreSQL 模式下所有 SQL 必须参数化；禁止用用户输入拼 SQL。只允许对受控 schema/table 名使用白名单拼接。
11. PostgreSQL 写路径必须有事务边界；失败必须 rollback；version/expected_version 语义必须与现有 service 错误语义兼容。
12. 文件读取必须兼容阶段 04 迁移后的 legacy reference：
    - 旧 store：`gridfs://<file_id>/<name>`
    - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`
    文件内容完整迁移可延期，但 metadata、reference parser 和清晰错误边界不得缺失。
13. 不修改前端 DTO、不改 API 返回结构。若 Postgres mode 需要 DTO 变化，先记录 `BLOCKED`，不要自行修改前端契约。
14. 如果发现阶段 02 schema 或阶段 04 数据不足以支撑某 public state store method，不得静默 fallback 到 Mongo 写路径；必须补 repository/schema/mapping，或记录明确 `BLOCKED`。

阶段 05 已完成事实：

- 阶段 05 gate：`PARTIAL`，不是最终迁移完成。
- 已新增：
  - `backend/src/fin_ops_platform/services/postgres_connection.py`
  - `backend/src/fin_ops_platform/services/postgres_state_store.py`
  - `backend/src/fin_ops_platform/services/state_store_factory.py`
  - `backend/src/fin_ops_platform/services/state_store_protocol.py`
  - `tests/test_state_store_contract.py`
  - `tests/test_postgres_state_store.py`
  - `tests/test_app_postgres_mode.py`
- 已修改：
  - `backend/src/fin_ops_platform/app/server.py` 通过 factory 创建 state store。
  - `backend/requirements.txt` 新增 `psycopg[binary,pool]==3.3.3`。
  - `docs/database-migration/05-postgresql-repository-tests.md` 记录执行结果。
- 阶段 05 已验证：
  - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py -q`
  - 结果：`14 passed, 5 warnings, 6 subtests passed`
  - `python -m pytest -q`
  - 结果：`1139 passed, 5 skipped, 5 warnings, 13 subtests passed`
  - `FIN_OPS_DATA_DIR=<temp> PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
  - 结果：`status=ready`，`storage.backend=local_pickle`，`storage.mode=auto`
- 阶段 05 的主要缺口：
  - 未用真实 `FIN_OPS_TEST_DATABASE_URL` 跑 PostgreSQL integration。
  - `PostgresStateStore` 写路径多数仍落 `app.app_settings state:<key>` JSONB snapshot，尚未完整写入正式领域表。
  - 多表业务 mutation 缺少显式事务上下文。
  - API smoke 只覆盖 readiness/factory 层，尚未覆盖真实 Postgres mode 下的 workbench/search/no OA/tax/ETC/import/file DTO。
  - 阶段 04 导入的正式表数据尚未通过 app service mapper 做端到端验证。
  - 生产服务器只读 smoke 尚未执行。

阶段 04 已完成事实：

- 阶段 04 gate：`PASS`。
- production export id：`fin_ops_app_export_20260519235526_5a233544`。
- source database：`fin_ops_platform_app`。
- manifest payload sha256：`54d14c2ee2c2f09e7fb7c62bd5a6729fbb7dad075c76180f2be3cf2dbc414152`。
- PostgreSQL phase04 pre-backup：
  - dump path：`/data/backups/fin_ops/postgres_phase04_20260520081506/fin_ops_pre_phase04_20260520081506.dump`
  - sha256：`1700535833a79072094cea257f09a005be1723aa1b8b2c4b2a91ca68e165cecb`
- PostgreSQL transform status：`transformed`。
- `staging.id_mappings=15993`。
- reconciliation report status：`pass`。
- reconciliation mismatches：`[]`。
- local reconciliation JSON：`docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`。
- local reconciliation Markdown：`docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.md`。
- 核心 PostgreSQL counts：
  - `app.import_batches=6`
  - `app.import_batch_rows=897`
  - `app.file_objects=445`
  - `app.import_files=31`
  - `app.invoices=391`
  - `app.bank_transactions=431`
  - `read_model.search_index_rows=822`
  - `read_model.workbench_candidate_matches=5274`
- GridFS manifest：`files=445`，`chunks=709`，`total_bytes=98716321`。
- 阶段 04 已解释 warnings：
  - 若干 `app.invoices.data_fingerprint` 在源 Mongo 中重复，阶段 04 已将重复组的可选 `data_fingerprint` 列置空，原始值保留在 `raw_payload.normalized_payload.data_fingerprint`。
  - 21 条 `import_files` 的 batch id 没有可证明的 `import_batches` mapping，阶段 04 已置空可选 FK 并保留 legacy/raw payload。

阶段 02/03 已通过事实：

- 阶段 02 gate：`PASS`，PostgreSQL database：`fin_ops`，PostgreSQL version：16.12。
- `app.schema_migrations` 0001-0007 已 applied。
- 阶段 03 gate：`PASS`，production staging import：`imported`，duplicate import：`skipped`。
- PostgreSQL staging 后验：`staging.mongo_exports=1`，`staging.mongo_raw_records=15494`。

服务器信息：

- 主机 IP：`139.155.5.132`
- 用户：`root`
- 协议：SSH
- 密码不得写入 prompt、文档、命令历史或日志；执行时由用户安全提供或使用已有 SSH 凭据。

必须先读的文档：

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `backend/README.md`
- `docs/index.md`
- `docs/dev/index.md`
- `docs/dev/backend.md`
- `docs/dev/testing.md`
- `docs/database-migration/README.md`
- `docs/database-migration/00-current-state-inventory.md`
- `docs/database-migration/code-evidence-index.md`
- `docs/database-migration/01-target-postgresql-design.md`
- `docs/database-migration/02-postgresql-schema-migration.md`
- `docs/database-migration/03-normalized-export-staging-import.md`
- `docs/database-migration/04-staging-transform-reconciliation.md`
- `docs/database-migration/05-postgresql-repository-tests.md`
- `docs/database-migration/06-postgresql-integration-repository-closure.md`
- `docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`

必须先读的代码：

- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/postgres_connection.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/state_store_protocol.py`
- `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- `backend/src/fin_ops_platform/app/main.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/domain/models.py`
- `backend/src/fin_ops_platform/domain/enums.py`
- `backend/src/fin_ops_platform/postgres/migrate.py`
- `backend/src/fin_ops_platform/postgres/migrations/0001_extensions_and_schemas.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0002_core_imports_invoices_bank.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0003_workbench_relations_exceptions.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0004_oa_projection_sync.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0005_tax_etc_turnover_settings_jobs.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0006_read_models.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0007_grants.sql`
- `backend/src/fin_ops_platform/tools/postgres_transform.py`
- `backend/src/fin_ops_platform/tools/transform_staging_to_postgres.py`
- `backend/src/fin_ops_platform/tools/reconcile_postgres_migration.py`
- `backend/src/fin_ops_platform/services/imports.py`
- `backend/src/fin_ops_platform/services/import_file_service.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `backend/src/fin_ops_platform/services/workbench_exception_case_service.py`
- `backend/src/fin_ops_platform/services/workbench_read_model_service.py`
- `backend/src/fin_ops_platform/services/workbench_candidate_match_service.py`
- `backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_service.py`
- `backend/src/fin_ops_platform/services/etc_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `backend/src/fin_ops_platform/services/historical_etc_repair_service.py`
- `backend/src/fin_ops_platform/services/background_job_service.py`
- `backend/src/fin_ops_platform/services/app_health_alert_service.py`
- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/services/search_service.py`
- `tests/test_state_store.py`
- `tests/test_state_store_contract.py`
- `tests/test_postgres_state_store.py`
- `tests/test_app_postgres_mode.py`
- `tests/test_postgres_migrations.py`
- `tests/test_postgres_transform.py`
- `tests/test_reconcile_postgres_migration.py`
- `tests/test_import_api.py`
- `tests/test_import_file_service.py`
- `tests/test_workbench_api.py`
- `tests/test_search_api.py`

工作方式要求：

- 使用 `superpowers:subagent-driven-development`。
- 先由主线程完成安全检查、文档/代码基线阅读、任务拆分。
- 并行派发 explorer 子代理做只读梳理；explorer 子代理不得写文件、不得连接服务器、不得连接数据库。
- 可并行派发 worker 子代理实现不重叠 write set；每个 worker 必须明确文件所有权，不得 revert 他人修改。
- 主线程负责整合、冲突处理、全量测试、生产只读 smoke 和阶段文档更新。
- 如果发现当前 worktree 有用户或前序阶段未提交修改，不得 revert；必须在这些改动基础上继续。

建议并行 explorer 分工：

1. Explorer A：真实 PostgreSQL test fixture 和 migration runner。
   - 只读文件：`postgres/migrate.py`、`tests/test_postgres_migrations.py`、阶段 02/03/04/06 文档。
   - 输出：test DB guard、apply migrations、truncate/seed helper 的最小实现方案。
2. Explorer B：core repository。
   - 只读文件：`imports.py`、`import_file_service.py`、`domain/models.py`、0002 SQL、`postgres_transform.py`、阶段 04 report。
   - 输出：imports/invoices/bank/file mapper、legacy id 恢复、GridFS URI 兼容和 contract tests。
3. Explorer C：workbench/read model repository。
   - 只读文件：workbench/no OA/category/read model/search services、0003/0006 SQL、相关 tests。
   - 输出：正式表写路径、version/source_versions 语义、API smoke。
4. Explorer D：ops/tax/ETC/turnover repository。
   - 只读文件：settings/jobs/health/tax/ETC/historical ETC/turnover services、0005 SQL、相关 tests。
   - 输出：JSONB dataclass/Enum/Decimal/datetime round-trip、正式表 mapping、事务风险。
5. Explorer E：API smoke 和前端 DTO 兼容。
   - 只读文件：`app/server.py` route dispatch、现有 API tests。
   - 输出：真实 Postgres mode 的最小 HTTP smoke、seed 数据、DTO 断言。

建议 worker 分工：

1. Worker 1：测试库 fixture 和 connection transaction。
   - Write set：
     - `backend/src/fin_ops_platform/services/postgres_connection.py`
     - `tests/postgres_test_utils.py`
     - `tests/test_postgres_state_store_integration.py`
2. Worker 2：core/files repository。
   - Write set：
     - `backend/src/fin_ops_platform/services/postgres_repositories/__init__.py`
     - `backend/src/fin_ops_platform/services/postgres_repositories/core.py`
     - `backend/src/fin_ops_platform/services/postgres_repositories/files.py`
     - corresponding parts of `postgres_state_store.py`
     - core/files tests
3. Worker 3：workbench/read model repository。
   - Write set：
     - `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
     - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
     - corresponding parts of `postgres_state_store.py`
     - workbench/read model integration tests
4. Worker 4：ops/tax/ETC/turnover repository。
   - Write set：
     - `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
     - corresponding parts of `postgres_state_store.py`
     - ops/tax/ETC/turnover integration tests
5. Worker 5：Postgres mode API smoke。
   - Write set：
     - `tests/test_app_postgres_mode_integration.py`
     - minimal reusable seed helpers in `tests/postgres_test_utils.py` only if coordinated with Worker 1

串行总流程：

Step 0：安全和基线确认

- 运行 `git status --short`，记录当前 dirty/untracked 文件。
- 不得 revert 用户或前序阶段修改。
- 运行：
  - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py -q`
  - `python -m pytest -q`
- 运行默认 check：
  - `FIN_OPS_DATA_DIR=$(mktemp -d) PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- 确认阶段 05 文档中的 gate 是 `PARTIAL`，本阶段目标是闭合该 gate。

Step 1：真实 PostgreSQL test DB fixture

建议文件：

- Create：`tests/postgres_test_utils.py`
- Create：`tests/test_postgres_state_store_integration.py`
- Modify：`tests/test_state_store_contract.py`

必须实现：

- `require_postgres_test_database_url()`：
  - 无 `FIN_OPS_TEST_DATABASE_URL` 时 skip integration tests。
  - URL 输出必须脱敏。
  - DB 名不含 `test` 且 `FIN_OPS_ALLOW_POSTGRES_TEST_DB != 1` 时 fail fast。
- migration apply helper：
  - 复用 `backend/src/fin_ops_platform/postgres/migrate.py` 或其内部 migration discovery/apply 逻辑。
  - apply 0001-0007 到 test DB。
- truncate helper：
  - 只允许在 guarded test DB 上执行。
  - truncate `audit`、`job`、`read_model`、`app`、`staging` schema 内测试表。
- minimal seed helper：
  - seed app settings/job/health。
  - seed import batch/invoice/bank transaction/file object/import file。
  - seed workbench/read model/search/no OA/tax/ETC/turnover 最小 rows。

验收：

- 无 `FIN_OPS_TEST_DATABASE_URL`：integration tests skip，不 fail。
- 有 test DB：migrations apply 成功，schema version 可查。
- guard 能阻止误写生产库。

Step 2：PostgresConnection 事务边界

建议文件：

- Modify：`backend/src/fin_ops_platform/services/postgres_connection.py`
- Test：`tests/test_postgres_state_store.py`
- Test：`tests/test_postgres_state_store_integration.py`

必须实现：

- `transaction()` context manager。
- transaction 内可多次 `execute/fetch_one/fetch_all`。
- 成功 commit。
- 异常 rollback。
- 支持 statement timeout。
- 不泄漏 URI。

验收：

- 单元测试验证 commit/rollback。
- integration 测试验证异常后 test table/目标表无部分写入。

Step 3：拆分正式表 repositories

建议新增目录：

- `backend/src/fin_ops_platform/services/postgres_repositories/`

建议文件：

- `__init__.py`
- `core.py`
- `files.py`
- `workbench.py`
- `read_models.py`
- `ops_tax_etc.py`

必须遵守：

- repositories 只处理 SQL/mapping，不改变 service 业务规则。
- 所有 SQL 参数化。
- table/schema 名如需动态必须白名单。
- 写正式表结构化列，同时写完整 `raw_payload.normalized_payload`。
- `app.app_settings state:<key>` 只能作为兼容 fallback，不得作为核心证明路径。

Step 4：Core/files repository closure

目标表：

- `app.import_batches`
- `app.import_batch_rows`
- `app.file_objects`
- `app.import_files`
- `app.invoices`
- `app.bank_transactions`
- `app.bank_transaction_categories`

必须实现：

- `PostgresStateStore.load()` 中 `imports` / `file_imports` 从正式表重建，优先恢复 legacy string ids。
- `ImportNormalizationService.from_snapshot()` 能消费 Postgres 重建的 snapshot。
- `FileImportService.from_snapshot()` 能消费 Postgres 重建的 snapshot。
- `store_import_file()` 写 `app.file_objects` 和 `app.import_files` metadata。
- `read_import_file()` 支持 app-owned local path 和两种 GridFS legacy URI。
- `delete_import_files()`：
  - app-owned local path 可物理删除。
  - legacy GridFS ref 只标记/删除 app 引用，不删除 GridFS content。
- `import_session_exists()`、`import_file_exists()`、`import_batch_exists()`、`invoice_exists()`、`transaction_exists()` 查询正式表。

测试：

- real DB seed 后 `load()["imports"]` 可初始化 `ImportNormalizationService`。
- real DB seed 后 `load()["file_imports"]` 可初始化 `FileImportService`。
- `store_import_file()` 后正式表可查 metadata。
- legacy GridFS URI parser 单元测试和 fake reader 测试通过。
- `delete_import_files()` 去重且不删除 legacy content。

Step 5：Workbench/read model repository closure

目标表：

- `app.workbench_pair_relations`
- `app.workbench_pair_relation_history`
- `app.workbench_row_overrides`
- `app.workbench_exception_cases`
- `app.workbench_exception_case_events`
- `app.no_oa_bank_batches`
- `app.no_oa_bank_batch_events`
- `job.workbench_matching_dirty_scopes`
- `read_model.workbench_rows`
- `read_model.workbench_snapshots`
- `read_model.workbench_candidate_matches`
- `read_model.search_index_rows`
- `read_model.cost_statistics_read_models`
- `read_model.tax_offset_read_models`

必须实现：

- `load/save_workbench_pair_relations()` 写正式表和 history event。
- `load/save_no_oa_bank_batches()` 写正式表和 event。
- `load/save_bank_transaction_categories()` 写正式表和 event。
- `save_workbench_overrides()` 写正式表。
- `save_workbench_exception_cases()` 写正式表。
- `load/save_workbench_read_models()` 写 `read_model.workbench_snapshots` / rows 或至少完整 payload 并保留 freshness。
- `load/save_workbench_candidate_matches()` 写 `read_model.workbench_candidate_matches`。
- `save_workbench_matching_dirty_scopes()` 写 `job.workbench_matching_dirty_scopes`。
- `load/save_cost_statistics_read_models()` 写 `read_model.cost_statistics_read_models`。
- `load/save_tax_offset_read_models()` 写 `read_model.tax_offset_read_models`。

测试：

- changed ids/scope 参数限制写入范围。
- 重复保存幂等。
- version/source_versions 语义保持。
- failure rollback。

Step 6：Ops/tax/ETC/turnover repository closure

目标表：

- `app.app_settings`
- `job.background_jobs`
- `audit.app_health_alerts`
- `app.tax_certified_import_sessions`
- `app.tax_certified_import_batches`
- `app.tax_certified_import_records`
- `app.etc_invoices`
- `app.etc_import_sessions`
- `app.etc_import_batches`
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

必须实现：

- settings 默认 shape 与 `ApplicationStateStore.load_app_settings()` 一致。
- background jobs 保存/读取不泄漏敏感字段，service payload `type` 与 SQL `job_type` 显式映射。
- app health alerts 保持 `{"records": ...}` shape。
- tax certified counters/sessions/batches/records round-trip。
- ETC state、ETC reconciliation state、historical ETC repair bundle/seed/state round-trip。
- `store_etc_reconciliation_file()`、`store_etc_invoice_file()` 写 `app.file_objects` 或对应 file table metadata。
- turnover relation/extras 保存完整 relation，不因正式表单字段丢失多 row 信息。

测试：

- dataclass/Enum/Decimal/datetime JSONB round-trip。
- counters 不重复。
- 文件 metadata 可查。
- rollback 测试。

Step 7：真实 Postgres mode API smoke

建议文件：

- Create：`tests/test_app_postgres_mode_integration.py`
- Modify：`tests/postgres_test_utils.py`

必须用 real test DB seed 并启动 app：

- 设置：
  - `FIN_OPS_APP_STORAGE_BACKEND=postgres`
  - `FIN_OPS_APP_READ_BACKEND=postgres`
  - `DATABASE_URL=$FIN_OPS_TEST_DATABASE_URL`
  - `FIN_OPS_POSTGRES_DATABASE_URL=$FIN_OPS_TEST_DATABASE_URL` if needed
- 验证：
  - `GET /health`
  - `GET /api/session/me`
  - `GET /api/workbench/settings`
  - `GET /api/background-jobs/active`
  - `GET /api/workbench?month=<known-month>`
  - `GET /api/search?q=<known-keyword>`
  - `GET /api/no-oa-bank-batches`
  - `GET /api/tax-offset`
  - `GET /api/etc/invoices`
  - `GET /api/etc/batches` if route exists and current app supports it
- 验证 response status 和核心 DTO 字段与现有默认模式契约一致。
- 不触发 OA Mongo 写入。
- 输出不泄漏 DB URL。

Step 8：生产只读 smoke

必须只读，不得重启服务，不得改配置。

可执行模板：

- `ssh root@139.155.5.132 'systemctl is-active fin-ops.service && systemctl show -p ActiveState -p SubState -p ExecMainPID fin-ops.service'`
- 只读 psql：
  - `select version from app.schema_migrations order by version;`
  - 核心 counts：
    - `app.import_batches`
    - `app.import_files`
    - `app.invoices`
    - `app.bank_transactions`
    - `read_model.search_index_rows`
    - `read_model.workbench_candidate_matches`
- 仅当服务器环境已有安全 Postgres URL 且不会写生产表时，执行 Postgres mode `--check`；否则记录未执行原因。

注意：

- 不要把 SSH 密码写进命令或文档。
- 不要在生产库执行 integration truncate/seed/write。
- 如果无法安全执行，只记录 `SKIPPED` 或 `BLOCKED`，不要绕过。

Step 9：更新文档和 gate

必须更新：

- `docs/database-migration/06-postgresql-integration-repository-closure.md`

记录：

- 实际执行的子代理分工。
- 新增/修改文件。
- test DB URL 脱敏标识，不写完整 URI。
- migrations apply 结果。
- integration tests 结果。
- API smoke 结果。
- 生产只读 smoke 结果。
- 未执行项和原因。
- gate 状态：`PASS` / `PARTIAL` / `BLOCKED`。

建议验证命令：

默认全量：

```bash
python -m pytest -q
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

PostgreSQL integration：

```bash
export FIN_OPS_TEST_DATABASE_URL='<redacted test db url>'
export FIN_OPS_ALLOW_POSTGRES_TEST_DB=1
export FIN_OPS_APP_STORAGE_BACKEND=postgres
export FIN_OPS_APP_READ_BACKEND=postgres
export DATABASE_URL="$FIN_OPS_TEST_DATABASE_URL"
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

最终 gate：

`PASS` 条件：

1. 默认 local/Mongo 全量测试通过。
2. 无 test DB 时 integration tests 正确 skip。
3. 有 test DB 时 PostgreSQL migrations、contract、repository integration、API smoke 全部通过。
4. 正式表写路径覆盖 core/workbench/read_models/ops_tax_etc/files 的关键 runtime writes。
5. 多表写入具备事务测试。
6. legacy GridFS URI 兼容测试通过。
7. 生产只读 smoke 通过并记录，或因权限/安全原因明确记录为 `SKIPPED` 且不影响 test DB gate。
8. OA Mongo 仍只读；未新增 OA 写路径。
9. 无 URI/密码/token 泄漏。

`PARTIAL` 条件：

- 默认模式和本地 fake tests 通过，但真实 test DB integration 未执行或部分未覆盖。
- repository 写路径仍主要依赖 `app.app_settings state:<key>` JSONB snapshot。
- API smoke 只覆盖部分 endpoint。

`BLOCKED` 条件：

- 默认模式被 PostgreSQL 改动破坏。
- 无法安全创建或确认 disposable test DB。
- 真实 Postgres mode 启动失败。
- API DTO 与现有前端契约不兼容。
- 任一 public state store method 缺实现且被现有 service 调用。
- 文件 legacy reference 无法读取或无清晰错误边界。
- test DB guard 无法防止误写生产。
- 任一流程需要写 OA Mongo。
```
