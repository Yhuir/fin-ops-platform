# Wave 5 - PostgresStateStore canonical facts state snapshot removal

日期：2026-06-29

## Scope

本切片删除 `PostgresStateStore` 中一组生产 canonical facts 对旧 `app.app_settings state:*` JSON snapshot 的 fallback/read-write：

- Workbench pair relations
- Workbench overrides
- Workbench exception cases
- no-OA bank batches
- bank transaction categories
- Turnover relations
- Turnover ledger extras
- tax certified imports
- pending invoice commands
- manual OA imports
- cost statistics read models
- tax offset read models
- background jobs runtime facts
- app health alerts audit facts
- ETC state
- ETC reconciliation state
- OA sync state
- historical ETC repair bundles
- historical ETC repair parsed seeds
- historical ETC repair states

不修改 07-owned read model runtime 文件。

## Boundary

- 正式 owner repository：`PostgresWorkbenchRelationRepository` / `PostgresWorkbenchRepository`。
- 禁止旧链路：`state:workbench_pair_relations`、`state:workbench_overrides`、`state:workbench_exception_cases`、`state:no_oa_bank_batches`、`state:bank_transaction_categories`、`state:turnover_relations`、`state:turnover_ledger_extras`、`state:tax_certified_imports`、`state:pending_invoice_commands`、`state:manual_oa_imports`、`state:cost_statistics_read_models`、`state:tax_offset_read_models`。
- runtime/audit 禁止旧链路：`state:background_jobs`、`state:app_health_alerts`。
- ETC 禁止旧链路：`state:etc_state`、`state:etc_reconciliation_state`。
- OA sync 禁止旧链路：`state:oa_sync_state`。
- historical ETC repair 禁止旧链路：`state:historical_etc_repair_bundles`、`state:historical_etc_repair_parsed_seeds`、`state:historical_etc_repair_states`。

## I/O

保留：

- PostgreSQL owner repository reads/writes。
- 现有 normalization contracts。

删除：

- `_load_snapshot(...)` fallback。
- `_save_snapshot(...)` mirror writes。

## Validation

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/services/state_store.py tests/test_postgres_state_store.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_store_snapshot_methods_round_trip_without_full_state_fallback tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_canonical_fact_snapshots_do_not_fallback_to_runtime_settings tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_canonical_fact_saves_do_not_write_runtime_settings_snapshots
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_postgres_canonical_fact_methods_do_not_use_runtime_settings_snapshots tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline
```

结果：通过。

## Remaining

`PostgresStateStore` 仍有其它 `state:*` runtime/audit/tooling snapshots and ETC fallback slices to classify or delete separately. GridFS production worker deletion仍受 07-owned worker registry 协调限制。
