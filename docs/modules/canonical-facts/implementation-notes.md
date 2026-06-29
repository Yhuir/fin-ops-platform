# Canonical Facts 实施记录

## 2026-06-29 - Tool runtime state port closure

目标：

- 完成 canonical facts 剩余维护项中可安全执行的工具 runtime I/O 收口。
- 保留仍有 runbook 价值的 bank/ETC 运维工具。
- 删除旧 `full snapshot application` 语义，避免工具 adapter 暴露整个 `state_store`。

变更：

- `Application` 增加 `tool_runtime_state_snapshot()`，只返回 retained operational tools 初始化所需的局部 runtime state。
- `Application.tool_runtime_ports()` 不再暴露完整 `state_store`。
- `tools/runtime_application.py` 的 builder 改为 `build_tool_runtime_application(...)`。
- ETC historical migration/link/cleanup 工具改用新的 tool runtime builder。
- `test_canonical_fact_tools_use_runtime_application_state_io_boundary` 收紧，禁止旧 builder 名称和完整 `state_store` port 回归。

结果：

- retained operational tools 仍是运维工具，不是业务事实源。
- `runtime_application.py` 仍作为最小 app-owned tool-port adapter 存在；把它拆成各 owner CLI 现在会复制 `Application` 的依赖组装，收益低且风险高。
- canonical facts 没有新的 final closure blocker。后续仅在这些 runbook 退休时删除对应工具和 adapter。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/tools/runtime_application.py backend/src/fin_ops_platform/tools/link_existing_etc_batches.py backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py backend/src/fin_ops_platform/tools/cleanup_orphan_etc_reconciliation_tasks.py tests/test_migrate_historical_etc_business_batches_tool.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_migrate_historical_etc_business_batches_tool tests.test_link_existing_etc_batches_tool tests.test_restore_bank_auto_tag_rules_tool -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_tools_use_runtime_application_state_io_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

## 2026-06-29 - Coordinated GridFS worker deletion final closure

目标：

- 解除 08 canonical-facts final closure 的最后 blocker。
- 与 07 read-model/runtime worker ownership 同步删除 `file_object.gridfs_migration`，禁止半删。

变更：

- 删除 `runtime_worker_registry.py` 中的 `file-migration` registration。
- 删除 `app/worker.py` 的 `--enable-file-object-migration` 参数、handler wiring 和动态 event append。
- 删除 `file_object_migration.py` 中的 `LegacyGridFSFileReader`、`GridFSObjectMigrationService` 和 legacy GridFS Mongo config parsing；保留当前对象存储 helper。
- 删除 `deploy/oa/env/fin-ops.worker.file-migration*.env.example`，并从 RabbitMQ dispatcher env 与 staging preflight 中移除 `file_object.gridfs_migration`。
- 更新 canonical/runtime/deploy docs 和 guards，禁止 legacy GridFS worker path 回归。

结果：

- Canonical facts final closure 不再被 GridFS migration worker 阻塞。
- `legacy_gridfs_id` 表字段/索引仍作为历史 metadata/schema contract 保留，不再对应生产 worker source-of-truth path。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/worker.py backend/src/fin_ops_platform/services/runtime_worker_registry.py tests/test_platform_runtime_boundary_guards.py
```

## 2026-06-29 - Final audit blocked-partial (historical, superseded)

目标：

- 审计当前 08 可安全处理的旧 source-of-truth 删除面。
- 不修改 07 read-model controller 拥有的 runtime/read model 文件。
- 明确 final closure 不能成立的剩余前置条件。

结论：

- 07-owned read-model/runtime 文件在本切片无 diff。
- 旧 exporter/reconcile/staging/transform/import-consistency 路径在源码中只剩 removal guard 引用。
- 工具侧直接 `build_application(...)`、`Application._*`、`_state_store`、`_initialize_runtime_services` 访问已集中到 `tools/runtime_application.py`。
- `ApplicationStateStore` / local pickle 已接受为非生产 fixture/tooling I/O，不是 canonical facts source。
- Canonical facts 当时是 `blocked-partial`，后续已被 2026-06-29 coordinated GridFS worker deletion slice 解除。

剩余前置：

- 与 07 协调删除 `file_object.gridfs_migration` worker 注册、worker flag/handler、legacy GridFS migration service/config 和对应 docs/guards。
- 将 `tools/runtime_application.py` 上的 ETC/bank 运维工具迁移到 owner module ports，或在满足删除条件后删除工具。

验证：

```bash
git diff --name-only -- backend/src/fin_ops_platform/services/read_model_manifest.py backend/src/fin_ops_platform/services/read_model_scope_policy.py backend/src/fin_ops_platform/services/read_model_refresh_gateway.py backend/src/fin_ops_platform/services/read_model_query_gateway.py backend/src/fin_ops_platform/services/runtime_queue.py backend/src/fin_ops_platform/services/runtime_worker_registry.py backend/src/fin_ops_platform/services/operation_freshness_barrier.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py docs/architecture/module-boundaries/read-model-contracts.md docs/modules/read-models .planning/refactors/modular-io-boundaries/autonomous
rg -n "build_application\(|app\._|application\._|_state_store|_initialize_runtime_services|ApplicationStateStore|local_pickle|Mongo|mongo|GridFS|gridfs|state:" backend/src/fin_ops_platform/tools -g '*.py'
rg -n "reconcile_(workbench|cost_statistics|tax_offset)_read_model|fin_ops_platform\.tools\.exporters|ExportDefinition|gridfs_files_manifest|import_postgres_staging|transform_staging_to_postgres|postgres_transform|check_import_fact_consistency|reconcile_postgres_migration" backend/src tests -g '*.py'
```

## 2026-06-29 - Wave 6 tool runtime public port 边界收口

目标：

- 保留现有 bank/ETC 运维工具行为。
- 删除工具目录对 `Application._*`、`_state_store` 和 `_initialize_runtime_services` 的直接访问。
- 不修改 07 read-model controller 拥有的 runtime/read model 文件。

变更：

- `Application` 增加 `initialize_tool_runtime_state(...)` 和 `tool_runtime_ports()`，由 app 内部继续负责已有依赖组装。
- `tools/runtime_application.py` 改为只调用 public app tool ports。
- `test_canonical_fact_tools_use_runtime_application_state_io_boundary` 收紧为包含 `runtime_application.py` 在内的工具目录零 app-private I/O。
- ETC link/migration 工具测试 fake 改为模拟 `tool_runtime_ports()`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/tools/runtime_application.py tests/test_link_existing_etc_batches_tool.py tests/test_migrate_historical_etc_business_batches_tool.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_migrate_historical_etc_business_batches_tool tests.test_link_existing_etc_batches_tool tests.test_restore_bank_auto_tag_rules_tool -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_tools_use_runtime_application_state_io_boundary -v
rg -n "app\._|_state_store|_initialize_runtime_services|getattr\(app, \"_state_store\"" backend/src/fin_ops_platform/tools -g '*.py'
```

结果：通过；工具目录无 app-private I/O，唯一 `_state_store` 文本命中是 `PostgresStateStore` 类名。

## 2026-06-29 - Wave 6 final blocker audit (historical, superseded)

目标：

- 验证是否还有不触碰 07-owned runtime/read model 文件的旧 source-of-truth 删除面。

结论：

- 当时没有新的非 07 生产删除切片。
- 当时剩余生产 legacy path 只有 `file_object.gridfs_migration` worker。
- 该 blocker 已被 2026-06-29 coordinated GridFS worker deletion slice 解除。

证据：

- 该历史审计时 `runtime_worker_registry.py` 仍注册 `--enable-file-object-migration` / `file_object.gridfs_migration`。
- 该历史审计时 `app/worker.py` 仍在该 flag 下创建 `LegacyGridFSFileReader` 和 `GridFSObjectMigrationService`。
- 该历史审计时 `file_object_migration.py` 仍包含 legacy GridFS reader/migration service。
- 工具 app-private scan 已无 `app._`、`_state_store` 或 `_initialize_runtime_services` 访问；旧 reconcile/export/staging/transform/import-consistency markers 只剩 removal guard。

## 2026-06-29 - Wave 5 PostgresStateStore canonical facts state snapshot 删除

目标：

- 删除 `PostgresStateStore` 中 Workbench pair relations、workbench overrides、workbench exception cases、no-OA bank batches、bank transaction categories、Turnover relations、Turnover ledger extras、tax certified imports、pending invoice commands、manual OA imports、cost statistics read models 和 tax offset read models 的旧 `app.app_settings state:*` fallback/read-write 路径。
- 删除 `PostgresStateStore` 中 background jobs 和 app health alerts runtime/audit facts 的旧 `app.app_settings state:*` fallback/read-write 路径；正式来源分别是 `job.background_jobs` 和 `audit.app_health_alerts`。
- 删除 `PostgresStateStore` 中 ETC state / ETC reconciliation state 的旧 `app.app_settings state:*` fallback/read-write 路径；ETC counters 从正式 PostgreSQL 表推导。
- 删除 `PostgresStateStore` 中 OA sync state 的旧 `app.app_settings state:oa_sync_state` fallback/read-write 路径；state-store snapshot 写入 `app.oa_sync_watermarks` 的 `oa_sync_state` 行。
- 删除 `PostgresStateStore` 中 historical ETC repair bundle / parsed seed / state 的旧 `app.app_settings state:*` fallback/read-write 路径；正式来源是 `app.historical_etc_repair_*` 表。

变更：

- 对应 load 方法不再读取旧 `state:*` snapshot。
- 对应 save 方法不再写 `state:workbench_pair_relations`、`state:workbench_overrides`、`state:workbench_exception_cases`、`state:no_oa_bank_batches`、`state:bank_transaction_categories`、`state:turnover_relations`、`state:turnover_ledger_extras`、`state:tax_certified_imports`、`state:pending_invoice_commands`、`state:manual_oa_imports`、`state:cost_statistics_read_models`、`state:tax_offset_read_models`。
- runtime/audit save 方法不再写 `state:background_jobs` 或 `state:app_health_alerts`。
- ETC save 方法不再写 `state:etc_state` 或 `state:etc_reconciliation_state`。
- OA sync save 方法不再写任何 `state:*` key。
- Historical ETC repair save 方法不再写 `state:historical_etc_repair_bundles`、`state:historical_etc_repair_parsed_seeds` 或 `state:historical_etc_repair_states`。
- 新增 targeted regression tests 和 static guard，防止这些 canonical facts 方法重新调用 `_load_snapshot(...)` / `_save_snapshot(...)`。

边界：

- 这些业务事实的生产读写只走 PostgreSQL owner repositories：`PostgresWorkbenchRelationRepository` / `PostgresWorkbenchRepository`。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/services/state_store.py tests/test_postgres_state_store.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_store_snapshot_methods_round_trip_without_full_state_fallback tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_canonical_fact_snapshots_do_not_fallback_to_runtime_settings tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_canonical_fact_saves_do_not_write_runtime_settings_snapshots
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_postgres_canonical_fact_methods_do_not_use_runtime_settings_snapshots tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore Mongo runtime/helper 删除

目标：

- 删除 `ApplicationStateStore` 中已经不可达的 App Mongo runtime 字段、retry/helper、GridFS import-file 分支和 remaining detailed helper。

变更：

- `store_import_file(...)` / `read_import_file(...)` / `delete_import_files(...)` 只保留本地文件 I/O；旧 `gridfs://` import file 引用会被拒绝或忽略，不再读取 GridFS。
- `clear_oa_attachment_invoice_cache(...)`、import/file/batch/invoice/transaction existence helper、`load_pending_invoice_commands(...)` / `save_pending_invoice_commands(...)` 只保留本地 pickle/JSON I/O。
- 删除 `ApplicationStateStore` 内部 `_mongo_*` runtime 字段、Mongo retry helper、collection helper、remaining detailed load/save helper 和 fake Mongo state-store tests。
- 扩展 static guard，禁止 `MongoClient` / `GridFSBucket` / `PyMongoError` / `Binary` / `_mongo_*` runtime helper 回到 `ApplicationStateStore`。

边界：

- `ApplicationStateStore` 继续作为 local tooling/test store；生产 canonical facts 仍由 PostgreSQL owner repositories / business modules 管理。
- legacy GridFS Mongo 配置解析已移动到 `file_object_migration.py` 的迁移边界；`state_store.py` 不再暴露 App Mongo settings loader。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_store_import_file_round_trips_locally tests.test_state_store.StateStoreTests.test_pending_invoice_commands_persist_locally tests.test_state_store.StateStoreTests.test_oa_attachment_invoice_cache_save_load_and_clear_locally tests.test_state_store.StateStoreTests.test_save_no_oa_bank_batches_persists_and_loads_local_snapshot tests.test_state_store.StateStoreTests.test_app_health_alerts_save_and_load_local_snapshot
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_import_matching_snapshots_do_not_use_app_mongo
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore imports/file-imports/matching Mongo snapshot 删除

