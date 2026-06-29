# Canonical Facts Wave 6 Tool Runtime State Port Closure

日期：2026-06-29

## 目标

- 完成 canonical facts 剩余维护项中可安全执行的工具 runtime I/O 收口。
- 保留仍有 runbook 价值的 bank/ETC 运维工具。
- 删除旧 `full snapshot application` 语义，避免工具 adapter 暴露整个 `state_store`。

## 变更

- `Application` 增加 `tool_runtime_state_snapshot()`，只返回 retained operational tools 初始化所需的局部 runtime state。
- `Application.tool_runtime_ports()` 不再暴露完整 `state_store`。
- `tools/runtime_application.py` 的 `build_full_snapshot_application(...)` 改为 `build_tool_runtime_application(...)`，并通过 public `tool_runtime_state_snapshot()` / `initialize_tool_runtime_state(...)` 完成初始化。
- ETC historical migration/link/cleanup 工具改用新的 `build_tool_runtime_application(...)`。
- `test_canonical_fact_tools_use_runtime_application_state_io_boundary` 收紧：禁止工具恢复旧 builder 名称，并禁止 `tool_runtime_ports()` 暴露完整 `state_store`。

## 结果

- retained operational tools 仍是运维工具，不是业务事实源。
- `runtime_application.py` 仍作为最小 app-owned tool-port adapter 存在；把它拆成各 owner CLI 现在会复制 `Application` 的依赖组装，收益低且风险高。
- canonical facts 没有新的 final closure blocker。后续仅在这些 runbook 退休时删除对应工具和 adapter。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/tools/runtime_application.py backend/src/fin_ops_platform/tools/link_existing_etc_batches.py backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py backend/src/fin_ops_platform/tools/cleanup_orphan_etc_reconciliation_tasks.py tests/test_migrate_historical_etc_business_batches_tool.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_migrate_historical_etc_business_batches_tool tests.test_link_existing_etc_batches_tool tests.test_restore_bank_auto_tag_rules_tool -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_tools_use_runtime_application_state_io_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_legacy_source_paths_stay_in_removal_baseline -v
```
