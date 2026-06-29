# Canonical Facts Wave 5 - OA attachment audit tool removal

日期：2026-06-29

## 目标

删除无活跃命名审计任务依赖的 OA attachment audit 工具，避免 direct OA Mongo audit path 作为 permanent deferred tooling 保留。

## 证据

- CodeGraph callers 显示 `audit_oa_attachment_records(...)` 和 `write_oa_attachment_audit_report(...)` 只被 `tools/oa_attachment_audit.py` 调用。
- `tools/oa_attachment_audit.py` 直接构造 `MongoOAAdapter(settings=settings)` 读取 OA Mongo。
- 该工具已经不在 production app/server/worker 链路中；删除不会触碰 07-owned read model runtime 文件。

## 变更

- 删除 `backend/src/fin_ops_platform/tools/oa_attachment_audit.py`。
- 删除 `backend/src/fin_ops_platform/services/oa_attachment_audit.py`。
- 删除 `tests/test_oa_attachment_audit.py`。
- 更新 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_oa_attachment_audit_tool_is_removed`。
- 更新 current docs：
  - `docs/architecture/backend-refactor/architecture-inventory.md`
  - `docs/modules/canonical-facts/tests.md`
  - `docs/modules/canonical-facts/implementation-notes.md`

## 验证

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_attachment_audit_tool_is_removed
```

## 剩余

- OA Mongo external input 仍保留在 `mongo_oa_adapter.py` / `oa_sync_source_adapter.py` / OA sync worker 边界，用于同步到 PostgreSQL projection facts。
- `file_object.gridfs_migration` production worker deletion remains `blocked-by-read-model-controller`.