目标：

- 删除 `ApplicationStateStore.load()` / `save(...)` 以及 imports / file-imports / matching 旧 App Mongo detailed/split/legacy snapshot 路径。

变更：

- `load()` / `save(...)` 只保留本地 pickle I/O，不再读取 App Mongo detailed/split/legacy snapshot。
- 删除 imports、file-imports、matching 旧 detailed collection 常量、metadata 映射、full snapshot 聚合调用和 detailed load/save helper。
- 旧 Mongo snapshot 测试收敛为 local snapshot / local import file round-trip 测试，并新增 static guard 防止这些旧符号回归。

边界：

- 生产 imports / file-imports / matching canonical facts 仍由 PostgreSQL owner repositories / business modules 管理。
- 本切片只删除 local `ApplicationStateStore` 的旧 App Mongo snapshot 污染；不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_state_store_persists_and_loads_local_snapshot tests.test_state_store.StateStoreTests.test_state_store_load_ignores_app_mongo_config tests.test_state_store.StateStoreTests.test_store_import_file_round_trips_locally
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_import_matching_snapshots_do_not_use_app_mongo tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore Workbench read model Mongo branch 删除

目标：

- 删除 `ApplicationStateStore` 中 Workbench read models / candidate matches / matching dirty scopes 的旧 App Mongo 分支。

变更：

- `load_workbench_read_models(...)` / `save_workbench_read_models(...)` 只保留本地 pickle I/O。
- `load_workbench_candidate_matches(...)` / `save_workbench_candidate_matches(...)` 只保留本地 pickle I/O。
- `save_workbench_matching_dirty_scopes(...)` 只保留本地 pickle I/O。
- 删除旧 Workbench read model/candidate/dirty-scope detailed collection 常量、metadata 映射、full snapshot 聚合调用和 detailed load/save helper。
- 将旧 Mongo collection 测试收敛为本地 snapshot 测试，并新增 static guard。

边界：

- 生产 Workbench read model / candidate projection 仍由 PostgreSQL read model/repository owner 管理；本切片只删除 local `ApplicationStateStore` 的旧 App Mongo snapshot 污染。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_save_workbench_read_models_persists_and_loads_snapshot tests.test_state_store.StateStoreTests.test_save_workbench_read_models_accepts_changed_scopes_for_local_snapshot tests.test_state_store.StateStoreTests.test_save_workbench_candidate_matches_persists_locally_across_store_instances tests.test_state_store.StateStoreTests.test_save_workbench_candidate_matches_accepts_changed_months_for_local_snapshot tests.test_state_store.StateStoreTests.test_save_workbench_matching_dirty_scopes_persists_locally_across_store_instances -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_workbench_read_models_do_not_use_app_mongo tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore cost/tax read model Mongo branch 删除

目标：

- 删除 `ApplicationStateStore` 中 cost statistics / tax offset read model snapshot 的旧 App Mongo 分支。

变更：

- `load_cost_statistics_read_models(...)` / `save_cost_statistics_read_models(...)` 只保留本地 pickle I/O。
- `load_tax_offset_read_models(...)` / `save_tax_offset_read_models(...)` 只保留本地 pickle I/O。
- 删除旧 read model detailed collection 常量、metadata 映射、full snapshot 聚合调用和 detailed load/save helper。
- 将旧 Mongo incremental collection 测试收敛为本地 snapshot 测试，并新增 static guard。

边界：

- 生产 cost/tax read model projection 仍由 PostgreSQL read model/repository owner 管理；本切片只删除 local `ApplicationStateStore` 的旧 App Mongo snapshot 污染。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_save_cost_statistics_read_models_persists_locally_across_store_instances tests.test_state_store.StateStoreTests.test_save_cost_statistics_read_models_accepts_changed_scopes_for_local_snapshot tests.test_state_store.StateStoreTests.test_save_tax_offset_read_models_persists_locally_across_store_instances tests.test_state_store.StateStoreTests.test_save_tax_offset_read_models_accepts_changed_scopes_for_local_snapshot -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_cost_and_tax_read_models_do_not_use_app_mongo tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore Turnover facts Mongo branch 删除

目标：

- 删除 `ApplicationStateStore` 中 Turnover relations / ledger extras 的旧 App Mongo 分支。

变更：

- `load_turnover_relations(...)` / `save_turnover_relations(...)` 只保留本地 pickle I/O。
- `load_turnover_ledger_extras(...)` / `save_turnover_ledger_extras(...)` 只保留本地 pickle I/O。
- 删除旧 Turnover detailed collection 常量、metadata 映射、full snapshot 聚合调用和 detailed load/save helper。
- 将旧 Mongo-specific state store 测试收敛为本地 round-trip / audit-log 测试，并新增 static guard。

边界：

- 生产 Turnover canonical facts 仍由 PostgreSQL workbench repository / `PostgresStateStore` 管理。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_save_turnover_relations_persists_locally_across_store_instances tests.test_state_store.StateStoreTests.test_save_turnover_ledger_extras_persists_locally_across_store_instances -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_turnover_facts_do_not_use_app_mongo tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore bank transaction categories Mongo branch 删除

目标：

- 删除 `ApplicationStateStore` 中 bank transaction categories 的旧 App Mongo 分支。

变更：

- `load_bank_transaction_categories(...)` / `save_bank_transaction_categories(...)` 只保留本地 pickle I/O。
- 新增 static guard 和本地 round-trip 测试。

边界：

- 生产 bank transaction category facts 仍由 PostgreSQL workbench repository / service 管理。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_bank_transaction_categories_persist_locally_across_store_instances -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_bank_transaction_categories_do_not_use_app_mongo -v
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore workbench overrides Mongo branch 删除

目标：

- 删除 `ApplicationStateStore` 中 workbench overrides / exception cases 的旧 App Mongo 分支。

变更：

- `save_workbench_overrides(...)` / `save_workbench_exception_cases(...)` 只保留本地 pickle I/O。
- 旧 Mongo-specific tests 收敛为本地 store snapshot 测试。
- 新增 static guard。

边界：

- 生产 workbench overrides / exception cases facts 仍由 PostgreSQL workbench repository 管理。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_save_workbench_overrides_persists_local_snapshot tests.test_state_store.StateStoreTests.test_save_workbench_overrides_accepts_changed_rows_for_local_snapshot tests.test_state_store.StateStoreTests.test_save_workbench_exception_cases_persists_local_snapshot -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_workbench_overrides_do_not_use_app_mongo -v
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore workbench pair relations Mongo branch 删除

目标：

- 删除 `ApplicationStateStore` 中 workbench pair relations 的旧 App Mongo 分支。

变更：

- `load_workbench_pair_relations(...)` / `save_workbench_pair_relations(...)` 只保留本地 pickle I/O。
- 旧 Mongo-specific tests 收敛为本地 store round-trip / changed-case merge 测试。
- 新增 static guard。

边界：

- 生产 workbench pair relation facts 仍由 PostgreSQL workbench relation repository 管理。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_save_workbench_pair_relations_persists_and_loads_snapshot tests.test_state_store.StateStoreTests.test_save_workbench_pair_relations_can_incrementally_update_changed_case_only tests.test_state_store.StateStoreTests.test_save_workbench_pair_relations_persists_history_metadata -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_workbench_pair_relations_do_not_use_app_mongo -v
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore tax imports Mongo branch 删除

目标：

- 删除 `ApplicationStateStore` 中 tax certified imports / tax offset plan 的旧 App Mongo / mongo-only 分支。

变更：

- `load_tax_certified_imports(...)` / `save_tax_certified_imports(...)` 只保留本地 pickle I/O。
- `save_tax_offset_plan(...)` 不再检查 `MONGO_ONLY_STORAGE_MODE`。
- 新增 static guard 和本地 round-trip/idempotency 测试。

边界：

- 生产 tax facts 仍由 PostgreSQL `PostgresOpsTaxEtcRepository` / `PostgresStateStore` 管理。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_tax_imports_and_offset_plan_persist_locally -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_tax_imports_do_not_use_app_mongo -v
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore OA pending payment relation Mongo/full-snapshot branch 删除

目标：

- 删除 `ApplicationStateStore` 中 OA pending payment bank relations 的旧 App Mongo / whole snapshot 分支。

变更：

- `load_oa_pending_payment_bank_relations(...)` / `save_oa_pending_payment_bank_relations(...)` 只保留本地 pickle I/O。
- 新增 static guard 和本地 round-trip 测试。

边界：

- 生产事实源仍是 PostgreSQL `app.oa_pending_payment_bank_relations`。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_oa_pending_payment_bank_relations_persist_locally_across_store_instances -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_oa_pending_payment_bank_relations_do_not_use_app_mongo -v
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore no-OA bank batches Mongo branch 删除

目标：

- 删除 `ApplicationStateStore` 中 no-OA bank batches 的旧 App Mongo 分支。

变更：

- `load_no_oa_bank_batches(...)` / `save_no_oa_bank_batches(...)` 只保留本地 pickle I/O。
- 新增 static guard；行为复用已有本地 round-trip 测试。

边界：

- 不改变 `ApplicationStateStoreProtocol`。
- 不改变 PostgreSQL canonical facts owner repository。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_save_no_oa_bank_batches_persists_and_loads_local_snapshot -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_no_oa_bank_batches_do_not_use_app_mongo -v
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore jobs/health Mongo branch 删除

目标：

- 删除 `ApplicationStateStore` 中 background jobs 和 app health alerts 的旧 App Mongo 分支。

变更：

- `load_background_jobs(...)` / `save_background_jobs(...)` 只保留本地 pickle I/O。
- `load_app_health_alerts(...)` / `save_app_health_alerts(...)` 只保留本地 pickle I/O。
- 新增 static guard 和 background jobs 本地 round-trip 测试；app health 复用已有本地 round-trip 测试。

边界：

- 不改变 `ApplicationStateStoreProtocol`。
- 不改变 PostgreSQL canonical facts owner repository。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_background_jobs_persist_locally_across_store_instances tests.test_state_store.StateStoreTests.test_app_health_alerts_persist_locally_across_store_instances -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_jobs_and_health_do_not_use_app_mongo -v
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore historical ETC repair Mongo/GridFS branch 删除

目标：

- 删除 `ApplicationStateStore` 中 historical ETC repair bundle / parsed seed / repair state 的旧 App Mongo 和 GridFS 分支。

变更：

- `save_historical_etc_repair_bundle(...)` 只保留本地文件 bundle 写入，不再写 Mongo GridFS 或 Mongo detailed collection。
- `load_historical_etc_repair_bundle_metadata(...)`、`save_historical_etc_repair_parsed_seed(...)`、`load_historical_etc_repair_parsed_seeds(...)`、`load_historical_etc_repair_states(...)`、`save_historical_etc_repair_states(...)` 只保留本地 JSON I/O。
- `read_historical_etc_repair_bundle(...)` 遇到旧 `gridfs://` metadata 时明确失败。
- 删除 historical ETC repair GridFS id helper。
- 新增 static guard 和本地 round-trip 测试。

边界：

- 不改变 `ApplicationStateStoreProtocol`。
- 不改变 PostgreSQL canonical facts owner repository。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_historical_etc_repair_persists_locally_and_rejects_legacy_gridfs_refs -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_historical_etc_repair_does_not_use_app_mongo -v
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore ETC state Mongo branch 删除

目标：

- 删除 `ApplicationStateStore` 中 ETC state / ETC reconciliation state 的旧 App Mongo detailed collection 分支。

变更：

- `load_etc_state(...)` / `save_etc_state(...)` 只保留本地 pickle I/O。
- `load_etc_reconciliation_state(...)` / `save_etc_reconciliation_state(...)` 只保留本地 pickle I/O。
- 新增 static guard，禁止这四个方法重新引用 `_mongo_database`、`_mongo_detailed_collections` 或 `MONGO_ONLY_STORAGE_MODE`。
- 新增本地 round-trip 测试，证明该 local tooling/test store 仍可跨实例持久化 ETC 状态。

边界：

