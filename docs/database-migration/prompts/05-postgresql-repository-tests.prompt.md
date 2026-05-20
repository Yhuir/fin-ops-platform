# 05 阶段 Codex 执行 Prompt：PostgreSQL repository 层和测试

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 05：在 Python 后端加入 PostgreSQL repository/state store 接入层，使 app 能在 PostgreSQL 模式下读取和写入 app 自身业务数据，同时继续从 OA Mongo 只读读取 OA 数据。阶段 05 完成后，Mongo/default 模式必须保持现有行为和测试通过，Postgres 模式必须具备可验证的 contract tests、关键 API smoke、app readiness check 和阶段文档记录；但本阶段仍不得切换生产用户流量，不得启用 dual-write，不得修改或重启生产服务配置。

你必须遵守以下硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。阶段 05 只能保留/复用现有 OA 只读 adapter 行为；不得写入、建索引、修复、清洗、备份或迁移 OA Mongo。
2. app Mongo `fin_ops_platform_app` 不得写入。默认 Mongo/local 模式必须保持兼容；若需要读取 app Mongo 只允许通过现有测试或只读兼容验证，不得重导出、不得清理、不得改 schema/index。
3. PostgreSQL 生产库 `fin_ops` 已在阶段 04 承载迁移后的 app 数据。本阶段允许对生产 PostgreSQL 做只读 smoke；禁止对生产 PostgreSQL 执行业务写入 smoke，除非先创建专用测试库/临时 schema 并明确隔离。
4. 禁止修改生产服务配置、禁止重启 `fin-ops.service`、禁止切换生产运行 backend、禁止 shadow-read、禁止 dual-write。
5. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码或 prompt。所有 URI 输出必须脱敏。
6. 不得把业务 SQL 散落到 service 业务逻辑里。service 层应继续通过 state store/repository 边界访问数据。
7. 不得破坏 Mongo/default 模式。未配置 PostgreSQL 时，现有 `ApplicationStateStore`、本地测试、`python -m fin_ops_platform.app.main --check` 必须继续通过。
8. PostgreSQL 模式下所有 SQL 必须参数化；禁止用用户输入拼 SQL。只允许对受控 table/schema 名使用白名单拼接。
9. PostgreSQL 写路径必须有事务边界；失败应 rollback；version/expected_version 语义必须与现有服务错误语义兼容。
10. 文件读取必须兼容阶段 04 迁移后的 legacy reference，例如 `gridfs://...`。文件内容完整迁移可延期，但 metadata 和 legacy reference 不得丢。
11. 不修改前端 DTO、不改 API 返回结构，除非测试证明现有 DTO 已错误且先记录 BLOCKED。
12. 如果发现阶段 02 schema 或阶段 04 数据不足以支撑某 public state store method，不得静默 fallback 到 Mongo 写路径；必须记录 `BLOCKED` 或把该 method 明确实现为只读/未支持并证明没有被 Postgres mode smoke 调用。

阶段 04 已完成的事实：

- 阶段 04 gate：`PASS`。
- production export id：`fin_ops_app_export_20260519235526_5a233544`。
- source database：`fin_ops_platform_app`。
- manifest payload sha256：`54d14c2ee2c2f09e7fb7c62bd5a6729fbb7dad075c76180f2be3cf2dbc414152`。
- staging raw records：`15494`。
- PostgreSQL phase04 pre-backup：
  - dump path：`/data/backups/fin_ops/postgres_phase04_20260520081506/fin_ops_pre_phase04_20260520081506.dump`
  - sha256：`1700535833a79072094cea257f09a005be1723aa1b8b2c4b2a91ca68e165cecb`
- PostgreSQL transform status：`transformed`。
- `staging.id_mappings=15993`。
- reconciliation report status：`pass`。
- reconciliation mismatches：`[]`。
- local reconciliation JSON：`docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`。
- local reconciliation Markdown：`docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.md`。
- remote reconciliation JSON：`/data/exports/fin_ops/fin_ops_app_export_20260519235526_5a233544/stage04/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`。
- remote reconciliation Markdown：`/data/exports/fin_ops/fin_ops_app_export_20260519235526_5a233544/stage04/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.md`。
- 核心 PostgreSQL counts：
  - `app.import_batches=6`
  - `app.import_batch_rows=897`
  - `app.file_objects=445`
  - `app.import_files=31`
  - `app.invoices=391`
  - `app.bank_transactions=431`
  - `read_model.search_index_rows=822`
  - `read_model.workbench_candidate_matches=5274`
