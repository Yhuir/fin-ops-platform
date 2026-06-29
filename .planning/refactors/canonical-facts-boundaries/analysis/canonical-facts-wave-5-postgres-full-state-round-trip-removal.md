# Canonical Facts Wave 5: PostgreSQL Full-State Round-Trip Removal

日期：2026-06-28

## Scope

删除 `PostgresStateStore` 中由 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT` 控制的 `state:full_state` whole snapshot 读写 fallback。该路径会让 PostgreSQL `app.app_settings` 的旧 JSON 聚合重新覆盖 canonical facts，不能保留为 production-reachable compatibility branch。

## Changes

- `backend/src/fin_ops_platform/services/postgres_state_store.py`
  - `_load_snapshot_payload(...)` 不再读取 `state:full_state` fallback。
  - `save(...)` 不再写 `state:full_state`。
  - 删除 `_legacy_full_state_snapshot_enabled()`。
- `tests/test_postgres_state_store.py`
  - 更新 snapshot round-trip 测试，证明旧 env 即使设置也不会写 `state:full_state`。
- `docs/architecture/persistence-and-read-models.md`
  - 删除 migration/shadow/test 可用 env 恢复 whole snapshot round-trip 的旧说明。
- `docs/operations/monitoring.md`
  - 更新 `state:full_state` 监控说明，强调不应再由 `PostgresStateStore.save()` 写入。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_store_snapshot_methods_round_trip_without_full_state_fallback tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_save_does_not_write_full_state_snapshot -v
```

结果：通过。

## Closure Note

本 slice 删除了 `PostgresStateStore.save/load` 的 full-state round-trip。`PostgresStateStore.load_bootstrap_snapshot()` 仍存在，属于后续 legacy bootstrap/migration/shadow/test 风险项；`Application.readiness_summary()` 保留对 `FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT` 的拒绝只是误配置 guard，不恢复旧写入能力。
