# Wave 5 - PostgresStateStore State Module Import Removal

日期：2026-06-29

## Target

移除 PostgreSQL production state store 对 local `state_store.py` 模块的最后 import。

## Changes

- `PostgresStateStore` 本地定义 `GRIDFS_REF_PREFIX = "gridfs://"`。
- `postgres_state_store.py` 不再 import `fin_ops_platform.services.state_store`。
- `test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime` 禁止 PostgreSQL state store 恢复该 import。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_gridfs_legacy_reader_stays_out_of_normal_api_runtime tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_store_rejects_legacy_gridfs_reference
```

## Result

PostgreSQL state store no longer imports the local pickle state-store module.
