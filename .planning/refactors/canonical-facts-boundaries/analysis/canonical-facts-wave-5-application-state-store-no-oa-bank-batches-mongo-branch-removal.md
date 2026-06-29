# Wave 5 - ApplicationStateStore no-OA bank batches Mongo branch removal

日期：2026-06-29

## 目标

删除 `ApplicationStateStore` 中 no-OA bank batches 的旧 App Mongo 分支。

## 变更

- `load_no_oa_bank_batches(...)` / `save_no_oa_bank_batches(...)` 不再读写 Mongo detailed collection。
- 以上方法不再检查 `MONGO_ONLY_STORAGE_MODE`。
- 新增 static guard；行为复用已有本地 round-trip 测试。

## 边界结论

- 不改变 `ApplicationStateStoreProtocol`。
- 不修改 PostgreSQL canonical facts owner repository。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_save_no_oa_bank_batches_persists_and_loads_local_snapshot -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_no_oa_bank_batches_do_not_use_app_mongo -v
```

结果：通过。
