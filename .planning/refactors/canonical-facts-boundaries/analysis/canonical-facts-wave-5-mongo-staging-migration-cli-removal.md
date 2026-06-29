# Canonical Facts Wave 5 - Mongo Staging Migration CLI Removal

Date: 2026-06-29

## Scope

Removed legacy Mongo export/staging CLI wrappers:

- `backend/src/fin_ops_platform/tools/import_postgres_staging.py`
- `backend/src/fin_ops_platform/tools/transform_staging_to_postgres.py`
- `tests/test_import_postgres_staging.py`

## Evidence

- Repository search found no current docs/runbook references for either CLI.
- CodeGraph impact showed `import_postgres_staging` was referenced only by its own test and by `transform_staging_to_postgres.py`.
- CodeGraph impact showed `transform_staging_to_postgres` had no external caller.
- A follow-up slice deleted `postgres_transform.py` and `tests/test_postgres_transform.py`; this CLI-removal slice no longer depends on retained transform test code.

## Decision

Delete the CLI wrappers instead of isolating them. They are migration-era Mongo staging entrypoints, not current named operational tools. Keeping them would preserve old App Mongo-to-PostgreSQL migration paths without current owner/runbook criteria.

## Verification

Passed:

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_mongo_staging_migration_cli_tools_are_removed
rg -n "import_postgres_staging|transform_staging_to_postgres" backend/src tests -g '*.py'
```

The final `rg` match in code/tests is only the removal guard.
