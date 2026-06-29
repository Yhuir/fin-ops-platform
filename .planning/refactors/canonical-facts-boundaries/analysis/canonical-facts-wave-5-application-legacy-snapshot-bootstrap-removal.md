# Wave 5 - Application legacy snapshot bootstrap removal

日期：2026-06-28

## 目标

删除 `Application` 对 legacy full snapshot bootstrap 的生产装配和调用入口。`LegacySnapshotBootstrap` 类暂时保留给显式 test/migration/shadow loader 场景，但不再由 app/API runtime 持有或调用。

## 变更

- `server.py` 不再 import `LegacySnapshotBootstrap`。
- `Application.__init__` 不再创建 `self._legacy_bootstrap`。
- `_runtime_bootstrap_state()` 不再在 `bootstrap_mode == "legacy"` 时调用 full snapshot loader，始终返回空启动 state。
- 删除 `_load_persisted_state(...)`。
- readiness bootstrap summary 使用固定空 `legacy_snapshot` summary，不再调用 object summary。
- canonical legacy source path baseline 中 `server.py` 的 `load_full_snapshot` count 从 1 降为 0。

## 边界结论

- app/API production wiring 不再存在 full snapshot bootstrap call path。
- `bootstrap_mode=legacy` 仍作为旧参数/测试兼容值存在，但不再恢复 whole snapshot。
- 显式 `LegacySnapshotBootstrap` 类仍可被 test/migration/shadow 直接实例化；它不是 app/API production wiring。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_runtime_bootstrap.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。
