# Wave 5 - ApplicationStateStore OA pending payment relations Mongo branch removal

日期：2026-06-29

## 目标

删除 `ApplicationStateStore` 中 OA pending payment bank relations 的旧 App Mongo / whole snapshot 分支。

## 变更

- `load_oa_pending_payment_bank_relations(...)` 只读本地 pickle snapshot。
- `save_oa_pending_payment_bank_relations(...)` 只写本地 pickle snapshot。
- 以上方法不再调用 `self.load()` / `self.save(...)` 进入旧 Mongo/full snapshot 路径，也不再检查 `MONGO_ONLY_STORAGE_MODE`。
- 新增 static guard 和本地 round-trip 测试。

## 边界结论

- 不改变 PostgreSQL canonical facts owner repository：生产事实源仍是 `app.oa_pending_payment_bank_relations`。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_oa_pending_payment_bank_relations_persist_locally_across_store_instances -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_oa_pending_payment_bank_relations_do_not_use_app_mongo -v
```

结果：通过。
