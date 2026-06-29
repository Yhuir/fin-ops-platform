# Canonical Facts Wave 5 - Import Fact Consistency Tool Removal

Date: 2026-06-29

## Scope

Removed the unregistered legacy cutover audit tool:

- `backend/src/fin_ops_platform/tools/check_import_fact_consistency.py`

## Evidence

- CodeGraph found no callers for `check_import_fact_consistency`.
- Repository text search found no current docs, tests or runbook entry that names this tool.
- The tool only checked legacy Mongo linkage fields such as `legacy_mongo_id` / `legacy_source_batch_id` after snapshot cutover.

## Decision

Delete instead of isolate. It is not a current named migration/audit/rollback operation, so keeping it would preserve a stale migration-era audit path without owner/runbook/deletion criteria.

## Verification

Passed:

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_import_fact_consistency_tool_is_removed
rg -n "check_import_fact_consistency" backend/src tests -g '*.py'
```

The final `rg` match in code/tests is only the removal guard.
