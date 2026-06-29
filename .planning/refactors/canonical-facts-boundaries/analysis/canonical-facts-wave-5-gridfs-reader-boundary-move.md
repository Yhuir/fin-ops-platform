# Wave 5 - GridFS Reader Boundary Move

日期：2026-06-29

## Target

把 legacy GridFS reader 从 PostgreSQL state store 文件移出，限制到 file-object migration 边界。

## Changes

- `LegacyGridFSFileReader` 从 `postgres_state_store.py` 移到 `file_object_migration.py`。
- `app/worker.py` 从 `file_object_migration.py` 导入 `LegacyGridFSFileReader` 和 `GridFSObjectMigrationService`。
- `postgres_state_store.py` 不再 import `load_mongo_state_settings`，不再暴露 legacy GridFS reader。
- 更新 runtime/bootstrap 和 platform boundary guard，证明 PostgreSQL state store 不再携带 legacy GridFS reader。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/file_object_migration.py backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/app/worker.py tests/test_runtime_bootstrap.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_postgres_state_store_does_not_expose_legacy_gridfs_reader tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline
```

## Result

Legacy GridFS access remains blocked from normal API/runtime state store. The remaining production worker deletion is still blocked by 07-owned `runtime_worker_registry.py`.
