# Canonical Facts Wave 5 - shadow / dual state-store module removal

日期：2026-06-29

## 目标

删除已无 production caller 的 legacy shadow/dual state-store 支撑模块，避免它们作为独立 test/tooling 对象长期保留。

## 证据

- CodeGraph impact 只显示模块自身和旧测试文件。
- CodeGraph callers 对 `DualStateStore` / `ShadowStateStore` 无 runtime caller。
- `rg` 只发现旧测试和历史文档引用。

## 变更

- 删除 `backend/src/fin_ops_platform/services/shadow_state_store.py`。
- 删除 `backend/src/fin_ops_platform/services/dual_state_store.py`。
- 删除 `tests/test_shadow_state_store.py`。
- 删除 `tests/test_dual_state_store.py`。
- 新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_shadow_and_dual_state_store_modules_are_removed`。
- 更新当前事实源文档：
  - `docs/architecture/backend-refactor/platform-runtime-boundary-audit.md`
  - `docs/architecture/backend-refactor/architecture-inventory.md`
  - `docs/modules/canonical-facts/tests.md`
  - `docs/modules/canonical-facts/implementation-notes.md`

## 验证

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_shadow_and_dual_state_store_modules_are_removed
```

## 剩余

- `state_store_diff.py` 保留为独立 diff utility。
- `ApplicationStateStore` / local pickle 本体仍是 local tooling/test I/O deferred。
- `file_object.gridfs_migration` production worker deletion remains `blocked-by-read-model-controller`.
