# Canonical Facts Wave 5: State Store Factory PostgreSQL Only

日期：2026-06-29

## Scope

删除 `state_store_factory.build_state_store(...)` 的默认 local / mongo / auto fallback：

- unset `FIN_OPS_APP_STORAGE_BACKEND`
- `auto`
- `local`
- `local_pickle`
- `mongo`
- `mongo_pickle`

## Decision

- `ApplicationStateStore` 本体仍保留给直接单元测试和后续 local pickle implementation slice。
- `build_state_store(...)` 是 app runtime storage admission point；它不应再把未配置或非 PostgreSQL backend 接入 `Application`。
- 本 slice 要求有 `data_dir` 的 app runtime 必须显式 `FIN_OPS_APP_STORAGE_BACKEND=postgres`。

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store_factory.py tests/test_state_store_factory_preflight.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store_factory_preflight -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_default_requires_postgres_backend tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_production_guard_rejects_default_local_storage tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_production_guard_rejects_explicit_local_storage tests.test_postgres_state_store.PostgresStateStoreTests.test_factory_postgres_mode_requires_database_url -v
PYTHONPATH=backend/src python3 -m unittest tests.test_app_postgres_mode.AppPostgresModeTests.test_default_build_application_requires_postgres_backend tests.test_app_postgres_mode.AppPostgresModeTests.test_postgres_backend_without_database_url_fails_clearly tests.test_app_postgres_mode.AppPostgresModeTests.test_readiness_includes_postgres_status_without_uri -v
```

结果：通过。
