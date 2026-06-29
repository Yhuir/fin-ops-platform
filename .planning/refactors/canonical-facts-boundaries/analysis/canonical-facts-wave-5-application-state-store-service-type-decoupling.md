# Wave 5 - ApplicationStateStore service type decoupling

日期：2026-06-28

## 目标

删除 production services 对 local `ApplicationStateStore` 旧事实源实现的直接类型绑定。服务只依赖 state store I/O 合同，不依赖 local pickle 类。

## 变更

- `AppSettingsService`、`BackgroundJobService`、`SettingsDataResetService` 的 `state_store` 类型从 `ApplicationStateStore` 改为已有 `ApplicationStateStoreProtocol`。
- 删除上述服务对 `fin_ops_platform.services.state_store.ApplicationStateStore` 的直接 import。
- 新增 static guard，禁止普通 production service 重新 import local `ApplicationStateStore`。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/app_settings_service.py backend/src/fin_ops_platform/services/background_job_service.py backend/src/fin_ops_platform/services/settings_data_reset_service.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_production_services_do_not_type_bind_to_local_application_state_store tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_settings_data_reset_pair_snapshot_uses_explicit_port -v
```

结果：通过。

## 剩余

`ApplicationStateStore` / local pickle implementation 仍保留给 dev/test/tooling 和 factory preflight 路径。该 slice 只删除 production service 的旧类耦合，不算 local pickle final closure。
