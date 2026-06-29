# Canonical Facts Wave 5: OA Attachment Audit Cache Write Removal

日期：2026-06-29

## Scope

删除 OA attachment audit CLI 中旧 App state cache 写入开关：

- `--allow-cache-write`
- `ApplicationStateStore(data_dir)` cache 注入
- `MongoOAAdapter(..., attachment_invoice_cache=cache)` 写 cache 路径

## Decision

- 该 CLI 是只读审计工具，旧 App state cache 写入不是当前 active named migration / rollback 入口。
- PostgreSQL `app.oa_attachment_invoice_cache*` 已是 OA attachment parser cache 的 canonical 持久化边界；审计 CLI 不应写 local pickle / App state cache。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/oa_attachment_audit.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_attachment_audit_does_not_write_app_state_cache -v
```

结果：通过。
