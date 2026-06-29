# Canonical Facts Wave 5 - Runtime Convergence Closure Tool Removal

日期：2026-06-29

## 目标

删除旧 `run_runtime_convergence_closure` 高权限收敛工具。该工具仍包含 App Mongo、legacy GridFS、旧 snapshot 和 worker smoke 的组合检查，不应继续作为 canonical facts final closure 的验证入口。

## 变更

- 删除 `backend/src/fin_ops_platform/tools/run_runtime_convergence_closure.py`。
- 删除 `tests/test_runtime_convergence_closure.py`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_runtime_convergence_closure_tool_is_removed`，防止工具和测试回归。
- 更新 operations/architecture/module docs，删除旧命令和测试入口，改为分项 gate。

## 边界结论

- 本 slice 不修改 07-owned read model runtime files。
- 本 slice 不删除 `file_object.gridfs_migration` production worker；该项仍受 `runtime_worker_registry.py` 07 ownership 阻塞。
- 当前运行时收口验证使用分项 gate，而不是一个包含旧事实源 smoke 的大工具。

## 验证

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_runtime_convergence_closure_tool_is_removed -v
git diff --check
bash scripts/verify.sh docs
```

结果：通过。
