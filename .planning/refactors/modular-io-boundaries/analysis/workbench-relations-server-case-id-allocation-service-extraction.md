# Workbench Relations - Server Case ID Allocation Service Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:server-case-id-allocation-service-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move relation snapshot parsing and `CASE-AUTO-*` collision avoidance out of `Application._next_workbench_relation_case_id(...)` into an explicit service, while preserving confirm-link auto case id behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-case-id-allocation-relation-read-owner-audit.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Change Summary

- Added `WorkbenchRelationCaseIdAllocator`.
- Moved relation snapshot `pair_relations` parsing and used-case-id collision avoidance into the allocator.
- Kept `Application._next_workbench_relation_case_id(...)` as a thin delegate that wires:
  - `relation_snapshot_provider=self._workbench_pair_relation_service.snapshot`
  - `next_case_id=self._workbench_override_service._next_case_id`
- Added a static guard proving `server.py` no longer parses `pair_relations` in `_next_workbench_relation_case_id(...)`.

## Preserved Semantics

- Confirm-link without explicit `case_id` still allocates `CASE-AUTO-*` ids from `WorkbenchOverrideService`.
- Existing active `CASE-AUTO-0001` is skipped and the next available id is used.
- Duplicate confirm-link without explicit `case_id` still allocates a new case and replaces the active relation as before.
- Relation writes, read model freshness, dirty scope contract, operation barriers, API response shape, frontend behavior and Go/Fiber/Go Worker admission are unchanged.

## Legacy Classification

- Removed from `server.py`: relation snapshot shape parsing in `_next_workbench_relation_case_id(...)`.
- New owner: `WorkbenchRelationCaseIdAllocator`.
- Still open:
  - transaction-persist closure accounting
  - rollback closure accounting
  - whole-state persistence snapshot surfaces
  - final `workbench_relation` closure accounting

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:server-case-id-allocation-service-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:transaction-persist-closure-accounting-audit`

## Seven Test Category Decision

1. Business core unit tests: covered by existing case-id collision characterization tests.
2. Service-layer tests: covered by static guard and existing Workbench write characterization.
3. API contract tests: no response shape changed; confirm-link API behavior is covered through characterization tests.
4. Read model/cache/background job tests: not directly changed.
5. Frontend component and interaction tests: not applicable; no frontend code changed.
6. End-to-end business-flow integration tests: not added for this internal allocation refactor.
7. Existing feature regression tests: covered by duplicate confirm-link and active `CASE-AUTO-0001` skip regressions.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_relation_case_id_allocator.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_case_id_allocation_uses_allocator -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_confirm_link_without_case_id_skips_existing_active_auto_relation_case_id -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_duplicate_confirm_link_without_case_id_allocates_new_case_and_replaces_active_relation -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this slice is closed. `workbench_relation` remains `implementation-gap-open`.
