# Wave 5 - ApplicationStateStore tax imports Mongo branch removal

日期：2026-06-29

## 目标

删除 `ApplicationStateStore` 中 tax certified imports / tax offset plan 的旧 App Mongo / mongo-only 分支。

## 变更

- `load_tax_certified_imports(...)` / `save_tax_certified_imports(...)` 只保留本地 pickle I/O。
- `save_tax_offset_plan(...)` 不再检查 `MONGO_ONLY_STORAGE_MODE`。
- 新增 static guard 和本地 round-trip/idempotency 测试。

## 边界结论

- 不改变 PostgreSQL canonical facts owner repository：生产 tax facts 仍由 `PostgresOpsTaxEtcRepository` / `PostgresStateStore` 管理。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_tax_imports_and_offset_plan_persist_locally -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_tax_imports_do_not_use_app_mongo -v
```

结果：通过。