- 金额对账：
  - invoices：`count=391`，`amount_sum=2164926.230000`，`signed_amount_sum=2164926.230000`
  - bank transactions：`count=431`，`amount_sum=28428537.660000`，`signed_amount_sum=-338747.500000`
- GridFS manifest：`files=445`，`chunks=709`，`total_bytes=98716321`。
- 阶段 04 已解释 warnings：
  - 若干 `app.invoices.data_fingerprint` 在源 Mongo 中重复，阶段 04 已将重复组的可选 `data_fingerprint` 列置空，原始值保留在 `raw_payload.normalized_payload.data_fingerprint`。
  - 21 条 `import_files` 的 batch id 没有可证明的 `import_batches` mapping，阶段 04 已置空可选 FK 并保留 legacy/raw payload。
- `fin-ops.service` 阶段 04 前后均为 `active`，未重启。
- 阶段 04 后本地全量测试：`1125 passed, 5 skipped, 5 warnings, 7 subtests passed`。

阶段 02/03 已通过的事实：

- 阶段 02 gate：`PASS`，PostgreSQL database：`fin_ops`，PostgreSQL version：16.12。
- `public.schema_migrations` 0001-0007 已 applied。
- 阶段 03 gate：`PASS`，production staging import：`imported`，duplicate import：`skipped`。
- PostgreSQL staging 后验：`staging.mongo_exports=1`，`staging.mongo_raw_records=15494`。

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
- `web/README.md`
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
- `docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`

必须先读的代码：

- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- `backend/src/fin_ops_platform/services/oa_adapter.py`
- `backend/src/fin_ops_platform/app/main.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes/`
- `backend/src/fin_ops_platform/domain/models.py`
- `backend/src/fin_ops_platform/domain/enums.py`
- `backend/src/fin_ops_platform/postgres/migrate.py`
- `backend/src/fin_ops_platform/postgres/migrations/0001_extensions_and_schemas.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0002_core_imports_invoices_bank.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0003_workbench_relations_exceptions.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0004_oa_projection_sync.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0005_tax_etc_turnover_settings_jobs.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0006_read_models.sql`
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
- `backend/src/fin_ops_platform/services/background_job_service.py`
- `backend/src/fin_ops_platform/services/app_health_alert_service.py`
- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/services/search_service.py`
- `tests/test_state_store.py`
- `tests/test_app.py`
- `tests/test_import_api.py`
- `tests/test_import_file_service.py`
- `tests/test_workbench_api.py`
- `tests/test_search_api.py`
- `tests/test_postgres_migrations.py`
- `tests/test_postgres_transform.py`
- `tests/test_reconcile_postgres_migration.py`

工作方式要求：

- 使用 `superpowers:subagent-driven-development`。
- 先由主线程完成代码/文档基线阅读和总体计划，然后并行派发只读 explorer 子代理，最后由主线程或 worker 子代理分批实现。
- explorer 子代理只读，不允许写文件，不允许连接服务器。
- worker 子代理如写代码，必须明确 disjoint write set；子代理之间不得改同一文件。
- 主线程统一整合、跑全量测试、更新阶段文档。
- 遇到服务器操作：先 dry-run/只读 smoke，再执行；生产服务不重启、不改配置。

建议并行 explorer 分工：

1. Explorer A：完整梳理 `ApplicationStateStore` public methods、现有初始化路径、配置/env 使用、`app.main --check` 行为，输出 factory/Protocol 最小改动建议。
2. Explorer B：梳理 imports/invoices/bank/files 相关 service 如何调用 store，输出 PostgreSQL core repository 方法清单、DTO/dataclass mapper、文件 legacy reference 兼容点。
3. Explorer C：梳理 workbench/no OA/categories/read models/search 相关 service 调用，输出 read/write method、version 语义、API smoke 清单。
4. Explorer D：梳理 settings/jobs/health/tax/ETC/turnover 相关 service 调用，输出 read/write method、JSONB snapshot round-trip、ETC/file 方法清单。
5. Explorer E：梳理现有 tests/fixtures 和可复用测试数据库策略，输出 contract tests、integration skip 条件、最小 fixture 数据方案。

串行总流程：

Step 0：安全和现状确认

- 运行 `git status --short`，记录已有未提交修改，不得 revert 用户或前序阶段改动。
- 运行 `python -m pytest -q`，确认阶段 05 开始前基线；若失败，先判断是否与当前任务相关。
- 阅读上述文档和代码。
- 确认阶段 04 report `status=pass`。
- 确认 `backend/requirements.txt` 当前依赖；不要盲目新增依赖。
- 如果需要新增 PostgreSQL driver，优先考虑 `psycopg`，但必须先确认环境、测试和部署约束；新增依赖必须记录理由。

Step 1：设计 PostgreSQL mode 的边界

- 明确 storage backend 环境变量：
  - `FIN_OPS_APP_STORAGE_BACKEND=local_pickle|mongo|postgres`
  - `FIN_OPS_APP_READ_BACKEND=storage|mongo|postgres`
  - `DATABASE_URL`
  - `FIN_OPS_POSTGRES_CONNECT_TIMEOUT_SECONDS`
  - `FIN_OPS_POSTGRES_STATEMENT_TIMEOUT_MS`
- 默认行为必须保持现有 local/mongo 路径。
- PostgreSQL 配置缺失只阻断 PostgreSQL 模式，不阻断默认模式。
- 输出一份实施内联设计到阶段文档的执行记录草稿；不要等最后才补。

Step 2：实现连接、配置、factory

建议文件：

- Create：`backend/src/fin_ops_platform/services/postgres_connection.py`
- Create/Modify：`backend/src/fin_ops_platform/services/state_store_factory.py`
- Modify：`backend/src/fin_ops_platform/app/server.py`
- Modify if needed：`backend/src/fin_ops_platform/app/main.py`
- Test：`tests/test_app_postgres_mode.py`

必须实现：

- `PostgresSettings`：从 env/arg 解析 DB URL 和 timeout；输出/异常必须脱敏。
- PostgreSQL health check：`select 1`、`current_database()`、`schema_migrations` 0001-0007。
- factory：只在 `FIN_OPS_APP_STORAGE_BACKEND=postgres` 时初始化 Postgres store。
- 默认模式：不需要 `DATABASE_URL`，不 import/初始化 Postgres connection。
- `--check`：输出 backend、migration readiness、但不泄漏 URI/密码。

测试要求：

- 默认模式无 `DATABASE_URL` 仍通过。
- Postgres 模式缺 `DATABASE_URL` 报清晰错误。
- Postgres mode check 使用测试 DB 或 mock connection 验证。

Step 3：定义 state store Protocol 和 contract tests

建议文件：

- Create：`backend/src/fin_ops_platform/services/state_store_protocol.py`
- Create：`tests/test_state_store_contract.py`

必须覆盖：

- `state_store.py` 中所有被 service/API 使用的 public methods。
- 空值读取、写入后读取、覆盖更新、幂等保存、删除/清空方法。
- Mongo/local store 必须先通过 contract，证明 contract 与现有语义一致。
- Postgres store 后续必须跑同一 contract。

方法清单至少包括：

- `load()` / `save(payload)`
- app settings：`load_app_settings()` / `save_app_settings()`
- OA app-side state/cache：`load_oa_sync_state()` / `save_oa_sync_state()` / `load_manual_oa_imports()` / `save_manual_oa_imports()` / `add_manual_oa_imports()` / `remove_manual_oa_import()` / `load_oa_attachment_invoice_cache_entry()` / `save_oa_attachment_invoice_cache_entry()` / `clear_oa_attachment_invoice_cache()`
- imports/files：`store_import_file()` / `read_import_file()` / `delete_import_files()` / `import_session_exists()` / `import_file_exists()` / `import_batch_exists()` / `invoice_exists()` / `transaction_exists()`
- workbench：`load_workbench_pair_relations()` / `save_workbench_pair_relations()` / `load_workbench_read_models()` / `save_workbench_read_models()` / `load_workbench_candidate_matches()` / `save_workbench_candidate_matches()` / `save_workbench_matching_dirty_scopes()` / `save_workbench_overrides()` / `save_workbench_exception_cases()`
- categories/no OA/turnover/read models：`load_bank_transaction_categories()` / `save_bank_transaction_categories()` / `load_no_oa_bank_batches()` / `save_no_oa_bank_batches()` / `load_turnover_relations()` / `save_turnover_relations()` / `load_turnover_relation_audit_log()` / `save_turnover_relation_audit_log()` / `load_turnover_ledger_extras()` / `save_turnover_ledger_extras()` / `load_cost_statistics_read_models()` / `save_cost_statistics_read_models()` / `load_tax_offset_read_models()` / `save_tax_offset_read_models()`
- tax/ETC/jobs/health：`load_tax_certified_imports()` / `save_tax_certified_imports()` / `load_etc_state()` / `save_etc_state()` / `load_etc_reconciliation_state()` / `save_etc_reconciliation_state()` / `store_etc_reconciliation_file()` / `read_etc_reconciliation_file()` / `store_etc_invoice_file()` / `read_etc_invoice_file()` / `etc_invoice_file_exists()` / `delete_etc_invoice_file()` / `save_historical_etc_repair_bundle()` / `load_historical_etc_repair_bundle_metadata()` / `read_historical_etc_repair_bundle()` / `save_historical_etc_repair_parsed_seed()` / `load_historical_etc_repair_parsed_seeds()` / `load_historical_etc_repair_parsed_seed()` / `load_historical_etc_repair_states()` / `save_historical_etc_repair_states()` / `load_background_jobs()` / `save_background_jobs()` / `load_app_health_alerts()` / `save_app_health_alerts()`

如果实际 `state_store.py` 方法名和以上清单不同，以代码事实为准，不得猜测。

Step 4：实现 PostgresStateStore 和 repositories

建议文件：

- Create：`backend/src/fin_ops_platform/services/postgres_state_store.py`
- Create：`backend/src/fin_ops_platform/services/postgres_repositories/__init__.py`
- Create：`backend/src/fin_ops_platform/services/postgres_repositories/core.py`
- Create：`backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- Create：`backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- Create：`backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Create/Modify：`backend/src/fin_ops_platform/services/postgres_repositories/files.py`
- Test：`tests/test_postgres_state_store.py`

