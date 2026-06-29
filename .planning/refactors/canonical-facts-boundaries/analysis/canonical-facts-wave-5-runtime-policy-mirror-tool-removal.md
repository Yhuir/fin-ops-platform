# Canonical Facts Wave 5: Runtime Policy / Mirror Tool Removal

日期：2026-06-29

## Scope

删除剩余旧 App Mongo/local pickle runtime policy / controlled mirror-write CLI：

- `backend/src/fin_ops_platform/tools/run_runtime_state_policy_preflight.py`
- `backend/src/fin_ops_platform/tools/run_controlled_mirror_write_rehearsal.py`
- `tests/test_stage15_runtime_tools.py`

## Decision

- 两个 CLI 直接构造 local pickle / App Mongo readonly `ApplicationStateStore`，并用于旧 runtime state 与 PostgreSQL 的 policy / mirror rehearsal。
- `run_controlled_mirror_write_rehearsal.py` 还包含执行写入分支，虽有 guard，但仍是旧 source-of-truth mirror write 链路。
- CodeGraph 显示 production app/API/worker 没有调用者，只有工具测试和 `run_controlled_mirror_write_rehearsal.py` 对 `run_runtime_state_policy_preflight.py` 的内部依赖。
- 08 closure 目标要求删除非必需旧链路，因此本 slice 不继续保留 tool-only 例外。

## Verification

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_app_mongo_shadow_preflight_tools_are_removed -v
```

结果：通过。
