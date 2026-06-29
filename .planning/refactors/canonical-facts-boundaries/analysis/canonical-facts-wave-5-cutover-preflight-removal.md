# Canonical Facts Wave 5: Cutover Preflight Removal

日期：2026-06-29

## Scope

删除旧 cutover preflight checker / CLI：

- `backend/src/fin_ops_platform/tools/verify_cutover_preflight.py`
- `tests/test_cutover_preflight.py`
- `backend/src/fin_ops_platform/services/cutover_preflight.py` 中的 `CutoverPreflightChecker`、`CutoverPreflightConfig` 和 `build_checker_from_env`

## Decision

- `verify_cutover_preflight.py` 是旧 PostgreSQL cutover rehearsal 工具，不是当前 active named migration / rollback 入口。
- `cutover_preflight.py` 仍被 `invoice_pool_cleanup.py` 复用 secret redaction helper；本 slice 只保留脱敏 helper，删除 cutover checker 行为。旧 `shadow_read_psql_store.py` 已在后续 shadow-read removal slice 删除。
- 后续 slice 已删除 `state_store_factory.py` 的 `FIN_OPS_APP_STORAGE_BACKEND=shadow|dual` backend 构造入口；`FIN_OPS_CUTOVER_PREFLIGHT_ONLY` 不再作为 factory 安全闸使用。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/cutover_preflight.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_cutover_preflight_checker_is_removed -v
```

结果：通过。
