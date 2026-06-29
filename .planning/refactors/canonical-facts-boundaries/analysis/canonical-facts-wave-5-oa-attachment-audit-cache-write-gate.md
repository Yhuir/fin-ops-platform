# Canonical Facts Wave 5: OA Attachment Audit Cache Write Gate

日期：2026-06-28

## 目标

阻断 OA attachment audit CLI 默认写入 `ApplicationStateStore` / App Mongo-local cache，避免审计工具把旧 App state cache 当成 canonical facts 链路的一部分。

## 当前判断

- `backend/src/fin_ops_platform/app/oa_attachment_audit.py` 原本是人工 CLI 审计入口，不应被 production app/server/worker 调用。
- 该脚本原先默认构造 `ApplicationStateStore(data_dir)` 作为 `MongoOAAdapter` 的 attachment invoice cache，可能写入旧 App state cache。
- OA Mongo 是外部输入，OA attachment invoice cache 不是 PostgreSQL canonical facts。

## 变更

- `oa_attachment_audit.py` 当时改为默认不构造 `ApplicationStateStore` cache。
- 后续 wave 5 slice 已删除 `--allow-cache-write` 和 `ApplicationStateStore` cache 注入。
- 当前 guard 是 `test_oa_attachment_audit_does_not_write_app_state_cache`，证明 server/worker/services 不引用该 CLI，且旧 App state cache write path 不存在。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/oa_attachment_audit.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_attachment_audit_does_not_write_app_state_cache tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_oa_mongo_adapter_direct_use_is_allowlisted tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## Closure 状态

本 slice 删除了审计 CLI 的默认旧 App state cache 写入，但没有删除 OA Mongo 外部输入或 attachment cache implementation。后续已把该 CLI 迁到 `tools/`；如果长期保留，应明确登记为永久 non-production tooling。
