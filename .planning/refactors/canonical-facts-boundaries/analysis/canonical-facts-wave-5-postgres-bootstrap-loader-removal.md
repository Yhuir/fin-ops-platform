# Canonical Facts Wave 5: PostgreSQL Bootstrap Loader Removal

日期：2026-06-28

## Scope

删除 PostgreSQL state store 的 legacy full snapshot bootstrap 入口，并阻断 legacy bootstrap 对 generic `state_store.load()` 的 fallback。目标是避免 `FIN_OPS_BOOTSTRAP_MODE=legacy` 在 PostgreSQL 下重新读取 app snapshot 作为 canonical facts fallback。

## Changes

- `backend/src/fin_ops_platform/services/postgres_state_store.py`
  - 删除 `PostgresStateStore.load_bootstrap_snapshot()`。
- `backend/src/fin_ops_platform/services/runtime_bootstrap.py`
  - `LegacySnapshotBootstrap.load_full_snapshot(...)` 在 state store 没有显式 `load_bootstrap_snapshot` 时返回 `{}`，不再 fallback 到 `load()`。
- `backend/src/fin_ops_platform/services/state_store.py`
  - `ApplicationStateStore` 新增显式 `load_bootstrap_snapshot()`，local legacy/migration/shadow/test 入口命名化。
- `tests/test_runtime_bootstrap.py`
  - 新增 `test_legacy_bootstrap_does_not_fallback_to_generic_state_load`。
  - 将 PostgreSQL bootstrap 测试改为证明 `PostgresStateStore` 不暴露 bootstrap snapshot loader。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_does_not_fallback_to_generic_state_load tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_postgres_state_store_does_not_expose_bootstrap_snapshot_loader tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_loads_snapshot_only_for_explicit_test_migration_shadow_reason -v
```

结果：通过。

## Closure Note

PostgreSQL canonical facts 链路已无 `load_bootstrap_snapshot()`。`LegacySnapshotBootstrap` 和 local `ApplicationStateStore.load_bootstrap_snapshot()` 仍保留给 local legacy/migration/shadow/test；该 local legacy path 仍是后续删除或工具隔离项，不计为 final closure。
