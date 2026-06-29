# Canonical Facts Wave 5 - GridFS Verify/Rollback Tool Removal

日期：2026-06-29

## 目标

删除剩余 tool-only legacy GridFS verify/rollback 入口。生产文件读取已经不允许 GridFS fallback；这些工具没有当前命名迁移/回滚操作要求保留。

## 变更

- 删除 `backend/src/fin_ops_platform/tools/verify_file_object_migration.py`。
- 删除 `backend/src/fin_ops_platform/tools/rollback_file_object_migration.py`。
- 更新 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime`，防止两个工具回归。

## 边界结论

- 本 slice 不修改 07-owned `runtime_worker_registry.py`。
- `file_object.gridfs_migration` production worker path 仍受 `blocked-by-read-model-controller` 约束，不能半删。
- GridFS verify/rollback 手工工具已删除；剩余 GridFS legacy path 只剩 worker/registry/deploy 同步删除问题。

## 验证

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime -v
git diff --check
bash scripts/verify.sh docs
```

结果：通过。
