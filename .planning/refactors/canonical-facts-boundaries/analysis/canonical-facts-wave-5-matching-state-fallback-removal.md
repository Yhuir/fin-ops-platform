# Canonical Facts Wave 5: Matching State Fallback Removal

日期：2026-06-28

## Scope

删除 `PostgresStateStore._load_matching()` 对旧 `app.app_settings state:matching` JSON snapshot 的生产读取回退。

## Decision

- Matching 的读取事实源是正式 PostgreSQL 表 `app.matching_runs` 和 `app.matching_results`。
- `state:matching` 旧 snapshot 不能在正式表为空或存在时覆盖 matching facts。
- 本 slice 不删除 `PostgresStateStore.save({"matching": ...})` 的旧写入路径；该写入口仍需单独确认是否有生产调用者和正式 owner 写入替代。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_matching_does_not_fallback_to_runtime_snapshot -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。

## Remaining

- `save({"matching": ...})` 旧 `state:matching` 写入已在后续 wave 5 slice 删除。
- 其它 `state:*` 旧 snapshot 读写仍按 wave 5 逐项删除。
