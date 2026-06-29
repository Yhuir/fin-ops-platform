# Wave 5 - ApplicationStateStore imports/file-imports/matching Mongo snapshot removal

日期：2026-06-29

## Scope

本切片删除 `ApplicationStateStore` 中 imports、file-imports、matching 旧 App Mongo detailed/split/legacy snapshot 路径。

不修改 07-owned read model runtime 文件，不改变 PostgreSQL canonical facts owner。

## Boundary

- 生产 canonical facts：PostgreSQL owner repositories / business modules。
- `ApplicationStateStore`：仅保留 local pickle tooling/test store。
- 禁止旧链路：App Mongo detailed collections、legacy full snapshot collection、split state collections、file metadata/GridFS metadata fallback。

## I/O

输入：

- local `state.pkl`
- local import file path

输出：

- local `state.pkl`
- local import file content

删除的旧 I/O：

- App Mongo `application_state`
- App Mongo split state collections
- App Mongo imports/file-imports/matching detailed collections
- App Mongo import file metadata collection

## Validation

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py tests/test_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store.StateStoreTests.test_state_store_persists_and_loads_local_snapshot tests.test_state_store.StateStoreTests.test_state_store_load_ignores_app_mongo_config tests.test_state_store.StateStoreTests.test_store_import_file_round_trips_locally
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_import_matching_snapshots_do_not_use_app_mongo tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline
```

结果：通过。

## Remaining

08 仍处于 `wave-5-code-removal`。`ApplicationStateStore` 中其它尚未删除的 local/tooling legacy helper 需要按后续 bounded slice 继续处理；GridFS production worker 删除仍受 07-owned worker registry 协调限制。
