# Wave 5 - ApplicationStateStore Cost/Tax Read Model Mongo Branch Removal

日期：2026-06-29

## 范围

- 删除 `ApplicationStateStore.load_cost_statistics_read_models(...)`、`save_cost_statistics_read_models(...)`、`load_tax_offset_read_models(...)`、`save_tax_offset_read_models(...)` 的旧 App Mongo detailed collection / `MONGO_ONLY_STORAGE_MODE` 分支。
- 删除旧 cost/tax read model detailed collection 常量、metadata 映射、full snapshot 聚合调用和 detailed load/save helper。
- 保留 `ApplicationStateStore` 作为 local tooling/test store 的本地 pickle I/O。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

## 边界

- 生产 cost statistics / tax offset read model projection 由 PostgreSQL read model/repository owner 管理。
- `ApplicationStateStore` 不再能够通过这组方法读取或写入 App Mongo read model snapshot。
- 本切片不改变 HTTP/API contract、read model freshness、worker registry 或 durable queue contract。

## I/O

输入：

- `snapshot: dict[str, Any]`
- 可选 `changed_scope_keys` 参数；local store 接受但不执行 Mongo 增量集合写
- local tooling/test `data_dir`

输出：

- 本地 `state.pkl` 中的 `cost_statistics_read_models` 和 `tax_offset_read_models` snapshot

禁止 I/O：

- `_mongo_database`
- `_mongo_detailed_collections`
- `MONGO_ONLY_STORAGE_MODE`
- `COST_STATISTICS_READ_MODELS_*`
- `TAX_OFFSET_READ_MODELS_*`
- `_load_cost_statistics_read_models_detailed_payload`
- `_load_tax_offset_read_models_detailed_payload`
- `_save_cost_statistics_read_models_detailed`
- `_save_tax_offset_read_models_detailed`

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_save_cost_statistics_read_models_persists_locally_across_store_instances tests.test_state_store.StateStoreTests.test_save_cost_statistics_read_models_accepts_changed_scopes_for_local_snapshot tests.test_state_store.StateStoreTests.test_save_tax_offset_read_models_persists_locally_across_store_instances tests.test_state_store.StateStoreTests.test_save_tax_offset_read_models_accepts_changed_scopes_for_local_snapshot -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_cost_and_tax_read_models_do_not_use_app_mongo tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
git diff --check
bash scripts/verify.sh docs
```

结果：通过。
