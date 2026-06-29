# Wave 5 - ApplicationStateStore Bank Transaction Categories Mongo Branch Removal

日期：2026-06-29

## 范围

- 删除 `ApplicationStateStore.load_bank_transaction_categories(...)` 和 `save_bank_transaction_categories(...)` 的旧 App Mongo detailed collection / `MONGO_ONLY_STORAGE_MODE` 分支。
- 保留 `ApplicationStateStore` 作为 local tooling/test store 的本地 pickle I/O。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

## 边界

- 生产 bank transaction category facts 由 PostgreSQL workbench repository / service 管理。
- `ApplicationStateStore` 不再能够通过这组方法读取或写入 App Mongo snapshot facts。
- 本切片不改变 HTTP/API contract、read model freshness、worker registry 或 durable queue contract。

## I/O

输入：

- `snapshot: dict[str, Any]`
- local tooling/test `data_dir`

输出：

- 本地 `state.pkl` 中的 `bank_transaction_categories` snapshot
- `load_bank_transaction_categories()` 返回 dict，缺失或非 dict 时返回 `{}`

禁止 I/O：

- `_mongo_database`
- `_mongo_detailed_collections`
- `MONGO_ONLY_STORAGE_MODE`

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_bank_transaction_categories_persist_locally_across_store_instances -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_bank_transaction_categories_do_not_use_app_mongo tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
git diff --check
bash scripts/verify.sh docs
```

结果：通过。
