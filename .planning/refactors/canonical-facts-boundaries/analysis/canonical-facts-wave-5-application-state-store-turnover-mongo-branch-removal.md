# Wave 5 - ApplicationStateStore Turnover Mongo Branch Removal

日期：2026-06-29

## 范围

- 删除 `ApplicationStateStore.load_turnover_relations(...)`、`save_turnover_relations(...)`、`load_turnover_ledger_extras(...)`、`save_turnover_ledger_extras(...)` 的旧 App Mongo detailed collection / `MONGO_ONLY_STORAGE_MODE` 分支。
- 删除旧 Turnover detailed collection 常量、metadata 映射、full snapshot 聚合调用和 detailed load/save helper。
- 保留 `ApplicationStateStore` 作为 local tooling/test store 的本地 pickle I/O。
- 不修改 07 read-model controller 负责的 runtime/read model 文件。

## 边界

- 生产 Turnover canonical facts 由 PostgreSQL workbench repository / `PostgresStateStore` 管理。
- `ApplicationStateStore` 不再能够通过这组方法读取或写入 App Mongo snapshot facts。
- 本切片不改变 HTTP/API contract、read model freshness、worker registry 或 durable queue contract。

## I/O

输入：

- `snapshot: dict[str, Any]`
- local tooling/test `data_dir`

输出：

- 本地 `state.pkl` 中的 `turnover_relations` 和 `turnover_ledger_extras` snapshot
- `load_turnover_relation_audit_log()` 仍从本地 `turnover_relations.audit_log` 派生 list

禁止 I/O：

- `_mongo_database`
- `_mongo_detailed_collections`
- `MONGO_ONLY_STORAGE_MODE`
- `TURNOVER_RELATIONS_*`
- `TURNOVER_LEDGER_EXTRAS_*`
- `_load_turnover_*_detailed_payload`
- `_save_turnover_*_detailed`

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_save_turnover_relations_persists_locally_across_store_instances tests.test_state_store.StateStoreTests.test_save_turnover_ledger_extras_persists_locally_across_store_instances -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_turnover_facts_do_not_use_app_mongo tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
git diff --check
bash scripts/verify.sh docs
```

结果：通过。
