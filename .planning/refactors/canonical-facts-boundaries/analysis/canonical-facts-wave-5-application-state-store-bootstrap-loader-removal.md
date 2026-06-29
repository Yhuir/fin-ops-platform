# Canonical Facts Wave 5 - ApplicationStateStore bootstrap snapshot loader removal

日期：2026-06-28

## 目标

删除 local `ApplicationStateStore` 暴露的 full snapshot bootstrap 入口，防止 legacy bootstrap 通过 local store 恢复 generic full-state `load()` 语义。

## 删除内容

- 删除 `ApplicationStateStore.load_bootstrap_snapshot()`。

## 保留内容

- `LegacySnapshotBootstrap` 仍保留对显式注入 `load_bootstrap_snapshot()` loader 的支持，用于 test/migration/shadow 专用场景。
- 该显式 loader 不来自 `ApplicationStateStore` 或 `PostgresStateStore`。
- `FIN_OPS_PRODUCTION_RUNTIME_GUARD=1` 下 `LegacySnapshotBootstrap.load_full_snapshot(...)` 仍 fail fast。

## Guard

- 新增 `test_application_state_store_does_not_expose_bootstrap_snapshot_loader`。
- 既有 `test_postgres_state_store_does_not_expose_bootstrap_snapshot_loader` 继续覆盖 PostgreSQL store。
- 既有 `test_legacy_bootstrap_does_not_fallback_to_generic_state_load` 继续证明缺少显式 loader 时不会调用 generic `load()`。

## 非闭环项

- local pickle implementation 仍存在，作为后续删除或工具隔离候选。
- 本 slice 没有修改 07-owned read model runtime 文件。