实现原则：

- 优先复用阶段 02 schema 和阶段 04 `raw_payload/normalized_payload`，避免重新定义业务结构。
- 读取时尽量恢复现有 service 期望的 payload/dataclass shape；不要改变 service/API DTO。
- 写入时使用事务和 upsert；保留 `created_at/updated_at/version` 语义。
- 对 JSONB snapshot 表，保证 round-trip：`save_x(load_x())` 不丢字段。
- 对 id mapping，读取 legacy 数据时可使用正式表 `legacy_mongo_id`、`raw_payload` 或 `staging.id_mappings`；不得依赖 app Mongo。
- 对可重建 read model，可先支持读取阶段 04 reference；真正重建可在后续步骤实现，但 Postgres mode smoke 必须可解释。

核心 repository 要求：

- imports/invoices/bank/files：
  - `import_session_exists` / `import_file_exists` / `import_batch_exists` / `invoice_exists` / `transaction_exists`
  - import history/load APIs 所需查询
  - `store_import_file` 写 `app.file_objects` 和 `app.import_files`
  - `read_import_file` 支持 `gridfs://...` legacy reference 或返回清晰的 deferred/unsupported error，由现有 service 能处理
- settings/jobs/health：
  - app settings round-trip
  - background jobs load/save/update
  - app health alerts load/save
- workbench/no OA/categories：
  - pair relations load/save
  - row overrides save/load
  - exception cases save/load
  - candidate matches load/save
  - dirty scopes save/load
  - no OA batches/events load/save
  - bank categories load/save
- tax/ETC/turnover：
  - tax certified imports load/save
  - ETC state and reconciliation state load/save
  - historical ETC repair metadata/read/save methods
  - turnover relations/events/extras load/save
- read models/search：
  - workbench snapshots/candidate matches load/save
  - cost statistics read models load/save
  - tax offset read models load/save
  - search rows load/search API smoke

Step 5：测试数据库和 integration fixture

建议：

