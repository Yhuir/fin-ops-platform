# Canonical Facts Wave 5 - State Store Preflight Local Pickle Helper Removal

日期：2026-06-29

## 目标

删除 `state_store_factory.py` 中已无调用的旧 preflight backend helper，避免文件继续声明 `local_pickle and postgres` 是受支持的 preflight backend。

## 变更

- 删除 `backend/src/fin_ops_platform/services/state_store_factory.py::_required_preflight_backend(...)`。
- 删除旧错误信息 `Supported preflight backend values are local_pickle and postgres.`。
- 新增 `tests/test_state_store_factory_preflight.py::StateStoreFactoryPreflightTests.test_local_pickle_preflight_backend_helper_is_removed`，防止该 helper 和旧支持声明回归。

## 边界结论

- app runtime factory 仍只接受 `FIN_OPS_APP_STORAGE_BACKEND=postgres`。
- 本 slice 不重新引入 shadow/dual/preflight backend。
- `ApplicationStateStore` 类本体仍存在，主要由 dev/test/tooling 使用；它不是本 slice 的完成项，仍是 wave 5 剩余 local pickle 删除/隔离范围。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/state_store_factory.py tests/test_state_store_factory_preflight.py
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store_factory_preflight -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
git diff --check
bash scripts/verify.sh docs
```

结果：通过。
