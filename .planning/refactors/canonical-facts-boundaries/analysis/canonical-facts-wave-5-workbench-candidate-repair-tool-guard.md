# Canonical Facts Wave 5: Workbench Candidate Repair Tool Guard

日期：2026-06-28

## Slice

历史记录：该 slice 曾锁定 `repair_workbench_candidate_snapshot.py` 只能作为显式工具路径，不能被 production API/worker hot path 导入。该工具已在 2026-06-29 后续 slice 删除。

## Evidence

- 当前 `backend/src/fin_ops_platform/app/` 和 `backend/src/fin_ops_platform/services/` 没有引用 `repair_workbench_candidate_snapshot`。
- 后续 slice 已删除该工具。

## Change

- `tests/test_platform_runtime_boundary_guards.py`
  - 后续改为 `test_workbench_candidate_snapshot_repair_tool_is_removed`。
  - 禁止 app/services 引用 `repair_workbench_candidate_snapshot`。
  - 要求工具文件不存在。

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_candidate_snapshot_repair_tool_is_removed -v
```

结果：通过。

## Closure Note

后续 slice 已删除该工具；当前 closure 不再把它列为 deferred tool-only path。
