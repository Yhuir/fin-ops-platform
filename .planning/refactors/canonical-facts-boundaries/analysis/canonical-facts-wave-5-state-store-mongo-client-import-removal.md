# Canonical Facts Wave 5 - State Store Mongo Client Import Removal

日期：2026-06-29

## 目标

在 `ApplicationStateStore` 不再构造 App Mongo snapshot store 后，删除 `state_store.py` 顶层已不需要的 Mongo client imports。

## 变更

- 删除 `from gridfs import GridFSBucket`。
- 删除 `from pymongo import MongoClient`。
- 收紧 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source`，防止这两个 imports 回归。

## 边界结论

- 本 slice 不删除 `load_mongo_state_settings(...)`；它暂时仍给 GridFS legacy reader 使用。
- 本 slice 不删除不可达 Mongo branch method body；后续继续清理。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_application_state_store_does_not_open_app_mongo_snapshot_source -v
git diff --check
bash scripts/verify.sh docs
```

结果：通过。