- 不改变 `ApplicationStateStoreProtocol`。
- 不改变 PostgreSQL canonical facts owner repository。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_etc_states_persist_locally_across_store_instances -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_etc_states_do_not_use_app_mongo tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 2026-06-29 - Wave 5 Workbench candidate repair tool 删除

目标：

- 删除会写旧 `app.app_settings state:workbench_candidate_matches` 的 repair 工具。

变更：

- 删除 `backend/src/fin_ops_platform/tools/repair_workbench_candidate_snapshot.py`。
- static guard 改为证明该工具不存在，且 app/services 不得引用该旧工具名。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_candidate_snapshot_repair_tool_is_removed -v
```

结果：通过。

## 2026-06-29 - Wave 5 Shadow-read rehearsal 删除

目标：

- 删除旧 App Mongo/local pickle shadow-read rehearsal 工具、底层 service 和 psql shadow-read store。

变更：

- 删除 `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`。
- 删除 `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`。
- 删除 `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`。
- 删除 `tests/test_shadow_read_rehearsal.py`。
- static guard 改为证明该 CLI/service 不存在，且 app/services 不得引用旧工具名。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_app_mongo_shadow_preflight_tools_are_removed -v
```

结果：通过。

## 2026-06-29 - Wave 5 Runtime policy / mirror 工具删除

目标：

- 删除剩余旧 App Mongo/local pickle runtime policy preflight 和 controlled mirror-write rehearsal CLI。

变更：

- 删除 `backend/src/fin_ops_platform/tools/run_runtime_state_policy_preflight.py`。
- 删除 `backend/src/fin_ops_platform/tools/run_controlled_mirror_write_rehearsal.py`。
- 删除 `tests/test_stage15_runtime_tools.py`。
- static guard 改为证明三条 shadow/preflight CLI 均不存在，且 app/services 不得引用旧工具名。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_app_mongo_shadow_preflight_tools_are_removed -v
```

## 2026-06-29 - Wave 5 Shadow / dual state-store 模块删除

目标：

- 删除旧 shadow/dual state-store 支撑模块，避免它们作为独立 legacy test/tooling 对象继续保留。

变更：

- 删除 `backend/src/fin_ops_platform/services/shadow_state_store.py`。
- 删除 `backend/src/fin_ops_platform/services/dual_state_store.py`。
- 删除 `tests/test_shadow_state_store.py`。
- 删除 `tests/test_dual_state_store.py`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_shadow_and_dual_state_store_modules_are_removed`。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_shadow_and_dual_state_store_modules_are_removed
```

结果：通过。

## 2026-06-29 - Wave 5 Cutover preflight checker 删除

目标：

- 删除旧 PostgreSQL cutover preflight checker / CLI，避免旧 cutover rehearsal 作为 canonical facts closure 的长期例外。

变更：

- 删除 `backend/src/fin_ops_platform/tools/verify_cutover_preflight.py`。
- 删除 `tests/test_cutover_preflight.py`。
- `backend/src/fin_ops_platform/services/cutover_preflight.py` 只保留通用 secret redaction helper；删除 `CutoverPreflightChecker`、`CutoverPreflightConfig` 和 `build_checker_from_env`。
- static guard 证明旧 CLI/checker/config 不存在且脱敏 helper 仍可用。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/cutover_preflight.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_cutover_preflight_checker_is_removed -v
```

结果：通过。

## 2026-06-29 - Wave 5 OA attachment audit cache write 删除

目标：

- 删除 OA attachment audit CLI 的旧 App state cache 写入开关。

变更：

- 删除 `--allow-cache-write`。
- 删除 `ApplicationStateStore(data_dir)` cache 注入。
- `MongoOAAdapter` 只以只读 OA settings 构造，不注入 old App state cache。
- static guard 改为证明该 CLI 没有 App state cache write path。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/oa_attachment_audit.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_attachment_audit_does_not_write_app_state_cache -v
```

结果：通过。

## 2026-06-29 - Wave 5 OA attachment audit 工具删除

目标：

- 删除无活跃命名审计任务依赖的 OA attachment audit 工具，避免 direct OA Mongo audit path 作为 permanent deferred tooling 保留。

变更：

- 删除 `backend/src/fin_ops_platform/tools/oa_attachment_audit.py`。
- 删除 `backend/src/fin_ops_platform/services/oa_attachment_audit.py`。
- 删除 `tests/test_oa_attachment_audit.py`。
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_oa_attachment_audit_tool_is_removed` 证明 app/tools/services/tests 中的该旧工具路径不能回归。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_attachment_audit_tool_is_removed
```

结果：通过。

## 2026-06-29 - Wave 5 State store factory shadow/dual 删除

目标：

- 删除 `state_store_factory` 中旧 shadow / dual preflight backend 构造入口。

变更：

- `FIN_OPS_APP_STORAGE_BACKEND=shadow` 不再构造 shadow wrapper。
- `FIN_OPS_APP_STORAGE_BACKEND=dual` 不再构造 dual wrapper。
- 删除 `FIN_OPS_PRIMARY_STORAGE_BACKEND` / `FIN_OPS_SHADOW_STORAGE_BACKEND` / `FIN_OPS_MIRROR_STORAGE_BACKEND` / `FIN_OPS_CUTOVER_PREFLIGHT_ONLY` 相关 factory 分支。
- `tests/test_state_store_factory_preflight.py` 改为证明 shadow / dual backend 被拒绝。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store_factory.py tests/test_state_store_factory_preflight.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store_factory_preflight -v
```

结果：通过。

## 2026-06-29 - Wave 5 State store factory postgres-only

目标：

- 删除 `state_store_factory.build_state_store(...)` 的默认 local / mongo / auto fallback。

变更：

- 未设置 `FIN_OPS_APP_STORAGE_BACKEND` 时不再构造 `ApplicationStateStore`。
- `auto` / `local` / `local_pickle` / `mongo` / `mongo_pickle` 均直接失败。
- 有 `data_dir` 的 app runtime 只接受 `FIN_OPS_APP_STORAGE_BACKEND=postgres`。
- `ApplicationStateStore` 本体暂时保留给直接测试和后续 local pickle implementation slice，不再由 factory 接入 app runtime。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store_factory.py tests/test_state_store_factory_preflight.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store_factory_preflight -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_default_requires_postgres_backend tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_production_guard_rejects_default_local_storage tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_production_guard_rejects_explicit_local_storage tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_postgres_mode_requires_database_url -v
PYTHONPATH=backend/src python3 -m unittest tests.test_app_postgres_mode.AppPostgresModeTests.test_default_build_application_requires_postgres_backend tests.test_app_postgres_mode.AppPostgresModeTests.test_postgres_backend_without_database_url_fails_clearly tests.test_app_postgres_mode.AppPostgresModeTests.test_readiness_includes_postgres_status_without_uri -v
```

结果：通过。

## 2026-06-29 - Wave 5 PostgreSQL GridFS read fallback 删除

目标：

- 删除 `PostgresStateStore` 文件读取路径里的 legacy GridFS fallback。

变更：

- 删除 `legacy_file_reader` constructor parameter。
- 删除 `FIN_OPS_ENABLE_LEGACY_GRIDFS_READS`。
- 删除 `_legacy_file_reader` runtime state。
- `read_import_file("gridfs://...")` 直接失败，要求先迁移到 verified object storage。
- static guard 禁止 PostgreSQL state store 恢复 legacy GridFS read fallback。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py tests/test_runtime_bootstrap.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_store_rejects_legacy_gridfs_reference tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_postgres_state_store_does_not_auto_configure_legacy_gridfs_reader tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime -v
```

结果：通过。

## 2026-06-29 - Wave 5 App Mongo export tool 删除

目标：

- 删除旧 App Mongo snapshot export 工具，避免 App Mongo export/audit fallback 继续作为 canonical facts closure 的 deferred path。

变更：

- 删除 `backend/src/fin_ops_platform/tools/export_app_mongo.py`。
- 删除 `tests/test_export_app_mongo.py`。
- static guard 改为证明旧 export 工具不存在，且 app/services 不得引用该旧工具名。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_app_mongo_export_tool_is_removed -v
```

结果：通过。

## 2026-06-28 - Wave 5 Workbench matching dirty scopes state snapshot 删除

目标：

- 删除 PostgreSQL runtime 对旧 `app.app_settings state:workbench_matching_dirty_scopes` JSON snapshot 的读写。

变更：

- `PostgresStateStore.save_workbench_matching_dirty_scopes(...)` 不再写 `app.app_settings`。
- `PostgresStateStore.load()` 返回空 dirty scopes snapshot，不再从旧 `state:*` key bootstrap。
- 正式 runtime 状态继续归 `job.workbench_matching_dirty_scopes`，本 slice 不编辑 07-owned read model runtime 文件。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_workbench_matching_dirty_scopes_do_not_use_runtime_snapshot -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 2026-06-29 - Wave 5 Matching state snapshot 写入删除

目标：

- 删除 `PostgresStateStore.save({"matching": ...})` 对旧 `app.app_settings state:matching` JSON snapshot 的写入。

变更：

- `PostgresStateStore.save(...)` 不再处理 `matching` 为 `_save_snapshot("matching", ...)`。
- 新增回归测试，证明保存 matching payload 后不会写旧 `state:matching`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_save_matching_does_not_write_runtime_snapshot tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_matching_does_not_fallback_to_runtime_snapshot -v
```

结果：通过。

## 2026-06-28 - Wave 5 Matching state snapshot 读取回退删除

目标：

- 删除 `PostgresStateStore._load_matching()` 对旧 `app.app_settings state:matching` JSON snapshot 的读取回退。

变更：

- Matching 读取只来自 PostgreSQL 正式表 `app.matching_runs` 和 `app.matching_results`。
- 新增回归测试，证明旧 `state:matching` 不会覆盖正式表结果。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_matching_does_not_fallback_to_runtime_snapshot -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

剩余：

- `save({"matching": ...})` 的旧 `state:matching` 写入已在后续 slice 删除。

## 2026-06-28 - Wave 5 ETC web legacy mutation 删除

目标：

- 删除前端对 legacy `/api/etc/batches*` list 和 mutation endpoint 的调用，避免页面继续通过旧兼容 API 写 ETC canonical facts。

变更：

- `web/src/features/etc/api.ts` 删除 `fetchEtcBatches`、`createEtcOaDraft`、`createEtcOaDraftForBatch`、`confirmEtcBatchSubmitted`、`markEtcBatchNotSubmitted` 和 `deleteEtcBatch`。
- `web/src/pages/EtcTicketManagementPage.tsx` 删除 `legacyBatch` delete plan，batch delete 只走 business-batches canonical API。
- 新增 static guard 禁止旧前端 list/mutation client 回归。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_web_etc_api_does_not_call_legacy_batch_mutations_or_list -v
cd web && npm test -- --run src/test/EtcApi.test.ts src/test/EtcTicketManagementPage.test.tsx
cd web && npm run build
```

结果：通过。

## 2026-06-28 - Wave 5 Application legacy snapshot bootstrap 删除

目标：

- 删除 `Application` app/API runtime 对 legacy full snapshot bootstrap 的装配和调用。

变更：

- `server.py` 不再 import 或实例化 `LegacySnapshotBootstrap`。
- `_runtime_bootstrap_state()` 不再因 `bootstrap_mode == "legacy"` 调用 full snapshot loader，始终返回空启动 state。
- 删除 `_load_persisted_state(...)`。
- readiness bootstrap summary 使用固定空 `legacy_snapshot` summary。
- static removal baseline 中 `server.py` 的 `load_full_snapshot` 引用数降为 0。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_runtime_bootstrap.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 2026-06-28 - Wave 5 ETC backend legacy batch API 删除

目标：

- 删除 backend legacy `/api/etc/batches*` 兼容 API 和它保护的旧 source-of-truth route/service 链路。

变更：

- 删除 `routes_etc_legacy_batches.py`。
- 删除 `etc_legacy_batch_read_facade.py`、`etc_legacy_batch_delete_service.py`、`etc_legacy_batch_lifecycle_service.py`。
- `server.py` 删除 legacy route dispatch、readiness entrypoints、`FIN_OPS_ENABLE_LEGACY_ETC_BATCH_API` gate、legacy factories 和 business-delete shim。
- 删除 `tests/test_etc_legacy_batch_*` service tests，并从 `tests/test_etc_backend.py` 删除直接保护 `/api/etc/batches*` 的旧 API tests。
- 保留有价值的 reconciliation-backed OA draft 回归，但改为 business-batches OA draft API。
- static guard 改为证明 legacy backend API 文件、server wiring 和 gate 都不存在。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_etc_batch_backend_api_is_removed tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_web_etc_api_does_not_call_legacy_batch_mutations_or_list tests.test_etc_backend.EtcApiTests.test_reconciliation_backed_oa_draft_uploads_supplements_and_uses_oa_total -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v
```

