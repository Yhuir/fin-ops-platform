# Canonical Facts Wave 5 - PostgreSQL Transform Tool Removal

Date: 2026-06-29

## Scope

Removed the legacy stage-04 transform implementation and its tests:

- `backend/src/fin_ops_platform/tools/postgres_transform.py`
- `tests/test_postgres_transform.py`

## Evidence

- After deleting the Mongo staging CLI wrappers, repository search showed `postgres_transform.py` was referenced only by `tests/test_postgres_transform.py` and canonical-facts documentation.
- CodeGraph impact for `build_transform_plan` found only `postgres_transform.py` and `tests/test_postgres_transform.py`.
- The transform logic was a migration-era App Mongo staging path, not a current owner module write/read port.

## Decision

Delete instead of continuing to maintain negative tests around a dead migration implementation. The regression guard now proves the old transform tool and tests do not return.

## Verification

Passed:

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_postgres_transform_tool_is_removed
rg -n "postgres_transform|test_postgres_transform|build_transform_plan|StagingRecord|build_transaction_sql" backend/src tests -g '*.py'
```

The final `rg` match in code/tests is only the removal guard.
