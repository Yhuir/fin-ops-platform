# Canonical Facts Wave 5: Workbench Candidate Repair Tool Removal

日期：2026-06-29

## Scope

删除旧 `backend/src/fin_ops_platform/tools/repair_workbench_candidate_snapshot.py`。

## Decision

- 该工具会把 Workbench candidate snapshot 写入 `app.app_settings state:workbench_candidate_matches`。
- `PostgresStateStore.save_workbench_candidate_matches(...)` 已经改为只写 `read_model.workbench_candidate_matches`。
- 当前没有生产 app/service 调用者；保留该工具只会继续留下旧 source-of-truth 写入口。

## Verification

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_candidate_snapshot_repair_tool_is_removed -v
```

结果：通过。
