# Canonical Facts Wave 5 - PostgreSQL Migration Reconcile Tool Removal

Date: 2026-06-29

## Scope

Removed the legacy stage-04 PostgreSQL migration reconciliation tool:

- `backend/src/fin_ops_platform/tools/reconcile_postgres_migration.py`
- `tests/test_reconcile_postgres_migration.py`

## Evidence

- CodeGraph impact for `reconcile_postgres_migration` only found the tool file itself.
- Repository search found no current docs or runbook references.
- The only external reference was `tests/test_reconcile_postgres_migration.py`.
- The tool read `staging.mongo_exports` / `staging.mongo_raw_records`, which are migration-era App Mongo staging tables, not current canonical facts runtime owners.

## Decision

Delete instead of isolate. No active named migration/audit/rollback operation requires this tool, and retaining it would keep a stale Mongo staging reconciliation path without an owner runbook.

## Verification

Passed:

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_postgres_migration_reconcile_tool_is_removed
rg -n "reconcile_postgres_migration" backend/src tests -g '*.py'
```

The final `rg` match in code/tests is only the removal guard.
