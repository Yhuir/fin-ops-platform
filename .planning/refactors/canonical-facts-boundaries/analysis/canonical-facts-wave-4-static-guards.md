# Canonical Facts Wave 4: Static Guards

日期：2026-06-28

## Change

新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline`。

该 guard 是删除基线，不是兼容闭环。它锁定当前 production app/API/worker 相关文件中的旧 source-of-truth 引用数量，并禁止以下未登记旧事实源 token 回到生产 orchestration 文件：

- `ApplicationStateStore`
- `_load_local_pickle`
- `_save_local_pickle`
- `load_bootstrap_snapshot`
- `state:full_state`
- `state:imports`
- `state:file_imports`
- `state:workbench`

同时基线跟踪这些已知旧链路引用：

- `load_full_snapshot`
- `MongoOAAdapter`
- `WorkbenchPairRelationService`
- `pair_relation_service`
- `legacy_fallback_provider`
- `GridFSObjectMigrationService`
- `LegacyGridFSFileReader`

## Interpretation

此 guard 的目的不是允许旧链路长期存在，而是防止旧链路在 wave 5 删除前继续扩散。后续删除旧代码时，必须同步降低对应 baseline count；如果新增引用，测试会失败。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## Next

进入 `wave-5-code-removal`。优先选择 bounded owner slice，删除最高风险旧生产 source-of-truth 路径，并同步降低 static guard baseline。
