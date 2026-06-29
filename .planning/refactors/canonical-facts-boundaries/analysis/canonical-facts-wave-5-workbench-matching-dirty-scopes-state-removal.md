# Canonical Facts Wave 5: Workbench Matching Dirty Scopes State Removal

日期：2026-06-28

## Scope

删除 `PostgresStateStore` 对旧 `app.app_settings state:workbench_matching_dirty_scopes` JSON snapshot 的生产读写。

## Decision

- Workbench matching dirty scopes 的正式 runtime source 是 `job.workbench_matching_dirty_scopes`。
- PostgreSQL runtime 不再从 `state:workbench_matching_dirty_scopes` bootstrap in-memory dirty scope service。
- PostgreSQL runtime 不再把 dirty scope service snapshot 写回 `app.app_settings`。
- 07-owned repository / read model runtime 文件只读，本 slice 不编辑。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_workbench_matching_dirty_scopes_do_not_use_runtime_snapshot -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```

结果：通过。
