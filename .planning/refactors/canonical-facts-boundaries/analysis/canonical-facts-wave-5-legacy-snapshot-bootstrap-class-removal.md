# Wave 5 - Legacy snapshot bootstrap class removal

日期：2026-06-28

## 目标

删除 legacy full snapshot bootstrap 类本体。此前 `Application` 已经不再装配它，PostgreSQL 和 local state store 也不再暴露 `load_bootstrap_snapshot()`；保留该类只会让旧 full snapshot 恢复入口继续存在。

## 变更

- 从 `runtime_bootstrap.py` 删除 `LegacySnapshotBootstrap`。
- 删除空的 `LEGACY_SNAPSHOT_ALLOWLIST` 和 `LEGACY_FULL_SNAPSHOT_REASON_PREFIXES`。
- 删除旧类行为测试，改为断言 runtime bootstrap 模块不再暴露 legacy full snapshot bootstrap 符号。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/runtime_bootstrap.py tests/test_runtime_bootstrap.py
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## 剩余

full snapshot bootstrap production/runtime 类入口已删除。剩余 local pickle 工作是 `ApplicationStateStore` implementation/factory/tooling 边界，不再是 `LegacySnapshotBootstrap`。
