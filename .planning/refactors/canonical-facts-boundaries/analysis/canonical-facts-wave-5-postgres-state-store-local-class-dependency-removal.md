# Wave 5 - PostgresStateStore Local Class Dependency Removal

日期：2026-06-29

## Target

移除 PostgreSQL production state store 对 local pickle `ApplicationStateStore` 类的静态 helper 依赖。

## Changes

- `PostgresStateStore` 不再 import `ApplicationStateStore`。
- Manual OA imports normalization、dedupe 和 filename sanitization 改为 `postgres_state_store.py` 内部私有 helper。
- `test_production_services_do_not_type_bind_to_local_application_state_store` 去掉 `postgres_state_store.py` 例外，防止 production service 重新 type-bind local store class。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_store_snapshot_methods_round_trip_without_full_state_fallback tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_canonical_fact_saves_do_not_write_runtime_settings_snapshots tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_production_services_do_not_type_bind_to_local_application_state_store
```

## Result

Production PostgreSQL state store no longer depends on local pickle `ApplicationStateStore` for helper behavior.
