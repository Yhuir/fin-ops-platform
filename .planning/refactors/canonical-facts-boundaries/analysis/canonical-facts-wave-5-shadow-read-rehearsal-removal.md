# Canonical Facts Wave 5: Shadow Read Rehearsal Removal

日期：2026-06-29

## Scope

删除旧 App Mongo/local pickle shadow-read rehearsal CLI、底层 service 和 psql shadow-read store：

- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- `tests/test_shadow_read_rehearsal.py`

## Decision

- 该链路用于旧 local pickle / App Mongo 与 PostgreSQL shadow-read 对比，不应作为 canonical facts closure 的长期 tool-only 例外。
- 当前没有 production app/service 调用者，也没有其它工具导入该 CLI/service/store。
- 后续 slice 已删除 runtime policy preflight 和 controlled mirror-write rehearsal。

## Verification

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_app_mongo_shadow_preflight_tools_are_removed -v
```

结果：通过。
