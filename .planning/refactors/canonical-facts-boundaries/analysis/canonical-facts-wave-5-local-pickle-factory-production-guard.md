# Canonical Facts Wave 5: Local Pickle Factory Production Guard

日期：2026-06-28

## Scope

历史 slice：在 state store factory 层阻断 production guard 下的 local pickle / mongo / shadow / dual 旧事实源构造。后续 wave 5 slice 已进一步删除 default/local/mongo/auto factory fallback，`build_state_store()` 现在始终要求显式 PostgreSQL backend。

## Changes

- `backend/src/fin_ops_platform/services/state_store_factory.py`
  - 新增 `FIN_OPS_PRODUCTION_RUNTIME_GUARD` factory guard。
  - 当时 guard 开启时只允许 `FIN_OPS_APP_STORAGE_BACKEND=postgres`。
  - 后续 slice 已收敛为无论 guard 是否开启，backend 未设置或显式 `local_pickle` 都失败。
- `tests/test_postgres_state_store.py`
  - 新增 `test_factory_production_guard_rejects_default_local_storage`。
  - 新增 `test_factory_production_guard_rejects_explicit_local_storage`。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_default_requires_postgres_backend tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_production_guard_rejects_default_local_storage tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_production_guard_rejects_explicit_local_storage tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_postgres_mode_requires_database_url -v
```

结果：通过。

## Closure Note

本 slice 没有删除 `ApplicationStateStore` 或 local pickle 实现。它把 production app/API/worker factory 入口进一步前移为 fail fast。Local legacy implementation 仍服务 dev/test/tooling，后续仍需删除或工具隔离，不计为 final closure。
