# Canonical Facts Wave 5 - Tool runtime application I/O tightening

日期：2026-06-29

## 目标

把仍需保留的运维工具中对 `Application` 私有成员的读取集中到 `backend/src/fin_ops_platform/tools/runtime_application.py`，避免业务工具文件继续直接把 `Application` 当事实源容器。

本 slice 不删除当前 runbook 仍需要的工具：

- `restore_bank_auto_tag_rules.py`
- `link_existing_etc_batches.py`
- `migrate_historical_etc_business_batches.py`
- `cleanup_orphan_etc_reconciliation_tasks.py`

## 变更

- `runtime_application.py` 增加命名 tool runtime ports：
  - bank auto tag rules restore runtime；
  - ETC/import service readers；
  - ETC reconciliation task service reader；
  - Workbench relation command/reader；
  - object identity repository reader；
  - Workbench relation persistence / scope invalidation callbacks。
- `restore_bank_auto_tag_rules.py` 不再 import/call `build_application(...)`，改走 `bank_auto_tag_rules_runtime(...)`。
- ETC historical migration/link/cleanup 工具不再直接写 `app._...`，改走 `runtime_application.py` 的命名 port。
- `test_canonical_fact_tools_use_runtime_application_state_io_boundary` 收紧为：除 `runtime_application.py` 外，tools 目录不得直接调用 `build_application(`、`app._`、`_state_store` 或 `_initialize_runtime_services`。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/tools/runtime_application.py backend/src/fin_ops_platform/tools/restore_bank_auto_tag_rules.py backend/src/fin_ops_platform/tools/link_existing_etc_batches.py backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py backend/src/fin_ops_platform/tools/cleanup_orphan_etc_reconciliation_tasks.py tests/test_restore_bank_auto_tag_rules_tool.py tests/test_migrate_historical_etc_business_batches_tool.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_restore_bank_auto_tag_rules_tool tests.test_link_existing_etc_batches_tool tests.test_migrate_historical_etc_business_batches_tool -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_tools_use_runtime_application_state_io_boundary -v
rg -n "build_application\\(|app\\._|application\\._|_state_store|_initialize_runtime_services" backend/src/fin_ops_platform/tools -g '*.py'
```

Result: only `runtime_application.py` has direct Application/private runtime access; `repair_no_oa_bank_batch_lifecycle.py` only imports `PostgresStateStore` and is not Application-private contamination.

## 剩余风险

`runtime_application.py` 仍是 tool-only 隔离层，不是最终 canonical facts closure。后续删除条件不变：这些工具迁入 owner module service/repository ports，或确认不再需要后删除。
