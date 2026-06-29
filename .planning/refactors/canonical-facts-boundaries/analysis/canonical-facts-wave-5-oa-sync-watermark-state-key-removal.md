# Wave 5 - OA Sync Watermark state:* Key Removal

日期：2026-06-29

## Target

删除 `app.oa_sync_watermarks` 中继续使用 `state:*` 命名的 OA sync state key。

## Changes

- `PostgresOpsTaxEtcRepository.load_oa_sync_state()` 读取 `sync_key='oa_sync_state'`。
- `PostgresOpsTaxEtcRepository.save_oa_sync_state(...)` 写入 `sync_key='oa_sync_state'`。
- `tests/test_postgres_state_store.py` 增加负向断言，防止 `sync_key='state:oa_sync_state'` 回归。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_store_snapshot_methods_round_trip_without_full_state_fallback tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_canonical_fact_saves_do_not_write_runtime_settings_snapshots tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_canonical_fact_snapshots_do_not_fallback_to_runtime_settings
```

## Result

OA sync state no longer writes or prefers any `state:*` key in `app.app_settings` or `app.oa_sync_watermarks`.
