# Canonical Facts Wave 6 - Tool Runtime Public Port Boundary

## Goal

Remove direct `Application._*` and `_state_store` access from retained canonical-facts operational tools without deleting the tools or touching 07-owned read-model runtime files.

## Change

- Added `Application.initialize_tool_runtime_state(...)` as the public tool bootstrap hook.
- Added `Application.tool_runtime_ports()` as the public app-owned port bundle for retained operational tools.
- Updated `tools/runtime_application.py` to call only public app tool ports.
- Tightened `test_canonical_fact_tools_use_runtime_application_state_io_boundary` so every tool file, including `runtime_application.py`, is forbidden from direct `app._`, `_state_store` or `_initialize_runtime_services` access.
- Updated tool tests to fake the public `tool_runtime_ports()` boundary instead of private app fields.

## Boundary

`tools/runtime_application.py` remains as a small tool adapter because retained bank/ETC operational commands still need app-assembled services. It no longer owns or reaches into private app state directly. Private dependency assembly stays inside `Application`, where it already lives.

This is not a new `UnifiedFactSource` service and does not change canonical facts ownership.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/tools/runtime_application.py tests/test_link_existing_etc_batches_tool.py tests/test_migrate_historical_etc_business_batches_tool.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_migrate_historical_etc_business_batches_tool tests.test_link_existing_etc_batches_tool tests.test_restore_bank_auto_tag_rules_tool -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_canonical_fact_tools_use_runtime_application_state_io_boundary -v
rg -n "app\._|_state_store|_initialize_runtime_services|getattr\(app, \"_state_store\"" backend/src/fin_ops_platform/tools -g '*.py'
```

Result: tests passed. The scan found no app-private tool access; the only remaining `_state_store` text match is `PostgresStateStore` in `repair_no_oa_bank_batch_lifecycle.py`.