结果：通过；`tests.test_etc_backend` 118 个测试通过，4 个依赖本地票根样例的测试按既有 skip 条件跳过。

## 2026-06-28 - Wave 5 ETC imported task detail legacy read 删除

目标：

- 删除前端对 legacy `/api/etc/batches/{id}` batch detail 的读取依赖，为后端 legacy batch route/service 删除解除最后一个页面前置项。

变更：

- `fetchEtcBatchDetail(...)` 从 `web/src/features/etc/api.ts` 删除。
- `EtcTicketManagementPage` 已导入任务详情改用 `fetchEtcInvoices({ importBatchId, page: 1, pageSize: 500 })`，由页面使用 reconciliation task payload + canonical invoice list 组装 UI detail。
- `/api/etc/invoices` 增加 `importBatchId` / `import_batch_id` 查询参数并透传到 `EtcService.list_invoices(import_batch_id=...)`。
- 前端测试从旧 batch detail response mock 改为 canonical invoice list mock。
- static guard 禁止前端重新导出 `fetchEtcBatchDetail` 或旧 `/api/etc/batches/{id}` detail URL。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_invoices.py backend/src/fin_ops_platform/services/etc_service.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_web_etc_api_does_not_call_legacy_batch_mutations_or_list tests.test_etc_backend.EtcServiceTests.test_service_filters_invoices_by_import_batch_id -v
cd web && npm test -- --run src/test/EtcApi.test.ts src/test/EtcTicketManagementPage.test.tsx
cd web && npm run build
```

结果：通过；Vite build 仍有既有 CSS minify/chunk-size warning。

剩余：

- 后端 `routes_etc_legacy_batches.py` 和 `etc_legacy_batch_*` route/service/test 清理仍未完成。

剩余：

- `fetchEtcBatchDetail(...)` 仍为任务导入详情读取 `/api/etc/batches/{id}`；backend legacy route/service 仍 production-reachable，不能算 closure。

## 2026-06-28 - Wave 5 Worker OA Mongo 边界收紧

目标：

- 删除 worker 中不必要的 direct `MongoOAAdapter` 耦合，只保留 OA sync 外部输入源工厂。

变更：

- `_no_oa_workbench_matching_source_versions(...)` 改用 `attachment_invoice_cache_parser_version()`。
- worker 内部 adapter 缓存和 `_oa_payment_source_adapter()` 不再暴露 `MongoOAAdapter` 类型标注。
- static guard 将 worker `MongoOAAdapter` baseline 从 6 降到 2，并要求 direct construction 只存在于 `_build_oa_sync_source_adapter(...)`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/worker.py tests/test_platform_runtime_boundary_guards.py tests/test_worker_oa_sync.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_mongo_adapter_direct_use_is_allowlisted tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_worker_oa_mongo_adapter_is_confined_to_sync_source_factory -v
PYTHONPATH=backend/src python3 -m unittest tests.test_worker_oa_sync -v
```

结果：通过。

剩余：

- OA sync worker 仍保留唯一 direct `MongoOAAdapter(...)` 构造点，用于外部 OA 输入同步到 PostgreSQL `app.oa_*` projection facts；final closure 前必须迁到明确外部输入边界合同，或删除该 direct adapter construction。

## 2026-06-28 - Wave 1 合同基础

目标：

- 明确“统一事实源”是 PostgreSQL canonical facts + 各业务 owner 模块，不是 read model。
- 新增 canonical facts owner matrix 和全局 I/O 规则。
- 将该规则接入 `docs/architecture/module-boundaries/` 与 `docs/modules/` 索引。

决策：

- `canonical-facts` 是资源治理模块，不新增运行时代码模块或 `UnifiedFactSource` service。
- `read-models` 继续只负责派生投影、freshness、refresh 和 operation barrier。
- 旧生产 source-of-truth 路径必须删除；migration/audit/rollback 工具隔离保留不算 closure。

本轮未做：

- 未移动 repository、service 或 migration。
- 未新增数据库 schema。
- 未删除 legacy path。
- 未新增测试，因为没有运行时代码行为变化。

风险：

- owner matrix 是基于 migrations、长期文档和当前 service/repository 命名形成的首版；后续代码重构必须逐调用点验证。
- shared repository 和兼容路径仍可能让 owner 边界不够清晰，需按模块小步收口。

## 2026-06-28 - Wave 4 静态门禁

目标：

- 防止旧生产 source-of-truth 路径在删除前继续扩散。
- 用最小测试锁定当前旧链路引用基线，后续删除旧代码时同步降低 baseline。

决策：

- 复用 `tests/test_platform_runtime_boundary_guards.py`，不新建测试文件。
- 新增 `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline`，覆盖 production app/API/worker 相关文件中的 full snapshot、local pickle、`state:*` JSON、GridFS migration、OA Mongo adapter、Workbench pair relation 和 Turnover legacy fallback 引用基线。
- 这不是 closure；旧生产 source-of-truth 路径仍必须在后续 wave 删除。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 2026-06-28 - Wave 5 OA attachment audit cache write gate

目标：

- 防止 OA attachment audit CLI 默认写入旧 `ApplicationStateStore` / App Mongo-local cache。

变更：

- 后续 slice 已删除 `--allow-cache-write` 和 `ApplicationStateStore(data_dir)` cache 注入。
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_oa_attachment_audit_does_not_write_app_state_cache` 证明该旧写 cache 路径不能回归。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/oa_attachment_audit.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_attachment_audit_does_not_write_app_state_cache tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_mongo_adapter_direct_use_is_allowlisted tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

剩余：

- 该 CLI 后续已迁到 `tools/`；如果继续长期保留，应明确接受为永久 non-production tooling。

## 2026-06-28 - Wave 5 OA attachment audit app path 删除

目标：

- 把 OA attachment audit CLI 从 production `app/` 包迁出，避免 app/server/worker 链路继续携带这个 App Mongo 审计入口。

变更：

- 删除 `backend/src/fin_ops_platform/app/oa_attachment_audit.py`。
- 新增 `backend/src/fin_ops_platform/tools/oa_attachment_audit.py`；后续 slice 已删除旧 cache-write opt-in。
- 更新 static guard，要求旧 app 路径不存在。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/oa_attachment_audit.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_attachment_audit_does_not_write_app_state_cache -v
```

结果：通过。

## 2026-06-28 - Wave 5 Legacy snapshot production guard

目标：

- 防止 legacy full snapshot bootstrap 在 production runtime guard 下读取 local pickle / App snapshot。

变更：

- `LegacySnapshotBootstrap.load_full_snapshot(...)` 在 `FIN_OPS_PRODUCTION_RUNTIME_GUARD=1` 下直接 fail fast。
- 新增 `tests/test_runtime_bootstrap.py::RuntimeBootstrapTests.test_legacy_bootstrap_rejects_snapshot_under_production_runtime_guard`。
- 测试证明即使 reason 是 `migration_*` 允许前缀，production guard 下也不会调用 `load_bootstrap_snapshot()` 或 generic `load()`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/runtime_bootstrap.py tests/test_runtime_bootstrap.py
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_rejects_snapshot_under_production_runtime_guard tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_loads_snapshot_only_for_explicit_test_migration_shadow_reason tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_does_not_fallback_to_generic_state_load tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_rejects_production_full_snapshot_reason -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

剩余：

- 这是 production fail-fast guard，不是删除闭环。`ApplicationStateStore.load_bootstrap_snapshot()` 和 local pickle implementation 仍需删除，或由用户明确接受为永久 non-production tooling。

## 2026-06-28 - Wave 5 ETC legacy API production gate

目标：

- 防止 legacy `/api/etc/batches*` 在 production runtime guard 下继续作为 ETC canonical facts 生产入口。

变更：

- `Application._handle_request_untracked(...)` 中 legacy ETC batch dispatch 必须经过 `_legacy_etc_batch_api_enabled()`。
- 未显式设置 `FIN_OPS_ENABLE_LEGACY_ETC_BATCH_API` 时，`FIN_OPS_PRODUCTION_RUNTIME_GUARD=1` 默认关闭 legacy `/api/etc/batches*`。
- `readiness_summary().entrypoints` 在 gate 关闭时不再列出 legacy `/api/etc/batches*`。
- static guard 要求 dispatch 保持 gate，并禁止生产 deploy env templates 设置 `FIN_OPS_ENABLE_LEGACY_ETC_BATCH_API`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_etc_batch_api_is_gated_under_production_guard tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_routes_delegate_to_compat_route_owner -v
```

结果：通过。

剩余：

- 这是 production gate，不是删除闭环。legacy `/api/etc/batches*`、`routes_etc_legacy_batches.py` 和 `etc_legacy_batch_*` 仍需在前端/API 迁移后删除。

## 2026-06-28 - Wave 5 App Mongo shadow/preflight tool guard

目标：

- 防止 App Mongo/local pickle shadow-read、runtime policy preflight 和 controlled mirror-write rehearsal 被 production app/API/worker 主链路当作 canonical facts 来源。

变更：

- 历史新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_app_mongo_shadow_preflight_tools_stay_tool_only`，后续已收敛为 `test_app_mongo_shadow_preflight_tools_are_removed`。
- guard 禁止 `backend/src/fin_ops_platform/app/` 和 `backend/src/fin_ops_platform/services/` 引用 `run_shadow_read_rehearsal`、`run_runtime_state_policy_preflight` 或 `run_controlled_mirror_write_rehearsal`。
- 后续 slice 已删除 `run_shadow_read_rehearsal.py`、`services/shadow_read_rehearsal.py`、`run_runtime_state_policy_preflight.py` 和 `run_controlled_mirror_write_rehearsal.py`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_app_mongo_shadow_preflight_tools_are_removed -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
```

结果：通过。

剩余：

- 本 slice 是历史 tool-only 隔离证明，不是最终删除闭环。后续 slice 已删除 shadow-read rehearsal、runtime policy preflight 和 controlled mirror-write 工具。

## 2026-06-28 - Wave 5 Turnover relation write legacy 删除

目标：

- 删除 confirm、closure、withdraw 旧 fallback facade/factory，避免 relation 写入绕过新的 Turnover write facade 和 Workbench relation command 边界。

变更：

- 删除 `Application._turnover_ledger_confirm_legacy_fallback_facade`。
- 删除 `Application._turnover_ledger_closure_legacy_fallback_facade`。
- 删除 `Application._turnover_ledger_withdraw_legacy_fallback_facade`。
- 删除 `TurnoverLedgerConfirmLegacyFallbackFacade`、`TurnoverLedgerClosureLegacyFallbackFacade`、`TurnoverLedgerConfirmLegacyFallbackAdapterSet` 和 `TurnoverLedgerWithdrawLegacyFallbackFacade`。
- confirm、closure、cash-closure-withdraw、withdraw request boundary 缺少新 facade 时 fail fast。
- static guard 禁止 production app/API/worker 文件重新出现 confirm/closure/withdraw legacy fallback 类名。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_relation_legacy_fallback_facade_is_removed tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_confirm_and_closure_request_boundaries_fail_fast_without_write_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_withdraw_request_boundary_fails_fast_without_write_facade -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

补充验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api -v
```

结果：146 个 Turnover API 测试通过。

补充决策：

- 删除旧 fallback 后，本地模式不恢复旧链路，而是通过 `_LocalTurnoverLedgerRefreshQueue` 支撑 Turnover primary write facade 的本地 refresh I/O。
- PostgreSQL 模式仍必须使用 durable、支持事务内 enqueue 的 queue repository；缺失时 request boundary fail fast。
- queue failure 的旧“mutation 已落地”测试口径改为 primary UOW rollback 口径，禁止旧 side effect 继续成为 fallback 合同。

## 2026-06-28 - Wave 5 Workbench pair direct write fallback guard

目标：

- 证明 Workbench pair relation canonical fact 不再有 production direct write fallback 绕过 `WorkbenchRelationCommandService`。

变更：

- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_canonical_workbench_pair_relation_direct_write_fallbacks_do_not_return`。
- guard 只允许 `workbench_pair_relation_service.py` domain implementation 和 `workbench_relation_command_service.py` owner command service 调用 pair relation mutation methods。
- 其它 production `app/`、`services/` 文件如果重新通过 `pair_relation_service` 直接调用 `create_active_relation`、`cancel_relation`、`record_history` 或 `replace_with_confirmed_relation`，测试失败。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_workbench_pair_relation_direct_write_fallbacks_do_not_return -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

未删代码说明：

- 本 slice 未发现剩余 production direct pair write fallback，因此没有运行时代码可删。
- Repair、rollback、persist snapshot 路径继续按 owner 边界治理，不作为 production direct write fallback closure。

## 2026-06-28 - Wave 5 GridFS legacy runtime guard

目标：

- 防止 legacy GridFS reader/migration service 回到普通 API runtime source-of-truth。

变更：

- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime`。
- guard 禁止 `server.py` 引用 `LegacyGridFSFileReader`、`GridFSObjectMigrationService` 或 `file_object.gridfs_migration`。
- 后续 slice 已删除 `PostgresStateStore` 的 `FIN_OPS_ENABLE_LEGACY_GRIDFS_READS`、`legacy_file_reader` 注入和 `gridfs://` read fallback。
- guard 要求 `worker.py` 的 GridFS migration handler 只能出现在 `--enable-file-object-migration` 分支内。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime -v
```

结果：通过。

未删代码说明：

- `GridFSObjectMigrationService` 仍属于 migration worker path；后续 slice 已删除 rollback/verify tools。worker path 删除受 07-owned registry 阻塞，仍不计为最终 closure。
- 最终 closure 仍需要 backfill 完成后的删除条件或明确工具隔离保留策略。

## 2026-06-28 - Wave 5 PostgreSQL full-state snapshot deploy guard

目标：

- 防止 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT` 进入生产部署模板或 release 流程。

变更：

- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_deploy_runtime_templates_do_not_enable_postgres_full_state_snapshot`。
- guard 扫描 `deploy/oa/env/*.env.example`、`deploy/oa/fin_ops.env.example` 和 `deploy/oa/bin/finops-deploy-control.sh`，禁止出现 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT`。
- guard 保留 `scripts/deploy_oa.py` 必须调用 `check-release` 的断言。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_deploy_runtime_templates_do_not_enable_postgres_full_state_snapshot -v
```

结果：通过。

未删代码说明：

- `PostgresStateStore.save()` 旧 `state:full_state` round-trip 后续已删除；`PostgresStateStore.load_bootstrap_snapshot()` 后续也已删除。

## 2026-06-28 - Wave 5 PostgreSQL full-state snapshot round-trip 删除

目标：

- 删除 `PostgresStateStore` 中通过 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT` 恢复 `state:full_state` whole snapshot round-trip 的旧路径。

变更：

- `PostgresStateStore._load_snapshot_payload(...)` 不再读取 `state:full_state` 作为 fallback。
- `PostgresStateStore.save(...)` 不再根据 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT` 写 `state:full_state`。
- 删除 `PostgresStateStore._legacy_full_state_snapshot_enabled()`。
- 更新 `tests/test_postgres_state_store.py::PostgresStateStoreTests.test_postgres_store_snapshot_methods_round_trip_without_full_state_fallback`，证明即使设置旧 env 也不会写 `state:full_state`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_store_snapshot_methods_round_trip_without_full_state_fallback tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_save_does_not_write_full_state_snapshot -v
```

结果：通过。

未删代码说明：

- `PostgresStateStore.load_bootstrap_snapshot()` 后续已删除，继续作为 local legacy store 风险项处理。
- `Application.readiness_summary()` 仍拒绝 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT` 误配置；这是 production guard，不是恢复旧写入能力。

## 2026-06-28 - Wave 5 PostgreSQL bootstrap snapshot loader 删除

目标：

- 删除 PostgreSQL state store 的 legacy full snapshot bootstrap 入口，避免 `FIN_OPS_BOOTSTRAP_MODE=legacy` 在 PostgreSQL 下回退到旧 app snapshot。

变更：

- 删除 `PostgresStateStore.load_bootstrap_snapshot()`。
- `LegacySnapshotBootstrap.load_full_snapshot(...)` 不再在缺少 `load_bootstrap_snapshot` 时 fallback 到 generic `state_store.load()`。
- 当时 `ApplicationStateStore` 新增显式 `load_bootstrap_snapshot()`，local legacy 场景保留为命名入口；该入口后续已删除。
- 更新 `tests/test_runtime_bootstrap.py`，证明 PostgreSQL store 不暴露 bootstrap snapshot loader，legacy bootstrap 不会 fallback 到 generic `load()`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_does_not_fallback_to_generic_state_load tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_postgres_state_store_does_not_expose_bootstrap_snapshot_loader tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_loads_snapshot_only_for_explicit_test_migration_shadow_reason -v
```

结果：通过。

后续状态：

- `ApplicationStateStore.load_bootstrap_snapshot()` 后续已删除。
- PostgreSQL canonical facts 链路已无 `load_bootstrap_snapshot()` 入口。

## 2026-06-28 - Wave 5 ApplicationStateStore bootstrap snapshot loader 删除

目标：

- 删除 local legacy store 暴露的 full snapshot bootstrap 入口，避免 `LegacySnapshotBootstrap` 通过 `ApplicationStateStore` 恢复 generic `load()` 语义。

变更：

- 删除 `ApplicationStateStore.load_bootstrap_snapshot()`。
- 新增 `tests/test_runtime_bootstrap.py::RuntimeBootstrapTests.test_application_state_store_does_not_expose_bootstrap_snapshot_loader`。
- `LegacySnapshotBootstrap` 仍可调用显式注入的 test/migration/shadow loader；这不等同于 state store 重新暴露 full snapshot。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_runtime_bootstrap.py
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_application_state_store_does_not_expose_bootstrap_snapshot_loader tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_postgres_state_store_does_not_expose_bootstrap_snapshot_loader tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_loads_snapshot_only_for_explicit_test_migration_shadow_reason tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_does_not_fallback_to_generic_state_load tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_rejects_snapshot_under_production_runtime_guard -v
```

结果：通过。

后续：

- `LegacySnapshotBootstrap` 类后续已删除。
- local pickle implementation 仍存在，作为下一步旧事实源删除或工具隔离候选。

## 2026-06-28 - Wave 5 LegacySnapshotBootstrap 类删除

目标：

- 删除 legacy full snapshot bootstrap 类本体，避免旧 full snapshot 恢复入口继续作为可调用服务存在。

变更：

- 删除 `runtime_bootstrap.py` 中的 `LegacySnapshotBootstrap`。
- 删除空的 `LEGACY_SNAPSHOT_ALLOWLIST` 和 `LEGACY_FULL_SNAPSHOT_REASON_PREFIXES`。
- `test_runtime_bootstrap_does_not_expose_legacy_full_snapshot_adapter` 断言 runtime bootstrap 模块不再暴露这些旧符号。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/runtime_bootstrap.py tests/test_runtime_bootstrap.py
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 2026-06-28 - Wave 5 Worker OA sync source boundary

目标：

- 删除 `app/worker.py` 对 `MongoOAAdapter` 的直接 import 和 construction。

变更：

- 新增 `services/oa_sync_source_adapter.py`，集中构造 OA sync source adapter。
- `app/worker.py` 两条 OA sync path 都调用 `build_oa_sync_source_adapter(...)`。
- static guard 将 worker `MongoOAAdapter` baseline 从 2 降到 0，并只允许 `services/oa_sync_source_adapter.py` 直接 import `MongoOAAdapter`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/worker.py backend/src/fin_ops_platform/services/oa_sync_source_adapter.py tests/test_platform_runtime_boundary_guards.py tests/test_worker_oa_sync.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_mongo_adapter_direct_use_is_allowlisted tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_worker_oa_mongo_adapter_is_confined_to_sync_source_boundary tests.test_worker_oa_sync -v
```

结果：通过。

剩余：

- `MongoOAAdapter` 仍作为 OA external input/admission boundary 存在于 `services/oa_sync_source_adapter.py`，不再由 app worker orchestration 直接构造。

## 2026-06-28 - Wave 5 Workbench candidate state snapshot write 删除

目标：

- 删除 PostgreSQL runtime 对旧 `app.app_settings state:workbench_candidate_matches` JSON snapshot 的写入。

变更：

- `PostgresStateStore.save_workbench_candidate_matches(...)` 只写 `read_model.workbench_candidate_matches`，不再调用 `_save_snapshot("workbench_candidate_matches", ...)`。
- 新增 `test_postgres_save_candidate_matches_does_not_write_runtime_snapshot`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_save_candidate_matches_does_not_write_runtime_snapshot tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_candidate_matches_ignore_runtime_snapshot_fallback tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_candidate_matches_restore_completed_scope_runs -v
```

结果：通过。

剩余：

- `repair_workbench_candidate_snapshot.py` 已在后续 slice 删除；本项不再是 deferred repair path。

## 2026-06-28 - Wave 5 Workbench read model state snapshot write 删除

目标：

- 删除 PostgreSQL runtime 对旧 `app.app_settings state:workbench_read_models` JSON snapshot 的写入。

变更：

- `PostgresStateStore.save_workbench_read_models(...)` 只写 `read_model.workbench_*`，不再调用 `_save_snapshot("workbench_read_models", ...)`。
- 新增 `test_postgres_save_workbench_read_models_does_not_write_runtime_snapshot`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_save_workbench_read_models_does_not_write_runtime_snapshot tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_workbench_read_models_ignore_runtime_snapshot_fallback tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_workbench_read_models_do_not_fallback_to_runtime_snapshot_when_sql_empty -v
```

结果：通过。

## 2026-06-28 - Wave 5 Import state snapshot read 删除

目标：

- 删除 PostgreSQL runtime 对旧 `app.app_settings state:imports` / `state:file_imports` JSON snapshot 的 fallback 读取。

变更：

- `PostgresStateStore._load_imports()` 只返回 PostgreSQL canonical import facts。
- `PostgresStateStore._load_file_imports()` 只返回 PostgreSQL canonical file-import facts。
- 新增 `test_postgres_imports_do_not_fallback_to_runtime_snapshot` 和 `test_postgres_file_imports_do_not_fallback_to_runtime_snapshot`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_imports_do_not_fallback_to_runtime_snapshot tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_file_imports_do_not_fallback_to_runtime_snapshot tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_snapshot_reads_are_confined_to_legacy_allowlist -v
```

结果：通过。

## 2026-06-28 - Wave 5 Local pickle deploy guard

目标：

- 防止生产部署模板把 app runtime 重新配置为 `local_pickle`、`mongo_only` 或其它非 PostgreSQL source-of-truth。

变更：

- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_deploy_runtime_templates_keep_app_storage_backend_postgres`。
- guard 扫描 `deploy/oa/env/*.env.example` 和 `deploy/oa/fin_ops.env.example`；如果出现 `FIN_OPS_APP_STORAGE_BACKEND=`，值必须是 `postgres`。
- guard 要求 `deploy/oa/env/fin-ops.common.env.example` 显式保留 `FIN_OPS_APP_STORAGE_BACKEND=postgres`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_deploy_runtime_templates_keep_app_storage_backend_postgres -v
```

结果：通过。

未删代码说明：

- `ApplicationStateStore` / local pickle implementation 仍可能服务 dev/test/tooling。
- 生产 closure 先通过 readiness guard + deploy template guard 阻断正常 API/worker 入口；最终删除或工具隔离仍需单独 owner-migration slice。
- 后续 slice 已删除 `state_store_factory` 的 shadow / dual backend 构造入口；factory 不再通过 `FIN_OPS_APP_STORAGE_BACKEND=shadow|dual` 暴露旧 mirror/preflight path。

## 2026-06-28 - Wave 5 Local pickle factory production guard

目标：

- 防止 `build_state_store()` 构造 `ApplicationStateStore` / local pickle / mongo / shadow / dual 旧事实源。

变更：

- 后续 slice 已将 `state_store_factory.build_state_store(...)` 收敛为始终只允许 `FIN_OPS_APP_STORAGE_BACKEND=postgres`。
- 未设置 backend、`auto`、显式 `local_pickle`、`mongo` 都直接失败。
- 新增 `tests/test_postgres_state_store.py::PostgresStateStoreTests.test_factory_production_guard_rejects_default_local_storage`。
- 新增 `tests/test_postgres_state_store.py::PostgresStateStoreTests.test_factory_production_guard_rejects_explicit_local_storage`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_default_requires_postgres_backend tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_production_guard_rejects_default_local_storage tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_production_guard_rejects_explicit_local_storage tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_postgres_mode_requires_database_url -v
```

结果：通过。

未删代码说明：

- `ApplicationStateStore` / local pickle 实现仍保留给 dev/test/tooling。
- production app/API/worker 在 guard 开启时不能再通过 factory 构造 local legacy store。

## 2026-06-28 - Wave 5 App Mongo export tool guard

目标：

- 历史记录：曾防止 App Mongo snapshot export 被 production app/API/worker 当作 canonical facts 恢复或读取链路；该工具现已删除。

变更：

- 后续改为 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_app_mongo_export_tool_is_removed`。
- guard 禁止 `app/` 和 `services/` 引用 `export_app_mongo`。
- 后续 slice 已改为 `test_app_mongo_export_tool_is_removed`，要求工具文件不存在。
- 当前 guard 要求工具文件不存在。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_app_mongo_export_tool_is_removed -v
```

结果：通过。

未删代码说明：

- `export_app_mongo.py` 已删除，不再作为 final closure 的 deferred 项。
- 当前只证明它不能被 production app/service 作为 source-of-truth fallback 引用。

## 2026-06-28 - Wave 5 Direct OA Mongo adapter legacy bootstrap guard

目标：

- 防止 `server.py` 中 direct `MongoOAAdapter` 被接回 production API bootstrap 或普通页面 source-of-truth fallback。

变更：

- 当时新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_server_direct_oa_mongo_adapter_is_legacy_bootstrap_only`，后续已由删除 guard 取代。
- 当时 guard 要求 `_build_legacy_direct_oa_mongo_adapter()` 保持 `bootstrap_mode == "legacy"` gate。
- 当时 guard 要求 `_initialize_runtime_services(...)` 只能通过该 legacy-only builder 设置 `_source_oa_adapter`。
- guard 禁止 `_oa_pending_payment_source_adapter()` 复用 legacy bootstrap adapter；OA pending payment 的 Mongo 读取仍是独立外部输入路径。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_direct_oa_mongo_adapter_is_legacy_bootstrap_only tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_bootstrap_does_not_construct_direct_oa_mongo_adapter -v
```

结果：通过。

未删代码说明：

- direct `MongoOAAdapter` 仍在 `server.py` 中保留给 explicit legacy bootstrap 和 OA external-input 场景，不计为 final closure。
- 当前闭环是防止 direct adapter 成为 production canonical facts fallback。

后续状态：该 legacy bootstrap builder 已在下一 slice 删除；当前 guard 是 `test_server_direct_oa_mongo_adapter_legacy_bootstrap_builder_is_removed`。

## 2026-06-28 - Wave 5 Direct OA Mongo legacy bootstrap 删除

目标：

- 删除 `server.py` 中 legacy bootstrap 时直接构造 `MongoOAAdapter` 的旧 App Mongo source path。

变更：

- 删除 `Application._build_legacy_direct_oa_mongo_adapter(...)`。
- `_initialize_runtime_services(...)` 默认 `source_oa_adapter = None`。
- 正常 OA 读取仍通过 `PostgresOAProjectionAdapter`，当 state store 暴露 `oa_projection_repository` 时启用。
- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 中 `server.py` 的 `MongoOAAdapter` removal baseline 从 11 降到 8。
- 新 guard `test_server_direct_oa_mongo_adapter_legacy_bootstrap_builder_is_removed` 要求旧 builder 不得回归。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_runtime_bootstrap.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_direct_oa_mongo_adapter_legacy_bootstrap_builder_is_removed tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_bootstrap_does_not_construct_direct_oa_mongo_adapter -v
```

结果：通过。

剩余：

- OA pending payment source adapter 后续已删除；`MongoOAAdapter` 仍保留给 worker sync 等外部输入路径，最终 audit 需要证明它们只通过 owner/admission 边界进入 PostgreSQL canonical facts。

## 2026-06-28 - Wave 5 Direct OA source adapter 死 fallback 删除

目标：

- 删除 direct OA Mongo legacy bootstrap builder 移除后遗留的 `_source_oa_adapter` 状态和 `source_oa_adapter` 兼容分支，避免旧 adapter 字段作为未来 production fallback 回流。

变更：

- `_initialize_runtime_services(...)` 不再定义 `source_oa_adapter`，不再写入 `self._source_oa_adapter`。
- `IntegrationHubService(...)` 走自身默认 adapter，不再接收 legacy source adapter 占位。
- `AppSettingsService(...)` 不再从 legacy source adapter 注入 OA import options provider。
- `_oa_pending_payment_source_adapter()` 不再读取 `_source_oa_adapter`；OA pending payment 保留自己的显式外部输入 adapter 构造路径。
- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 中 `server.py` 的 `MongoOAAdapter` removal baseline 从 8 降到 7。
- `test_server_direct_oa_mongo_adapter_legacy_bootstrap_builder_is_removed` 改为禁止 `_source_oa_adapter` 和 `source_oa_adapter` 回归。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_direct_oa_mongo_adapter_legacy_bootstrap_builder_is_removed tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_bootstrap_does_not_construct_direct_oa_mongo_adapter -v
```

结果：通过。

剩余：

- `MongoOAAdapter` 仍保留给 OA pending payment source adapter 和 worker sync 等外部输入路径；最终 audit 需要证明它们只通过 owner/admission 边界进入 PostgreSQL canonical facts。

## 2026-06-28 - Wave 5 OA pending payment direct Mongo source 删除

目标：

- 删除 OA pending payment in-progress projection 在 `server.py` 中直接加载 OA Mongo settings 并构造 `MongoOAAdapter` 的旧 source path。

变更：

- 删除 `Application._oa_pending_payment_source_adapter()`。
- `server.py` 不再 import 或调用 `load_mongo_oa_settings`。
- `_oa_pending_payment_projection()` 默认使用 PostgreSQL OA projection repository；非 PostgreSQL测试/本地路径才沿用既有 workbench adapter fallback。
- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 中 `server.py` 的 `MongoOAAdapter` removal baseline 从 7 降到 6。
- `test_server_direct_oa_mongo_adapter_legacy_bootstrap_builder_is_removed` 禁止 `_oa_pending_payment_source_adapter()` 和 `load_mongo_oa_settings` 回归。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_runtime_bootstrap.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_direct_oa_mongo_adapter_legacy_bootstrap_builder_is_removed tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_bootstrap_does_not_construct_direct_oa_mongo_adapter -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_payment_status_service tests.test_oa_pending_payment_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api -v
```

结果：通过。

剩余：

- `MongoOAAdapter` 仍保留在 worker OA sync 和 workbench retained/cache 分支；这些不是本 slice 的删除范围。

## 2026-06-28 - Wave 5 Workbench Mongo type-check 删除

目标：

- 删除 `server.py` 中两个不再需要的 Workbench direct Mongo type checks，降低旧 App Mongo adapter 对 production Workbench 链路的耦合。

变更：

- `_workbench_cache_read_payload_helper()` 传入 `is_mongo_oa_adapter=lambda: False`，production app 不再启用旧 Mongo cache gating。
- `_derived_lifecycle_oa_adapter_cache_executor(...)` 改为 duck-typed `invalidate_records_cache(...)`，不再要求 adapter 是 `MongoOAAdapter`。
- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 中 `server.py` 的 `MongoOAAdapter` removal baseline 从 6 降到 4。
- `test_workbench_cache_read_payload_helper_extraction_stays_local` 要求 app wiring 不再恢复 Mongo type check。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_cache_read_payload_helper_extraction_stays_local -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_cache_read_payload_helper tests.test_derived_data_lifecycle_service -v
```

结果：通过。

剩余：

- `server.py` 仍有 retained-all OA payload 和 fallback month 的 `MongoOAAdapter` type checks，需要单独迁移/删除。
- Worker OA sync 仍显式构造 `MongoOAAdapter`。

## 2026-06-28 - Wave 5 Workbench retained-all Mongo fallback 删除

目标：

- 删除 Workbench retained-all 中依赖 direct `MongoOAAdapter` 的生产分支，防止月份列表失败时继续按 cutoff 范围扫描旧 OA Mongo 源。

变更：

- `_workbench_oa_payload_builder()` 不再通过 `isinstance(..., MongoOAAdapter)` 决定 retained-all 分支；retained-all 由明确的 OA retention cutoff 设置触发。
- `_retained_oa_months_for_all_scope(...)` 在 adapter 无法提供 available months 时返回空列表，不再 fallback 到 cutoff month range。
- 删除 `_fallback_retained_oa_months_for_all_scope(...)` 和 `_fallback_retained_oa_end_month()`。
- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 中 `server.py` 的 `MongoOAAdapter` removal baseline 从 4 降到 2。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_workbench_v2_api.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_oa_payload_builder_extraction_stays_local tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_retained_all_oa_payload_builder_extraction_stays_local -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_oa_payload_builder tests.test_workbench_retained_all_oa_payload_builder tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_all_does_not_fabricate_cutoff_month_range_when_month_listing_errors tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_retained_all_scope_includes_manual_imported_oa_and_attachment_invoices -v
```

结果：通过。

剩余：

- `server.py` 仅剩 `MongoOAAdapter` import 和 attachment invoice parser version helper 两处引用。
- Worker OA sync 仍显式构造 `MongoOAAdapter`。

## 2026-06-28 - Wave 5 Parser version Mongo dependency 删除

目标：

- 删除 app/server 和 SQL projection 中为了读取 attachment invoice parser version 而 import `MongoOAAdapter` 的静态依赖。

变更：

- `server.py` 不再 import `MongoOAAdapter`；`_current_oa_attachment_invoice_parser_version()` 直接调用 `attachment_invoice_cache_parser_version()`。
- `workbench_sql_projection.py`、`workbench_relation_sql_projection.py`、`search_pending_sql_projection.py`、`cost_tax_sql_projection.py` 不再通过 `MongoOAAdapter._attachment_invoice_cache_parser_version()` 取版本。
- `test_canonical_fact_legacy_source_paths_stay_in_removal_baseline` 中 `server.py` 的 `MongoOAAdapter` removal baseline 从 2 降到 0。
- `test_oa_mongo_adapter_direct_use_is_allowlisted` 收紧 direct Mongo adapter allowlist，移除 app/server 和 SQL projection parser-version-only 旧依赖。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/workbench_sql_projection.py backend/src/fin_ops_platform/services/search_pending_sql_projection.py backend/src/fin_ops_platform/services/cost_tax_sql_projection.py backend/src/fin_ops_platform/services/workbench_relation_sql_projection.py tests/test_runtime_bootstrap.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_mongo_adapter_direct_use_is_allowlisted tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_write_and_matching_services_do_not_import_external_clients_directly tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_production_bootstrap_does_not_construct_direct_oa_mongo_adapter -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime tests.test_search_pending_sql_runtime -v
```

结果：通过。

剩余：

- Worker OA sync 仍显式构造 `MongoOAAdapter`。

## 2026-06-28 - Wave 5 Workbench candidate repair tool guard

目标：

- 历史记录：曾防止 `repair_workbench_candidate_snapshot.py` 被 production API/worker hot path 当作 `state:workbench_candidate_matches` fallback；该工具现已删除。

变更：

- 当时新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_workbench_candidate_snapshot_repair_stays_tool_only`。
- 后续 slice 已改为 `test_workbench_candidate_snapshot_repair_tool_is_removed`，要求工具文件不存在。

验证：

历史验证已被后续删除测试取代：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_candidate_snapshot_repair_tool_is_removed -v
```

结果：通过。

后续：

- 该工具已删除，不再作为 final closure 的 deferred 项。

## 2026-06-28 - Wave 5 ETC legacy batch SLO probe 删除

目标：

- 防止生产默认 HTTP SLO 把 legacy `/api/etc/batches*` 当作 ETC canonical facts 主链路。

变更：

- 从 `backend/src/fin_ops_platform/tools/http_slo_probe.py` 的默认 API probes 删除 `etc_batches`。
- 保留 `etc_business_batches` 默认 probe，生产默认 SLO 继续覆盖 ETC 用户可见 canonical 主入口。
- 更新 `tests/test_http_slo_probe.py::HttpSloProbeTests.test_default_probes_cover_page_domains_and_known_slow_endpoints`，禁止 `etc_batches` 和 `/api/etc/batches` 回到默认 probes。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe.HttpSloProbeTests.test_default_probes_cover_page_domains_and_known_slow_endpoints -v
```

结果：通过。

未删代码说明：

- legacy `/api/etc/batches*` 兼容 API 仍 production 可达，因此 canonical facts final closure 未完成。
- 本 slice 只删除生产默认观测链路里的旧 endpoint，下一步仍需删除或替换兼容 API 本身。

## 2026-06-28 - Wave 5 Turnover relation-extra legacy 删除

目标：

- 删除 relation-extra 旧 fallback facade/factory，避免补充信息写入绕过新的 Turnover write facade。

变更：

- 删除 `Application._turnover_ledger_relation_extra_legacy_fallback_facade`。
- 删除 `TurnoverLedgerRelationExtraLegacyFallbackFacade` 和 `TurnoverLedgerRelationExtraLegacyFallbackAdapterSet`。
- `_turnover_ledger_relation_extra_write_facade()` 在缺少新 facade 时返回 `None`，由 request boundary fail fast。
- static guard 禁止 production app/API/worker 文件重新出现 `TurnoverLedgerRelationExtraLegacyFallback`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_request_boundary_facade_wires_current_extra_reader_and_write_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_request_boundary_fails_fast_without_write_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_relation_extra_legacy_fallback_facade_is_removed -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 2026-06-28 - Wave 5 Turnover tag-selection legacy 删除

目标：

- 删除 tag-selection 旧 fallback facade/factory，避免设置写入绕过新的 Turnover write facade。

变更：

- 删除 `Application._turnover_ledger_tag_selection_legacy_fallback_facade`。
- 删除 `TurnoverLedgerTagSelectionLegacyFallbackFacade` 和 `TurnoverLedgerTagSelectionLegacyFallbackAdapterSet`。
- `_turnover_ledger_tag_selection_write_facade()` 在缺少新 facade 时返回 `None`，由 request boundary fail fast。
- static guard 禁止 production app/API/worker 文件重新出现 `TurnoverLedgerTagSelectionLegacyFallback`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_ledger_tag_selection_request_boundary_facade_wires_write_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_ledger_tag_selection_request_boundary_fails_fast_without_write_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_ledger_tag_selection_legacy_fallback_facade_is_removed -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 2026-06-28 - Wave 5 Turnover bank-row-tags legacy fallback 删除

目标：

- 删除一个 bounded production old source-of-truth fallback，不把旧链路继续留在 request boundary。

变更：

- `TurnoverLedgerBankRowTagsRequestBoundaryFacade` 不再接收 `legacy_fallback_provider`。
- 缺少 `TurnoverLedgerWriteFacade` 时直接 fail fast，不再回退到 legacy fallback facade。
- `Application._turnover_ledger_bank_row_tags_request_boundary_facade` 不再注入 `_turnover_ledger_bank_row_tags_legacy_fallback_facade`。
- canonical facts legacy source path removal baseline 已同步降低，生产代码中 `legacy_fallback_provider` 引用归零。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_bank_row_tags_request_boundary_facade_wires_validation_and_affected_months_without_legacy_fallback tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_bank_row_tags_request_boundary_fails_fast_without_write_facade -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

剩余：

- Turnover 其它 `*LegacyFallbackFacade` 类、Workbench pair snapshot 引用、GridFS migration、platform full snapshot/local pickle/App Mongo 工具隔离仍未完成。

## 2026-06-28 - Wave 5 Turnover bank-row-tags legacy class 删除

目标：

- 删除 bank-row-tags 旧 fallback facade/factory 本体，避免后续 production wiring 重新接回旧 source-of-truth 链路。

变更：

- 删除 `Application._turnover_ledger_bank_row_tags_legacy_fallback_facade`。
- 删除 `TurnoverLedgerBankRowTagsLegacyFallbackFacade` 和 `TurnoverLedgerBankRowTagsLegacyFallbackAdapterSet`。
- `_turnover_ledger_bank_row_tags_write_facade()` 在缺少新 facade 时返回 `None`，由 request boundary fail fast。
- static guard 禁止 production app/API/worker 文件重新出现 `TurnoverLedgerBankRowTagsLegacyFallback`。

验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_bank_row_tags_request_boundary_facade_wires_validation_and_affected_months_without_legacy_fallback tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_bank_row_tags_request_boundary_fails_fast_without_write_facade tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_turnover_bank_row_tags_legacy_fallback_facade_is_removed -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 2026-06-28 - Wave 5 ApplicationStateStore service 类型解耦

目标：

- 删除普通 production service 对 local `ApplicationStateStore` 旧事实源实现的直接类型绑定。

变更：

- `AppSettingsService`、`BackgroundJobService`、`SettingsDataResetService` 的 `state_store` 类型改为已有 `ApplicationStateStoreProtocol`。
- 新增 static guard 禁止普通 production service 重新 import local `ApplicationStateStore`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/app_settings_service.py backend/src/fin_ops_platform/services/background_job_service.py backend/src/fin_ops_platform/services/settings_data_reset_service.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_production_services_do_not_type_bind_to_local_application_state_store tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_settings_data_reset_pair_snapshot_uses_explicit_port -v
```

结果：通过。

剩余：

- `ApplicationStateStore` / local pickle implementation 仍保留给 dev/test/tooling 和 factory preflight；本 slice 不算 local pickle final closure。

## 2026-06-29 - Wave 5 state store preflight local-pickle helper 删除

目标：

- 删除 `state_store_factory.py` 中无调用的旧 preflight backend helper，避免继续把 `local_pickle` 描述成可支持的 preflight 事实源。

变更：

- 删除 `_required_preflight_backend(...)`。
- 删除旧错误信息 `Supported preflight backend values are local_pickle and postgres.`。
- 新增 `tests/test_state_store_factory_preflight.py::StateStoreFactoryPreflightTests.test_local_pickle_preflight_backend_helper_is_removed`，防止 helper 和旧支持声明回归。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store_factory.py tests/test_state_store_factory_preflight.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store_factory_preflight -v
```

剩余：

- `ApplicationStateStore` local pickle 实现本体仍存在，主要由 dev/test/tooling 直接构造；它仍是后续删除/隔离项，不计入 final closure。

## 2026-06-29 - Wave 5 GridFS production worker 删除阻塞

结论：

- `file_object.gridfs_migration` production worker path 仍存在于 `worker.py`、deploy env examples、RabbitMQ dispatcher event 和 worker registry。
- 安全删除必须同步移除 `backend/src/fin_ops_platform/services/runtime_worker_registry.py` 中的 `file-migration` registration。
- 该 registry 当前属于 07 read-model closure 只读文件，因此 08 本线程不半删 worker/deploy 文件，避免 registry、部署模板和 worker CLI 不一致。

状态：

- 标记为 `blocked-by-read-model-controller`。
- 等 07 停止或用户显式把 registry 文件分配给 08 后，再一次性删除 worker flag、handler block、registry registration、deploy env examples、dispatcher event、相关 docs 和测试期望。

## 2026-06-29 - Wave 5 runtime convergence closure 工具删除

目标：

- 删除旧高权限 `run_runtime_convergence_closure` 工具，避免继续用包含 App Mongo、legacy GridFS、旧 snapshot smoke 的大工具作为 canonical facts 收口入口。

变更：

- 删除 `backend/src/fin_ops_platform/tools/run_runtime_convergence_closure.py`。
- 删除 `tests/test_runtime_convergence_closure.py`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_runtime_convergence_closure_tool_is_removed`。
- `docs/operations/monitoring.md`、`docs/operations/postgresql-runtime.md`、`docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`、`docs/modules/runtime-workers/tests.md` 和 `docs/modules/domain-events-lifecycle/boundary-io.md` 不再把旧工具/测试列为当前验证入口。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_runtime_convergence_closure_tool_is_removed -v
```

## 2026-06-29 - Wave 5 GridFS verify/rollback 工具删除

目标：

- 删除剩余手工 legacy GridFS verify/rollback 工具，避免继续保留可回滚到 legacy GridFS pointer 的旧入口。

变更：

- 删除 `backend/src/fin_ops_platform/tools/verify_file_object_migration.py`。
- 删除 `backend/src/fin_ops_platform/tools/rollback_file_object_migration.py`。
- 更新 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime`，防止两个工具回归。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime -v
```

剩余：

- `file_object.gridfs_migration` worker path 仍需和 07-owned `runtime_worker_registry.py` 协调删除，不能在 08 单独半删。

## 2026-06-29 - Wave 5 ApplicationStateStore App Mongo 构造入口删除

目标：

- 删除 `ApplicationStateStore` 自动读取 App Mongo config 并构造 Mongo snapshot store 的入口。

变更：

- `ApplicationStateStore.__init__(...)` 不再调用 `load_mongo_state_settings(...)`。
- `ApplicationStateStore.__init__(...)` 不再构造 `MongoClient` 或 `GridFSBucket`。
- `storage_backend` / `storage_mode` 固定为 `local_pickle`，`mongo_database_name` 固定为 `None`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source`。
- 更新 `tests/test_state_store.py::StateStoreTests.test_application_state_store_ignores_app_mongo_config`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source -v
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_application_state_store_ignores_app_mongo_config tests.test_state_store.StateStoreTests.test_local_manual_oa_imports_are_persisted_idempotently_and_removable -v
```

剩余：

- `ApplicationStateStore` local pickle 本体仍未删除。
- legacy GridFS Mongo 配置解析已移动到 `file_object_migration.py`；GridFS production worker 删除仍受 07-owned registry 阻塞。
- 文件内不可达 Mongo branch method body 和旧 mongo-mode tests 仍需后续清理。

## 2026-06-29 - Wave 5 local state store legacy Mongo settings loader 删除

目标：

- 让本地 `ApplicationStateStore` 模块不再携带 App Mongo snapshot 配置入口；GridFS 迁移需要的 legacy Mongo 配置只留在 file-object migration 边界内。

变更：

- 删除 `state_store.py` 中的 `MongoStateSettings`、`load_mongo_state_settings(...)` 和 `DEFAULT_APP_MONGO_DATABASE`。
- `file_object_migration.py` 新增 `LegacyGridFSMongoSettings` / `load_legacy_gridfs_mongo_settings(...)`，仅供 `LegacyGridFSFileReader.from_data_dir(...)` 使用。
- `tests/test_state_store.py` 的 legacy Mongo config 测试迁移为 GridFS migration boundary 测试。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_local_state_store_does_not_expose_legacy_mongo_settings_loader`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/file_object_migration.py backend/src/fin_ops_platform/services/state_store.py tests/test_state_store.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_legacy_gridfs_migration_uses_explicit_app_mongo_config_with_default_database tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_postgres_state_store_does_not_expose_legacy_gridfs_reader tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_local_state_store_does_not_expose_legacy_mongo_settings_loader tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline
```

结果：通过。

剩余：

- GridFS migration worker 本身仍是 `blocked-by-read-model-controller`，因为完整删除必须同步移除 07-owned `runtime_worker_registry.py` 中的 `file_object.gridfs_migration` 注册。

## 2026-06-29 - Wave 5 runtime data path 与 local state store 解耦

目标：

- 生产 app/worker/service/tool 需要默认数据目录时，不再 import local `state_store.py`。

变更：

- 新增 `backend/src/fin_ops_platform/services/runtime_paths.py::default_data_dir()`。
- `ApplicationStateStore` 内部改用 `_default_data_dir()`，但 `state_store.py` 不再定义或导出 `default_data_dir()`。
- `app/main.py`、`app/worker.py`、`etc_reconciliation_service.py`、`turnover_ledger_sql_projection.py`、`repair_no_oa_bank_batch_lifecycle.py`、`link_existing_etc_batches.py` 改为从 `runtime_paths` 读取默认数据目录。
- `tests/test_state_store.py` 的默认数据目录测试迁移到 `runtime_paths`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_production_runtime_paths_do_not_import_local_state_store`，禁止 app/services/tools 重新从 local state store import。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/runtime_paths.py backend/src/fin_ops_platform/services/state_store.py backend/src/fin_ops_platform/app/main.py backend/src/fin_ops_platform/app/worker.py backend/src/fin_ops_platform/services/etc_reconciliation_service.py backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py backend/src/fin_ops_platform/tools/repair_no_oa_bank_batch_lifecycle.py backend/src/fin_ops_platform/tools/link_existing_etc_batches.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_default_data_dir_honors_environment_override tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_production_runtime_paths_do_not_import_local_state_store tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_production_services_do_not_type_bind_to_local_application_state_store tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_local_state_store_does_not_expose_legacy_mongo_settings_loader
```

结果：通过。

## 2026-06-29 - Wave 5 ApplicationStateStore ETC GridFS branch 删除

目标：

- 删除 `ApplicationStateStore` ETC reconciliation/invoice file 路径里不可达的 Mongo GridFS branch。

变更：

- `store_etc_reconciliation_file(...)` 和 `store_etc_invoice_file(...)` 只写本地文件。
- `read_etc_reconciliation_file("gridfs://...")` 和 `read_etc_invoice_file("gridfs://...")` 直接失败。
- `etc_invoice_file_exists("gridfs://...")` 返回 `False`。
- `delete_etc_invoice_file("gridfs://...")` no-op。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_application_state_store_etc_file_paths_do_not_use_mongo_gridfs`。
- 新增 `tests/test_state_store.py::StateStoreTests.test_etc_files_persist_locally_and_reject_legacy_gridfs_refs`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_etc_files_persist_locally_and_reject_legacy_gridfs_refs -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_etc_file_paths_do_not_use_mongo_gridfs tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source -v
```

剩余：

- `ApplicationStateStore` 其它不可达 Mongo branch method body 仍需后续删除。

## 2026-06-29 - Wave 5 ApplicationStateStore settings/OA Mongo branch 删除

目标：

- 删除 `ApplicationStateStore` settings、OA attachment cache、OA sync state 和 manual OA imports 方法中的不可达 App Mongo branch。

变更：

- `load_app_settings(...)` / `save_app_settings(...)` 只使用本地 JSON。
- `load_oa_attachment_invoice_cache_entry(...)` / `save_oa_attachment_invoice_cache_entry(...)` 只使用本地 JSON。
- `load_oa_sync_state(...)` / `save_oa_sync_state(...)` 只使用本地 pickle。
- `load_manual_oa_imports(...)` / `save_manual_oa_imports(...)` 只使用本地 JSON。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_application_state_store_settings_and_oa_cache_do_not_use_app_mongo`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_settings_and_oa_cache_do_not_use_app_mongo -v
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_local_manual_oa_imports_are_persisted_idempotently_and_removable tests.test_state_store.StateStoreTests.test_oa_attachment_invoice_cache_persists_locally_across_store_instances tests.test_state_store.StateStoreTests.test_oa_sync_state_persists_locally_across_store_instances -v
```

## 2026-06-29 - Wave 5 PostgresStateStore generic state snapshot API 删除

目标：

- 删除 PostgreSQL state store 中最后的通用 `app.app_settings state:*` helper，防止任意 canonical facts 重新绕过 owner repository 写入 runtime settings JSON snapshot。

变更：

- 删除 `STATE_KEY_PREFIX`。
- 删除 `_load_snapshot(...)`、`_save_snapshot(...)`、`_load_snapshot_or_empty(...)` 和 `_load_snapshot_or_table_map(...)`。
- `app.app_settings` 仅保留 `load_app_settings(...)` / `save_app_settings(...)` 的明确 app settings 边界。
- 收紧 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_postgres_canonical_fact_methods_do_not_use_runtime_settings_snapshots`，禁止通用 `state:*` snapshot API 回归。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_postgres_canonical_fact_methods_do_not_use_runtime_settings_snapshots tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_canonical_fact_snapshots_do_not_fallback_to_runtime_settings tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_canonical_fact_saves_do_not_write_runtime_settings_snapshots
```

## 2026-06-29 - Wave 5 PostgreSQL transform state snapshot 输出删除（已被后续工具删除 supersede）

目标：

- 防止 staging -> PostgreSQL 转换工具重新生成旧 `app.app_settings state:*` runtime snapshot rows。

变更：

- `no_oa_bank_batches_meta` 不再输出 `state:no_oa_bank_batches`。
- `bank_transaction_categories_meta` 不再输出 `state:bank_transaction_categories`；category audit events 仍写入 `app.bank_transaction_category_events`。
- `turnover_relations_meta` 不再输出 `state:turnover_relations`。
- 删除 `settings_snapshot_row(...)`。
- `tests/test_postgres_transform.py` 改为负向断言上述旧 `state:*` rows 不会生成。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/postgres_transform.py tests/test_postgres_transform.py
PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_transform.py -q
```

## 2026-06-29 - Wave 5 ETC tool runtime application I/O 边界

目标：

- 保留当前仍被 ETC/Workbench 运维文档引用的 historical migration/link/cleanup 工具，但禁止这些业务工具文件继续直接访问 `Application._state_store` 或 runtime 初始化私有方法。

变更：

- 新增 `backend/src/fin_ops_platform/tools/runtime_application.py`，集中封装工具用 lightweight application 构建、partial snapshot 初始化、ETC state persistence callback 和 invoice ETC metadata persistence callback。
- `link_existing_etc_batches.py`、`migrate_historical_etc_business_batches.py` 和 `cleanup_orphan_etc_reconciliation_tasks.py` 改为依赖该 tool-only I/O 边界。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_canonical_fact_tools_use_runtime_application_state_io_boundary`，禁止其它工具文件重新直接访问 `_state_store` 或 `_initialize_runtime_services`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/runtime_application.py backend/src/fin_ops_platform/tools/link_existing_etc_batches.py backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py backend/src/fin_ops_platform/tools/cleanup_orphan_etc_reconciliation_tasks.py tests/test_migrate_historical_etc_business_batches_tool.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_link_existing_etc_batches_tool tests.test_migrate_historical_etc_business_batches_tool
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_tools_use_runtime_application_state_io_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_production_runtime_paths_do_not_import_local_state_store
```

剩余：

- `runtime_application.py` 是 tool-only 隔离层，不算最终 closure。后续删除条件是这些工具迁入 owner module service/repository port，或确认运维入口不再需要后删除。

## 2026-06-29 - Wave 5 import fact consistency 旧工具删除

目标：

- 删除未登记的旧 snapshot cutover 审计工具，避免 legacy Mongo linkage 检查作为长期迁移工具残留。

变更：

- 删除 `backend/src/fin_ops_platform/tools/check_import_fact_consistency.py`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_legacy_import_fact_consistency_tool_is_removed`。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_import_fact_consistency_tool_is_removed
rg -n "check_import_fact_consistency" backend/src tests -g '*.py'
```

结果：代码和测试中只剩删除 guard。

## 2026-06-29 - Wave 5 PostgreSQL migration reconcile 旧工具删除

目标：

- 删除未被当前 runbook 引用的 stage-04 Mongo staging reconciliation 工具。

变更：

- 删除 `backend/src/fin_ops_platform/tools/reconcile_postgres_migration.py`。
- 删除 `tests/test_reconcile_postgres_migration.py`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_legacy_postgres_migration_reconcile_tool_is_removed`。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_postgres_migration_reconcile_tool_is_removed
rg -n "reconcile_postgres_migration" backend/src tests -g '*.py'
```

结果：代码和测试中只剩删除 guard。

## 2026-06-29 - Wave 5 Mongo staging migration CLI 删除

目标：

- 删除未被当前 runbook 引用的 Mongo export/staging CLI wrapper，避免旧 App Mongo -> PostgreSQL migration path 继续作为 deferred 工具残留。

变更：

- 删除 `backend/src/fin_ops_platform/tools/import_postgres_staging.py`。
- 删除 `backend/src/fin_ops_platform/tools/transform_staging_to_postgres.py`。
- 删除 `tests/test_import_postgres_staging.py`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_legacy_mongo_staging_migration_cli_tools_are_removed`。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_mongo_staging_migration_cli_tools_are_removed
rg -n "import_postgres_staging|transform_staging_to_postgres" backend/src tests -g '*.py'
```

结果：代码和测试中只剩删除 guard。

## 2026-06-29 - Wave 5 PostgreSQL transform 旧工具删除

目标：

- 删除 Mongo staging CLI 后已经变成 test-only 的 stage-04 transform 旧实现。

变更：

- 删除 `backend/src/fin_ops_platform/tools/postgres_transform.py`。
- 删除 `tests/test_postgres_transform.py`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_legacy_postgres_transform_tool_is_removed`。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_postgres_transform_tool_is_removed
rg -n "postgres_transform|test_postgres_transform|build_transform_plan|StagingRecord|build_transaction_sql" backend/src tests -g '*.py'
```

结果：代码和测试中只剩删除 guard。

## 2026-06-29 - Wave 5 Mongo export manifest helper 删除

目标：

- 删除 Mongo staging migration 删除后遗留的 App Mongo export manifest helper。

变更：

- 删除 `backend/src/fin_ops_platform/tools/export_manifest.py`。
- 删除 `tests/test_mongo_export_manifest.py`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_legacy_mongo_export_manifest_helpers_are_removed`。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_mongo_export_manifest_helpers_are_removed
rg -n "export_manifest|NdjsonWriter|ExportSerializationError|safe_jsonable|sha256_file|write_checksums" backend/src tests -g '*.py'
```

结果：代码和测试中只剩删除 guard。

## 2026-06-29 - Wave 5 legacy read model reconcile 工具删除

目标：

- 删除通过 `Application` 私有 legacy builder/API 作为 SQL read model 对照 oracle 的旧迁移 CLI，避免旧链路继续污染工具目录。

变更：

- 删除 `backend/src/fin_ops_platform/tools/reconcile_workbench_read_model.py`。
- 删除 `backend/src/fin_ops_platform/tools/reconcile_cost_statistics_read_model.py`。
- 删除 `backend/src/fin_ops_platform/tools/reconcile_tax_offset_read_model.py`。
- 更新 `docs/architecture/persistence-and-read-models.md`，移除三条旧命令，改为 worker refresh、fresh gate、模块测试、generation consistency 和生产只读 evidence。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_legacy_read_model_reconcile_tools_are_removed`。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_read_model_reconcile_tools_are_removed
rg -n "reconcile_(workbench|cost_statistics|tax_offset)_read_model|_build_raw_workbench_payload|_apply_candidate_matches_to_payload|_cost_statistics_service\\.get_explorer|_tax_api_routes\\.get_tax_offset" backend/src/fin_ops_platform/tools -g '*.py'
```

说明：本 slice 不修改 07-owned read model runtime 文件；它只删除旧迁移对照工具，read model runtime closure 仍由 07 controller 负责。

## 2026-06-29 - Wave 5 Mongo exporter definition package 删除

目标：

- 删除旧 App Mongo/stage export definition package。`export_manifest.py` 和 Mongo staging migration CLI 删除后，该 package 只剩自引用常量和 bytecode cache。

变更：

- 删除 `backend/src/fin_ops_platform/tools/exporters/`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_legacy_mongo_exporter_definition_package_is_removed`。

验证：

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_mongo_exporter_definition_package_is_removed
test ! -d backend/src/fin_ops_platform/tools/exporters
rg -n "fin_ops_platform\\.tools\\.exporters|ExportDefinition|CORE_EXPORTS|WORKBENCH_EXPORTS|OPS_TAX_ETC_EXPORTS|READ_MODEL_EXPORTS|gridfs_files_manifest|stage 03|stage 04" backend/src/fin_ops_platform/tools tests/test_platform_runtime_boundary_guards.py -g '*.py'
```

结果：旧 exporter package 路径已不存在；代码和测试中只剩删除 guard。

## 2026-06-29 - Wave 5 tool runtime Application I/O 收紧

目标：

- 保留当前 runbook 仍需要的恢复/迁移/清理工具，但不让业务工具文件直接把 `Application` 私有成员当 I/O 边界。

变更：

- `runtime_application.py` 增加 bank auto-tag restore、ETC/import service、ETC reconciliation task、Workbench relation command/reader、object identity repository、pair relation persistence 和 scope invalidation 等命名 tool runtime ports。
- `restore_bank_auto_tag_rules.py`、`link_existing_etc_batches.py`、`migrate_historical_etc_business_batches.py` 和 `cleanup_orphan_etc_reconciliation_tasks.py` 不再直接调用 `build_application(...)` 或 `app._...`。
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_canonical_fact_tools_use_runtime_application_state_io_boundary` 收紧为：除 `runtime_application.py` 外，tools 目录不得直接调用 `build_application(`、`app._`、`_state_store` 或 `_initialize_runtime_services`。

验证：

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/runtime_application.py backend/src/fin_ops_platform/tools/restore_bank_auto_tag_rules.py backend/src/fin_ops_platform/tools/link_existing_etc_batches.py backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py backend/src/fin_ops_platform/tools/cleanup_orphan_etc_reconciliation_tasks.py tests/test_restore_bank_auto_tag_rules_tool.py tests/test_migrate_historical_etc_business_batches_tool.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_restore_bank_auto_tag_rules_tool tests.test_link_existing_etc_batches_tool tests.test_migrate_historical_etc_business_batches_tool -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_tools_use_runtime_application_state_io_boundary -v
rg -n "build_application\\(|app\\._|application\\._|_state_store|_initialize_runtime_services" backend/src/fin_ops_platform/tools -g '*.py'
```

结果：直接 Application/private runtime 访问只剩 `runtime_application.py`。
