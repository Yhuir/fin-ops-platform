# Canonical Facts Wave 5: OA Attachment Audit App Path Removal

日期：2026-06-28

## 目标

把 OA attachment audit CLI 从 `app/` 包迁出，避免 production app/API/worker 链路继续携带 App Mongo 审计入口。

## 变更

- 删除 `backend/src/fin_ops_platform/app/oa_attachment_audit.py`。
- 新增 `backend/src/fin_ops_platform/tools/oa_attachment_audit.py`。
- 后续 slice 已删除 `--allow-cache-write` 和旧 App state cache 写入路径。
- 更新 static guard，要求旧 app 路径不存在。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/oa_attachment_audit.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_attachment_audit_does_not_write_app_state_cache -v
```

结果：通过。

## Closure 状态

本 slice 删除了 app 包下的旧 CLI 路径。`tools/oa_attachment_audit.py` 仍是 non-production audit tooling；如果长期保留，需要在最终 closure audit 中明确接受。
