# Canonical Facts Wave 5: App Mongo Shadow/Preflight Tool Guard

日期：2026-06-28

## 目标

历史记录：本 slice 曾临时锁定 App Mongo / local pickle shadow-read、runtime policy preflight 和 controlled mirror-write rehearsal 只能作为显式 CLI 工具路径，不能被 production app/API/worker 主链路当成 canonical facts 读取、恢复或写入入口。后续 wave 5 slice 已删除这些 CLI。

## 当前判断

- `run_shadow_read_rehearsal.py`、`run_runtime_state_policy_preflight.py` 和 `run_controlled_mirror_write_rehearsal.py` 已在后续 wave 5 slice 删除。
- app/services 当前没有引用这些工具模块。

## 变更

- 原 guard 曾禁止 `backend/src/fin_ops_platform/app/` 和 `backend/src/fin_ops_platform/services/` 引用三个 tool module。
- 后续 guard 改为 `test_app_mongo_shadow_preflight_tools_are_removed`，要求三个 CLI 文件不存在且 production app/services 不能引用旧模块名。

## 验证

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_app_mongo_shadow_preflight_tools_are_removed -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
```

结果：通过。

## Closure 状态

本 slice 是历史 tool-only 隔离证明，不是最终删除闭环。后续 slice 已删除 App Mongo/local pickle shadow/preflight/mirror CLI 和旧 cutover preflight checker/CLI。
