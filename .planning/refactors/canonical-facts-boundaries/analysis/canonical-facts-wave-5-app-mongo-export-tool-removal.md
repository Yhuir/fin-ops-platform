# Canonical Facts Wave 5: App Mongo Export Tool Removal

日期：2026-06-29

## Scope

删除旧 `backend/src/fin_ops_platform/tools/export_app_mongo.py` 和对应 `tests/test_export_app_mongo.py`。

## Decision

- App Mongo snapshot 不能作为 canonical facts source-of-truth 或长期 export/audit fallback。
- 该工具没有生产 app/service 调用者；继续保留只会留下旧 App Mongo 读取入口。
- 生产备份/恢复应走 PostgreSQL PITR、对象存储和部署运维 runbook，不通过 App Mongo export。

## Verification

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_app_mongo_export_tool_is_removed -v
```

结果：通过。