- 使用 `FIN_OPS_TEST_DATABASE_URL` 作为测试库连接。
- 没有 `FIN_OPS_TEST_DATABASE_URL` 时，Postgres integration tests 必须 `skip`，不能失败。
- 测试库必须包含 `test` 字样，或要求 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`。
- 测试前对测试库 apply 0001-0007。
- 导入一个小型 fixture：
  - 可通过 SQL 直接插入最小 app/read_model/job/audit 数据。
  - 或复用阶段 04 transformer 的小样本计划。
  - 不得依赖生产 PostgreSQL 写入。
- 对生产 PostgreSQL 只允许只读 smoke：
  - count/readiness/check 查询
  - `PostgresStateStore` read-only 初始化
  - 不执行 save/delete/write API

Step 6：API smoke

建议文件：

- Create：`tests/test_app_postgres_mode.py`
- Modify existing API tests only if adding backend parametrization is minimal and does not change DTO assertions.

必须覆盖：

- app readiness/check in default mode。
- app readiness/check in Postgres mode using test DB。
- `/health`
- `/api/session/me`
- settings read
- background jobs read
- imports history/list read
- bank/details or bank transaction search read
- workbench single month/list read
- search read
- tax read smoke
- ETC read smoke

要求：

- 不修改前端 DTO。
- Postgres mode API smoke 能证明 service 初始化没有回落到 app Mongo 写路径。
- OA 相关 API 若需要 OA Mongo，应只读，并可在无 OA Mongo 测试凭据时 skip 或 mock adapter；不得写 OA。

Step 7：服务器只读验证

只在本地实现和测试通过后执行。

服务器只读验证建议命令：

```bash
ssh root@139.155.5.132 '<read-only commands>'
```

在服务器上允许：

- 检查 `fin-ops.service` 状态。
- 用生产 PostgreSQL `fin_ops` 做只读 `--check` 或只读 repository smoke。
- 查询 phase04 counts 和 reconciliation report。

在服务器上禁止：

- 修改 `/etc/systemd/system/fin-ops.service*`
- 修改 `/opt/fin-ops/fin-ops.env`
- 重启服务
- 写生产 PostgreSQL 业务表
- 写 app Mongo 或 OA Mongo

Step 8：文档更新

必须更新：

- `docs/database-migration/05-postgresql-repository-tests.md`

记录：

- 实现文件清单。
- Postgres driver 选择和理由。
- Contract/API tests 结果。
- 默认 Mongo 模式测试结果。
- PostgreSQL integration tests 是否运行；若未运行，原因和需要的环境变量。
- 服务器只读 smoke 结果。
- 未完成/延期的方法清单，必须说明是否阻断阶段 06。
- 阶段 05 gate：`PASS` 或 `BLOCKED`。

验收命令：

本地默认全量：

```bash
python -m pytest -q
python -m fin_ops_platform.app.main --check
```

Postgres integration（有测试库时）：

```bash
export FIN_OPS_TEST_DATABASE_URL='<redacted test database url>'
export FIN_OPS_ALLOW_POSTGRES_TEST_DB=1
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py -q
```

Postgres app check（有测试库或只读生产库时，URI 不得输出完整值）：

```bash
FIN_OPS_APP_STORAGE_BACKEND=postgres \
FIN_OPS_APP_READ_BACKEND=postgres \
DATABASE_URL='<redacted>' \
python -m fin_ops_platform.app.main --check
```

最终输出要求：

- 列出修改/新增文件。
- 列出测试命令和结果。
- 列出 Postgres integration 是否执行。
- 列出服务器只读 smoke 是否执行。
- 明确说明 OA Mongo 未写、app Mongo 未写、生产服务未重启/未改配置。
- 明确阶段 05 gate：`PASS` 或 `BLOCKED`。

Gate PASS 条件：

- Mongo/default 模式全量测试通过。
- PostgreSQL store contract tests 通过。
- PostgreSQL mode app readiness/check 通过。
- 关键 API smoke 在 Postgres mode 通过，或者未覆盖项被明确列为不阻断且阶段 06 前无需生产使用。
- OA Mongo 仍只读，未新增写 OA 路径。
- app Mongo 默认兼容，未写入生产 app Mongo。
- 所有新增 SQL 参数化。
- 错误日志、文档、测试输出不泄漏完整 URI/密码/token。
- 文件读取能兼容阶段 04 `gridfs://` legacy reference，或明确记录后续文件内容迁移 blocker。
- 阶段文档已更新。

Gate BLOCKED 条件：

- Mongo/default 模式被破坏。
- Postgres mode 需要 OA Mongo 写权限。
- 任一现有 service 调用的 public state store method 在 Postgres mode 未实现且无 safe error/skip。
- API DTO 与前端合约不兼容。
- 写路径缺事务或 version conflict 语义。
- 文件读取无法兼容阶段 04 legacy reference 且影响关键导入/ETC API。
- 生产服务配置被修改或服务被重启。
```
