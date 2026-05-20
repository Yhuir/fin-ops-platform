# 07 阶段 Codex 执行 Prompt：PostgreSQL domain repository 完整闭合

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 07：基于阶段 06 的 `PARTIAL` 结果，把剩余 PostgreSQL domain repository、domain mapper、JSONB hydration、event/history 表、局部增量写入语义和真实 API smoke 全部闭合，使阶段 06/07 合并后的 PostgreSQL mode 达到可进入后续 shadow/dual-write/cutover 阶段的前置条件。

阶段 07 完成后必须满足：

1. 默认 local/Mongo 模式全量测试通过。
2. 无 `FIN_OPS_TEST_DATABASE_URL` 时 PostgreSQL integration tests 安全 skip。
3. 有 disposable PostgreSQL test DB 或本地临时 PostgreSQL cluster 时，migrations、repository integration、state store contract、API smoke 全部通过。
4. `PostgresStateStore` 不再依赖 `app.app_settings state:<key>` 作为主要运行时写路径；关键 runtime domains 必须写正式表，并能从正式表恢复现有 service/API 所需 shape。
5. `load()["imports"]` 可被 `ImportNormalizationService.from_snapshot()` 消费。
6. `load()["file_imports"]` 可被 `FileImportService.from_snapshot()` 消费。
7. tax certified、ETC、historical ETC、jobs、health、turnover、workbench/read model 的 JSONB round-trip 不破坏 dataclass/Enum/Decimal/datetime 使用。
8. pair relation/no OA/category/turnover 等 event/history 表写入闭合。
9. `changed_case_ids`、`changed_row_ids`、`changed_scope_keys`、`changed_scope_months` 局部写入语义正确，不误删、不误全量替换。
10. 生产仍不切换、不重启、不 dual-write、不 shadow-write。生产 PostgreSQL 只允许只读 smoke。

重要说明：

- 现有 `docs/database-migration/07-shadow-dualwrite-production-cutover.md` 是后续 cutover 需求草案，但阶段 06 Gate 结果为 `PARTIAL`，所以本次 07 不能执行生产 shadow/dual-write/cutover。
- 本次 07 的目标是把阶段 06 未完成项闭合，并将 gate 推进到可支持后续 cutover prompt 的状态。
- 如果执行中发现需要 schema 变更才能完整支持正式 repository，必须先新增 0008 migration 和 migration tests，并只在 disposable test DB 上验证；生产 schema 变更只允许生成计划和只读检查，不得直接执行。

你必须使用子代理并行完成可并行任务：

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- 主线程负责最终代码修改、集成、测试、文档更新和 gate 判定。
- 子代理优先做只读代码阅读、测试设计或独立 worker patch；如果让 worker 写代码，必须明确文件所有权，避免多个 worker 修改同一文件。
- 所有子代理都必须遵守本 prompt 的安全约束。

硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. OA Mongo 只能继续作为现有 `MongoOAAdapter` 的只读源；本阶段不实现 OA 数据写回。
3. app Mongo `fin_ops_platform_app` 不得写入。可以作为只读兼容源或历史事实校验源，但不得重导出、清理、建索引或改 schema。
4. 生产 PostgreSQL `fin_ops` 只能做只读 smoke/count/schema/readiness 检查；不得在生产库做 destructive truncate、seed、contract write、API write smoke。
5. 所有 destructive integration test 必须使用 disposable PostgreSQL test DB。DB 名必须包含 `test`，否则必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；如果无法证明是 test DB，立即停止并记录 `BLOCKED`。
6. 优先使用本机临时 PostgreSQL cluster 跑真实 integration；如果本机 `initdb/pg_ctl/createdb/psql` 不可用，再使用 `FIN_OPS_TEST_DATABASE_URL`；两者都不可用时 integration tests 必须 skip，并记录未完成验证。
7. 禁止修改或重启生产 `fin-ops.service`；禁止修改生产运行配置；禁止切换生产 backend；禁止 shadow-read/dual-write/生产 cutover。
8. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码或 prompt。所有 URI 输出必须脱敏。
9. 不得把业务 SQL 散落到 app route/service 业务逻辑里。service 层继续通过 state store/repository 边界访问数据。
10. 默认 local/Mongo 模式必须保持现有行为。未配置 PostgreSQL 时，不得读取生产 `DATABASE_URL`，不得初始化 PostgreSQL connection，不得影响 `python -m pytest -q` 和 `app.main --check`。
11. PostgreSQL 模式下所有 SQL 必须参数化；禁止用用户输入拼 SQL。只允许对受控 schema/table 名使用白名单拼接。
12. PostgreSQL 写路径必须有事务边界；失败必须 rollback；version/expected_version 语义必须与现有 service 错误语义兼容。
13. 文件读取必须兼容阶段 04 迁移后的 legacy reference：
    - 旧 store：`gridfs://<file_id>/<name>`
    - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`
14. 不修改前端 DTO、不改 API 返回结构。若 PostgreSQL mode 需要 DTO 变化，先记录 `BLOCKED`，不要自行修改前端契约。
15. 如果发现阶段 02 schema 或阶段 04 数据不足以支撑某 public state store method，不得静默 fallback 到 Mongo 写路径；必须补 repository/schema/mapping，或记录明确 `BLOCKED`。

阶段 06 已完成事实：

- 阶段 06 Gate：`PARTIAL`。
- 已新增：
  - `tests/postgres_test_utils.py`
  - `tests/test_postgres_test_utils.py`
  - `tests/test_postgres_state_store_integration.py`
  - `tests/test_app_postgres_mode_integration.py`
- 已修改：
  - `backend/src/fin_ops_platform/services/postgres_connection.py`
  - `backend/src/fin_ops_platform/services/postgres_state_store.py`
  - `docs/database-migration/06-postgresql-integration-repository-closure.md`
- 阶段 06 已验证：
  - 无 `FIN_OPS_TEST_DATABASE_URL` 时：`4 passed, 5 skipped`
  - 临时本地 PostgreSQL cluster，库名 `fin_ops_stage06_test`：`5 passed`
  - 阶段相关测试：`28 passed, 5 skipped`
  - 本地全量测试：`1143 passed, 10 skipped`
  - 生产只读 smoke：`fin-ops.service active/running`，`public.schema_migrations` 为 `0001` 到 `0007`
- 生产只读 counts：
  - `app.import_batches=6`
  - `app.import_batch_rows=897`
  - `app.file_objects=445`
  - `app.import_files=31`
  - `app.invoices=391`
  - `app.bank_transactions=431`
  - `read_model.search_index_rows=822`

阶段 06 未完成、必须在阶段 07 闭合：

- 未拆出 `postgres_repositories/*.py` package；当前仍在 `PostgresStateStore` 内集中实现。
- `load()["imports"]` 和 `load()["file_imports"]` 仍未完整恢复 `ImportNormalizationService.from_snapshot()` / `FileImportService.from_snapshot()` 需要的 domain object shape。
- tax certified、ETC、historical ETC 的正式表 mapper 和 JSONB dataclass hydration 仍未闭合。
- pair relation/no OA/category 的 history/event 表写入仍未完整闭合。
- `read_model.search_index_rows` 仍主要作为迁移/预留表，app search smoke 尚未覆盖正式 search index repository。
- `changed_case_ids`、`changed_row_ids`、`changed_scope_keys`、`changed_scope_months` 的删除/局部更新语义仍需深化。

阶段 04 已完成事实：

- 阶段 04 Gate：`PASS`。
- production export id：`fin_ops_app_export_20260519235526_5a233544`。
- source database：`fin_ops_platform_app`。
- manifest payload sha256：`54d14c2ee2c2f09e7fb7c62bd5a6729fbb7dad075c76180f2be3cf2dbc414152`。
- PostgreSQL transform status：`transformed`。
- `staging.id_mappings=15993`。
- reconciliation report status：`pass`。
- reconciliation mismatches：`[]`。
- local reconciliation JSON：`docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`。
- local reconciliation Markdown：`docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.md`。
- GridFS manifest：`files=445`，`chunks=709`，`total_bytes=98716321`。
- 阶段 04 warning 已解释：
  - 若干 `app.invoices.data_fingerprint` 在源 Mongo 中重复，阶段 04 已将重复组的可选 `data_fingerprint` 列置空，原始值保留在 `raw_payload.normalized_payload.data_fingerprint`。
  - 21 条 `import_files` 的 batch id 没有可证明的 `import_batches` mapping，阶段 04 已置空可选 FK 并保留 legacy/raw payload。

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
- `docs/database-migration/04-staging-transform-reconciliation.md`
- `docs/database-migration/05-postgresql-repository-tests.md`
- `docs/database-migration/06-postgresql-integration-repository-closure.md`
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md`
- `docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`

必须先读的代码：

- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/postgres_connection.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/state_store_protocol.py`
- `backend/src/fin_ops_platform/services/imports.py`
- `backend/src/fin_ops_platform/services/import_file_service.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `backend/src/fin_ops_platform/services/workbench_exception_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- `backend/src/fin_ops_platform/services/workbench_read_model_service.py`
- `backend/src/fin_ops_platform/services/workbench_candidate_match_service.py`
- `backend/src/fin_ops_platform/services/search_service.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_service.py`
- `backend/src/fin_ops_platform/services/tax_offset_service.py`
- `backend/src/fin_ops_platform/services/etc_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `backend/src/fin_ops_platform/services/historical_etc_repair_service.py`
- `backend/src/fin_ops_platform/services/turnover_relation_service.py`
- `backend/src/fin_ops_platform/services/background_job_service.py`
- `backend/src/fin_ops_platform/services/app_health_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/domain/models.py`
- `backend/src/fin_ops_platform/domain/enums.py`
- `backend/src/fin_ops_platform/postgres/migrations/0002_core_imports_invoices_bank.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0003_workbench_relations_exceptions.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0005_tax_etc_turnover_settings_jobs.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0006_read_models.sql`
- `tests/postgres_test_utils.py`
- `tests/test_postgres_state_store_integration.py`
- `tests/test_app_postgres_mode_integration.py`
- `tests/test_state_store_contract.py`

启动步骤：

1. 先运行基线：
   - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py -q`
   - `python -m pytest -q`
2. 检查是否能启动本机临时 PostgreSQL：
   - `command -v initdb && command -v pg_ctl && command -v createdb && command -v psql`
3. 如果可用，创建临时 cluster 和 `fin_ops_stage07_test`，运行真实 integration；测试结束必须 stop cluster 并删除 temp dir。
4. 如果不可用，检查 `FIN_OPS_TEST_DATABASE_URL`；无 test DB 时 integration tests 必须 skip，不能把 skip 当 PASS。
5. 使用子代理并行完成以下只读梳理：
   - Explorer A：core imports/file imports mapper，输出 `ImportNormalizationService.from_snapshot()` 和 `FileImportService.from_snapshot()` 需要的 exact shape。
   - Explorer B：workbench/no OA/category/dirty scopes 局部写入和 event/history 语义。
   - Explorer C：tax/ETC/historical ETC dataclass hydration 和正式表字段映射。
   - Explorer D：read models/search index/freshness/source_versions 语义。
   - Explorer E：API smoke seed/endpoints/DTO，不触发 OA Mongo。
6. 主线程基于子代理摘要拆分 worker 或本地实现。不要让多个 worker 修改同一文件。

推荐文件结构：

- Create: `backend/src/fin_ops_platform/services/postgres_repositories/__init__.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/core.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/files.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_connection.py` only if transaction API needs extension.
- Modify: `tests/postgres_test_utils.py`
- Modify/Create: `tests/test_postgres_state_store_integration.py`
- Modify/Create: `tests/test_app_postgres_mode_integration.py`
- Modify/Create: `tests/test_postgres_repositories_core.py`
- Modify/Create: `tests/test_postgres_repositories_workbench.py`
- Modify/Create: `tests/test_postgres_repositories_read_models.py`
- Modify/Create: `tests/test_postgres_repositories_ops_tax_etc.py`
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md` only to mark production cutover still deferred if needed.
- Create: `docs/database-migration/07-postgresql-domain-repository-completion.md`

任务 7.0：安全基线和执行记录

- [ ] 读完必读文档和代码。
- [ ] 记录当前 git branch、git status。不要 revert 非本阶段改动。
- [ ] 运行基线测试。
- [ ] 创建或更新 `docs/database-migration/07-postgresql-domain-repository-completion.md`。
- [ ] 在文档中记录 06 Gate 为 `PARTIAL`，本 07 不执行生产 cutover。
- [ ] 确认没有任何命令触碰 `form_data_db.form_data`。

Acceptance:

- 文档存在并说明阶段边界。
- 基线失败时先诊断；若失败与当前阶段无关，记录并继续；若会影响 07，先修复。

任务 7.1：Repository package 拆分和事务边界

- [ ] 新建 `postgres_repositories` package。
- [ ] 将 SQL 访问从 `PostgresStateStore` 中逐步拆到 repository 类，但保持 public `PostgresStateStore` API 不变。
- [ ] 每个 repository 接收 `PostgresConnection` 或 transaction-like object，不直接读取环境变量。
- [ ] 所有跨表写入支持注入 transaction。
- [ ] 保留 `app.app_settings state:<key>` 作为兼容 fallback，但正式表优先读取和写入。
- [ ] 为 repository 写轻量 unit tests，使用 fake connection 验证参数化 SQL 和事务调用顺序。

Acceptance:

- 默认模式不变。
- `PostgresStateStore` public methods 仍满足 `ApplicationStateStoreProtocol`。
- 真实 integration 能证明正式表写入，不只证明 snapshot。

任务 7.2：Core imports / invoices / bank transactions / file imports mapper

Files:

- Modify/Create: `backend/src/fin_ops_platform/services/postgres_repositories/core.py`
- Modify/Create: `backend/src/fin_ops_platform/services/postgres_repositories/files.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Test: `tests/test_postgres_repositories_core.py`
- Test: `tests/test_postgres_state_store_integration.py`
- Test: `tests/test_app_postgres_mode_integration.py`

Steps:

- [ ] 阅读 `ImportNormalizationService.from_snapshot()`，列出 `imports` snapshot exact shape。
- [ ] 阅读 `FileImportService.from_snapshot()`，列出 `file_imports` snapshot exact shape。
- [ ] 实现正式表到 domain-facing legacy id 的恢复：
  - `ImportedBatch.id = import_batches.legacy_mongo_id` 优先。
  - `Invoice.id = invoices.legacy_mongo_id` 优先。
  - `BankTransaction.id = bank_transactions.legacy_mongo_id` 优先。
  - `source_batch_id` / `legacy_source_batch_id` 必须恢复 legacy id。
  - `FileImportPreviewItem.id = import_files.legacy_mongo_id` 优先。
- [ ] `load()["imports"]` 返回 list/dict shape 必须可被 `ImportNormalizationService.from_snapshot()` 消费。
- [ ] `load()["file_imports"]` 返回 shape 必须可被 `FileImportService.from_snapshot()` 消费。
- [ ] `save(payload)` 对 `imports`、`file_imports` 写正式表，不只写 `state:full_state`。
- [ ] `store_import_file()`、`read_import_file()`、`delete_import_files()`、`import_file_exists()` 继续通过 06 integration。
- [ ] 增加 duplicate/idempotency tests：
  - invoice source_unique_key 不重复。
  - bank source_unique_key 不重复。
  - import file 重复保存不重复。
  - local delete 标记 deleted，GridFS ref 只标记不删除 legacy。
- [ ] 增加 transaction rollback test：batch 写入后故意失败，invoice/transaction 不应半写。

Acceptance:

- `ImportNormalizationService.from_snapshot(store.load()["imports"])` 在 real PostgreSQL integration 中通过。
- `FileImportService.from_snapshot(store.load()["file_imports"])` 在 real PostgreSQL integration 中通过。
- 核心正式表行数和 raw payload 在重复保存后稳定。

任务 7.3：Workbench / no OA / category / dirty scopes repository

Files:

- Modify/Create: `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Test: `tests/test_postgres_repositories_workbench.py`
- Test: `tests/test_postgres_state_store_integration.py`
- Test: `tests/test_app_postgres_mode_integration.py`

Steps:

- [ ] `workbench_pair_relations` 写 `app.workbench_pair_relations`，同时写 `app.workbench_pair_relation_history`。
- [ ] `workbench_row_overrides` 写 `app.workbench_row_overrides`，支持 `changed_row_ids` 局部 replace/delete。
- [ ] `workbench_exception_cases` 写 `app.workbench_exception_cases` 和 `app.workbench_exception_case_events`。
- [ ] `no_oa_bank_batches` 写 `app.no_oa_bank_batches` 和 `app.no_oa_bank_batch_events`。
- [ ] `bank_transaction_categories` 写 `app.bank_transaction_categories` 和 `app.bank_transaction_category_events`。
- [ ] `workbench_matching_dirty_scopes` 写 `job.workbench_matching_dirty_scopes`，`take_dirty_scopes()` 语义必须能通过 save 反映删除/处理。
- [ ] `changed_case_ids` 只更新指定 case，不全量替换。
- [ ] no OA submit/withdraw 与 pair relation、dirty scope 相关写入放入同一 transaction。
- [ ] category expected_version 语义保持，旧 version 重试必须 conflict。
- [ ] 测试 list/detail/submit/withdraw/category update 的 API DTO。

Acceptance:

- 重复保存同一 snapshot 不制造重复 rows/events，除非是明确的新业务 event。
- 局部写入不破坏未变数据。
- 真实 PostgreSQL API smoke 至少覆盖 no OA list/detail/submit 或 category update 的一个写路径。

任务 7.4：Read models / search index / freshness repository

Files:

- Modify/Create: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Test: `tests/test_postgres_repositories_read_models.py`
- Test: `tests/test_postgres_state_store_integration.py`
- Test: `tests/test_app_postgres_mode_integration.py`

Steps:

- [ ] `workbench_read_models` 写 `read_model.workbench_snapshots` 和必要的 `read_model.workbench_rows`。
- [ ] `workbench_candidate_matches` 写 `read_model.workbench_candidate_matches`；`changed_scope_months` 必须先删除对应月份旧 candidates，再插入新 candidates。
- [ ] `cost_statistics_read_models` 写 `read_model.cost_statistics_read_models`。
- [ ] `tax_offset_read_models` 写 `read_model.tax_offset_read_models`。
- [ ] `search_index_rows` 写 `read_model.search_index_rows`，或明确从 `workbench_snapshots` 派生并在文档中解释；若选择派生，API smoke 仍必须证明 PostgreSQL mode search 可用。
- [ ] 保持 source_versions freshness 语义：
  - workbench read model：expected versions 为空时存在即 fresh；不为空时逐 key 相等。
  - candidate match：expected versions 为空时 persisted `{}` 才 fresh；不为空时逐 key 相等。
- [ ] API smoke 覆盖 `/api/workbench?month=...` 和 `/api/search?q=...&month=...`。

Acceptance:

- Postgres mode 下 workbench/search DTO 与默认模式契约一致。
- 局部 scope 更新不误删其他月份/其他 scope。
- `source_versions` round-trip 后 freshness 判断不退化。

任务 7.5：Ops / tax / ETC / historical ETC / turnover repository

Files:

- Modify/Create: `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Test: `tests/test_postgres_repositories_ops_tax_etc.py`
- Test: `tests/test_postgres_state_store_integration.py`
- Test: `tests/test_app_postgres_mode_integration.py`

Steps:

- [ ] settings 继续写 `app.app_settings`，defaults merge 与 local store 一致。
- [ ] jobs 写 `job.background_jobs`，load 后 `BackgroundJobService` 能从 dict 还原。
- [ ] health alerts 写 `audit.app_health_alerts`，保持 `records` shape。
- [ ] tax certified import 写：
  - `app.tax_certified_import_sessions`
  - `app.tax_certified_import_batches`
  - `app.tax_certified_import_records`
- [ ] tax certified reload 后 `TaxCertifiedImportService` 的 confirm/list month 不因 dict/dataclass 退化报错。
- [ ] ETC state 写：
  - `app.etc_invoices`
  - `app.etc_import_sessions`
  - `app.etc_import_batches`
  - `app.etc_submission_batches`
  - `app.etc_business_batches`
- [ ] ETC reload 后 `EtcService` 的 list invoices、business batch/version conflict 路径不因 dict/dataclass 退化报错。
- [ ] ETC reconciliation 写：
  - `app.etc_reconciliation_tasks`
  - `app.etc_reconciliation_files`
  - `app.file_objects` FK。
- [ ] historical ETC repair 写：
  - `app.historical_etc_repair_bundles`
  - `app.historical_etc_repair_parsed_seeds`
  - `app.historical_etc_repair_states`
  - bundle file_object FK。
- [ ] turnover 写：
  - `app.turnover_relations`
  - `app.turnover_relation_events`
  - `app.turnover_ledger_extras`
- [ ] Decimal、datetime、Enum 必须 JSONB serialize/deserialize 一致。
- [ ] API smoke 覆盖：
  - `/api/tax-offset?month=...`
  - `/api/tax-offset/calculate`
  - 至少一个 ETC read endpoint 或 reconciliation task endpoint
  - `/api/background-jobs/active`
  - `/api/app-health`

Acceptance:

- 所有上述 service 在 Postgres mode 下 rebuild app 后仍可读已保存状态。
- 不触发 OA Mongo。
- DTO 不泄漏 DB URL/password。

任务 7.6：真实 PostgreSQL integration 和 API smoke 扩展

Files:

- Modify: `tests/postgres_test_utils.py`
- Modify: `tests/test_postgres_state_store_integration.py`
- Modify: `tests/test_app_postgres_mode_integration.py`

Steps:

- [ ] 增加 seed helpers：
  - `seed_core_imports_for_smoke`
  - `seed_file_import_session_for_smoke`
  - `seed_workbench_snapshot_for_smoke`
  - `seed_no_oa_batch_for_smoke`
  - `seed_tax_offset_for_smoke`
  - `seed_etc_state_for_smoke`
  - `seed_turnover_for_smoke`
- [ ] 每个 helper 必须只写 disposable DB，且每个 destructive helper 独立调用 test DB guard。
- [ ] 用 app factory 构造 Postgres mode app，不启动 HTTP server。
- [ ] 设置：
  - `FIN_OPS_APP_STORAGE_BACKEND=postgres`
  - `FIN_OPS_POSTGRES_DATABASE_URL=<test url>`
  - `FIN_OPS_TEST_DEFAULT_AUTH=1`
  - `FIN_OPS_DISABLE_STARTUP_HISTORICAL_ETC_REPAIR=1`
  - `FIN_OPS_OA_POLLING_ENABLED=0`
  - `FIN_OPS_WORKBENCH_MATCHING_DIRTY_WORKER_ENABLED=0`
- [ ] 临时 `data_dir` 不得含 `oa_mongo_config.json`。
- [ ] unset `FIN_OPS_OA_MONGO_*`、`FIN_OPS_STATE_MONGO_*`。
- [ ] 覆盖 read smoke：
  - `/health`
  - `/api/session/me`
  - `/api/app-health`
  - `/api/workbench/settings`
  - `/api/workbench?month=2026-03`
  - `/api/search?q=<seed keyword>&month=2026-03`
  - `/api/no-oa-bank-batches`
  - `/api/tax-offset?month=2026-01`
  - 一个 ETC/reconciliation read endpoint
- [ ] 覆盖 write smoke：
  - settings manual project round-trip
  - no OA submit/withdraw 或 bank category update
  - import file store/read/delete
- [ ] 每个写 smoke 后 rebuild app，再验证持久化 reload。

Acceptance:

- 有 real test DB 时新增 Postgres mode API smoke 全部通过。
- 无 real test DB 时 tests skip，不误用 production DB。

任务 7.7：生产只读 smoke 和文档 gate

Files:

- Create/Modify: `docs/database-migration/07-postgresql-domain-repository-completion.md`
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md` only if needed to mark cutover deferred.

Steps:

- [ ] 只读 SSH 检查 `fin-ops.service` 状态。
- [ ] 只读查询 `public.schema_migrations`。
- [ ] 只读查询核心 counts：
  - `app.import_batches`
  - `app.import_batch_rows`
  - `app.file_objects`
  - `app.import_files`
  - `app.invoices`
  - `app.bank_transactions`
  - `read_model.search_index_rows`
  - `read_model.workbench_candidate_matches`
- [ ] 记录脱敏结果，不写密码。
- [ ] 更新阶段 07 文档执行记录。
- [ ] 明确 Gate：`PASS` / `PARTIAL` / `BLOCKED`。

Acceptance:

- 生产只读 smoke 不修改任何业务表。
- 文档记录足以支撑下一阶段生成 shadow/dual-write/cutover prompt。

推荐验证命令：

```bash
python -m py_compile \
  backend/src/fin_ops_platform/services/postgres_connection.py \
  backend/src/fin_ops_platform/services/postgres_state_store.py \
  backend/src/fin_ops_platform/services/postgres_repositories/*.py
```

```bash
python -m pytest tests/test_postgres_test_utils.py -q
python -m pytest tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_state_store_contract.py -q
python -m pytest tests/test_postgres_repositories_core.py tests/test_postgres_repositories_workbench.py tests/test_postgres_repositories_read_models.py tests/test_postgres_repositories_ops_tax_etc.py -q
python -m pytest tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
python -m pytest -q
```

临时 PostgreSQL cluster 验证模板：

```bash
set -euo pipefail
TMPDIR_STAGE07="$(mktemp -d /tmp/finops-stage07-pg.XXXXXX)"
PORT="$(python - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)"
DATA_DIR="$TMPDIR_STAGE07/data"
LOG_FILE="$TMPDIR_STAGE07/postgres.log"
cleanup() {
  pg_ctl -D "$DATA_DIR" -m fast -w stop >/dev/null 2>&1 || true
  rm -rf "$TMPDIR_STAGE07"
}
trap cleanup EXIT
initdb -D "$DATA_DIR" -A trust -U postgres >/dev/null
pg_ctl -D "$DATA_DIR" -l "$LOG_FILE" -o "-F -p $PORT -h 127.0.0.1" -w start >/dev/null
createdb -h 127.0.0.1 -p "$PORT" -U postgres fin_ops_stage07_test
FIN_OPS_TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:$PORT/fin_ops_stage07_test" \
  python -m pytest tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
```

生产只读 smoke 模板：

```bash
ssh root@139.155.5.132 'systemctl is-active fin-ops.service && systemctl show -p ActiveState -p SubState -p ExecMainPID fin-ops.service'
```

```bash
ssh root@139.155.5.132 'su - postgres -c "psql -X -At -d fin_ops -v ON_ERROR_STOP=1 <<SQL
select version from public.schema_migrations order by version;
select '\''app.import_batches'\'', count(*) from app.import_batches
union all select '\''app.import_batch_rows'\'', count(*) from app.import_batch_rows
union all select '\''app.file_objects'\'', count(*) from app.file_objects
union all select '\''app.import_files'\'', count(*) from app.import_files
union all select '\''app.invoices'\'', count(*) from app.invoices
union all select '\''app.bank_transactions'\'', count(*) from app.bank_transactions
union all select '\''read_model.search_index_rows'\'', count(*) from read_model.search_index_rows
union all select '\''read_model.workbench_candidate_matches'\'', count(*) from read_model.workbench_candidate_matches;
SQL"'
```

Gate 判定：

`PASS` 条件：

- 默认 local/Mongo 全量测试通过。
- 无 test DB 时 integration tests 正确 skip。
- 有 test DB 或本地临时 PostgreSQL cluster 时，Postgres repository integration 和 API smoke 全部通过。
- `load()["imports"]`、`load()["file_imports"]` 可被对应 service `from_snapshot()` 消费。
- core/workbench/read_models/ops_tax_etc/files 的关键 runtime writes 写正式表并具备 transaction rollback tests。
- event/history 表写入闭合。
- 局部 changed ids/scope 语义有测试覆盖。
- tax/ETC/historical ETC JSONB round-trip 不破坏 service reload。
- legacy GridFS URI 兼容测试通过。
- 生产只读 smoke 通过并记录。
- OA Mongo 仍只读；未新增 OA 写路径。

`PARTIAL` 条件：

- 默认全量通过，但仍有一个或多个 repository domain 未完全 formal table round-trip。
- 真实 test DB 不可用且本机临时 PostgreSQL 也不可用，导致无法证明 integration。
- API smoke 只覆盖部分 domains。

`BLOCKED` 条件：

- 默认模式被 PostgreSQL 改动破坏。
- 真实 Postgres mode app 无法启动。
- 现有 schema 无法承载必要 runtime state，且不能安全新增 migration。
- API DTO 与现有前端契约不兼容。
- 任何 public state store method 缺实现且被 Postgres mode service 调用。
- 文件 legacy reference 无法读取或无清晰错误边界。
- test DB guard 无法防止误写生产。

最终输出要求：

1. 列出改动文件。
2. 列出测试命令和结果。
3. 列出生产只读 smoke 结果。
4. 明确 Gate 结果。
5. 如果 Gate 不是 `PASS`，列出剩余阻塞项和下一阶段建议。
6. 不输出任何密码、完整 URI、token 或 secret。
```
