# Canonical Facts Wave 5: App Mongo Export Tool Guard

日期：2026-06-28

## Scope

锁定 App Mongo snapshot export 只能作为显式 export/audit/migration 工具，不能回到 production app/API/worker source-of-truth 链路。

## Changes

- `tests/test_platform_runtime_boundary_guards.py`
  - 后续改为 `test_app_mongo_export_tool_is_removed`。
  - 禁止 `backend/src/fin_ops_platform/app` 和 `backend/src/fin_ops_platform/services` 引用 `export_app_mongo`。
  - 历史上要求 `export_app_mongo.py` 保留 `--source restore|production`、`--dry-run`、`--force`、`FIN_OPS_STORAGE_MODE=mongo_only`、`read_only=True` 和 source database 校验。
  - 后续 wave 5 slice 已删除该工具。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_app_mongo_export_tool_is_removed -v
```

结果：通过。

## Closure Note

后续 wave 5 slice 已删除 `export_app_mongo.py`。当前 closure 不再把 App Mongo export 列为 deferred tool-only path。
