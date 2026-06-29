# Canonical Facts Wave 5: PostgreSQL GridFS Read Fallback Removal

日期：2026-06-29

## Scope

删除 `PostgresStateStore` 文件读取路径里的 legacy GridFS fallback：

- `legacy_file_reader` constructor parameter
- `FIN_OPS_ENABLE_LEGACY_GRIDFS_READS`
- `_legacy_file_reader` runtime state
- `read_import_file("gridfs://...")` 旧读取分支

## Decision

- Production file reads must use verified object storage records.
- Legacy GridFS 只能作为 migration worker/tool input，不能作为 PostgreSQL state store read fallback。
- 本 slice 保留 `LegacyGridFSFileReader` class 给现有 migration worker/tools；worker flag / runtime registry 是后续 GridFS migration deletion or blocker slice。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_postgres_state_store.py tests/test_runtime_bootstrap.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_store_rejects_legacy_gridfs_reference tests.test_runtime_bootstrap.RuntimeBootstrapTests.test_postgres_state_store_does_not_auto_configure_legacy_gridfs_reader tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime -v
```

结果：通过。
