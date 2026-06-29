# Canonical Facts Wave 5: Legacy Snapshot Production Guard

日期：2026-06-28

## 目标

阻断 legacy full snapshot bootstrap 在 production runtime guard 下读取 local pickle / App snapshot，避免旧 snapshot 成为 PostgreSQL canonical facts 的恢复入口。

## 当前判断

- `Application` production bootstrap 已不调用 `LegacySnapshotBootstrap.load_full_snapshot(...)`。
- `PostgresStateStore` 已删除 `load_bootstrap_snapshot()`，不会暴露 PostgreSQL full-state snapshot loader。
- `ApplicationStateStore.load_bootstrap_snapshot()` 仍保留给 local legacy/migration/shadow/test 场景，最终仍需删除或永久标为 non-production tooling。

## 变更

- `LegacySnapshotBootstrap.load_full_snapshot(...)` 在 `FIN_OPS_PRODUCTION_RUNTIME_GUARD=1` 下直接 fail fast。
- 新增 `tests/test_runtime_bootstrap.py::RuntimeBootstrapTests.test_legacy_bootstrap_rejects_snapshot_under_production_runtime_guard`。
- 测试证明即使 reason 是 `migration_*` 允许前缀，production guard 下也不会调用 `load_bootstrap_snapshot()` 或 generic `load()`。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/runtime_bootstrap.py tests/test_runtime_bootstrap.py
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_rejects_snapshot_under_production_runtime_guard tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_loads_snapshot_only_for_explicit_test_migration_shadow_reason tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_does_not_fallback_to_generic_state_load tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_legacy_bootstrap_rejects_production_full_snapshot_reason -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## Closure 状态

本 slice 是 production fail-fast guard，不是最终删除。`ApplicationStateStore.load_bootstrap_snapshot()` 和 local pickle implementation 仍是 `pending-removal`；最终 closure 需要删除该 local legacy loader，或由用户明确接受为永久 non-production tooling。
