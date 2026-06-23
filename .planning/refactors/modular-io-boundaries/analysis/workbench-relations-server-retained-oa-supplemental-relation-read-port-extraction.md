# Workbench Relations - Server Retained-OA Supplemental Relation Read Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:server-retained-oa-supplemental-relation-read-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move `_supplemental_retained_oa_row_ids(...)` active relation reads behind an explicit read port, without changing retained-OA all-scope payload behavior.

This slice only changes the retained-OA support read boundary. It does not close `workbench_relation` and does not unblock Go hot-path admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-server-precondition-local-implementation-closure-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_workbench_v2_api.py`
- CodeGraph/text search for retained OA all-scope payload behavior.

## Change Summary

- Added `WorkbenchRetainedOaSupplementalRelationReadPort`.
- Added `Application._workbench_retained_oa_supplemental_relation_read_port(...)` as dependency assembly only.
- Changed `_supplemental_retained_oa_row_ids(...)` to call `relation_read_port.list_active_relations()` instead of reading `_workbench_pair_relation_service.list_active_relations()` directly.
- Added a static guard proving the method uses the explicit port and still preserves manual retained row ids, live bank row resolution, cutoff checks and sorted return semantics.

## Preserved Semantics

- Manual retained OA row ids remain included.
- OA/bank relation filtering remains unchanged.
- Bank rows are still resolved through `_resolve_live_rows_direct(..., month_hint="all")`.
- Bank cutoff-date checks still use `_row_is_on_or_after(..., row_type="bank")`.
- Missing live bank rows still skip the relation.
- Returned row ids remain sorted.
- API response shape, read model freshness, dirty scope contract, operation barriers, frontend behavior and Go/Fiber/Go Worker admission are unchanged.

## Legacy Classification

- Removed from this method: direct app-level broad pair relation service active relation list read.
- New owner: `WorkbenchRetainedOaSupplementalRelationReadPort`.
- Backing reader: `WorkbenchRelationCommandService(require_fresh_relations=False)`.
- Still open and intentionally not changed in this slice:
  - `_next_workbench_relation_case_id(...)`
  - transaction-persist closure accounting
  - rollback closure accounting
  - whole-state persistence snapshot surfaces
  - final `workbench_relation` closure accounting

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:server-retained-oa-supplemental-relation-read-port-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:server-case-id-allocation-relation-read-owner-audit`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no retention business rule changed.
2. Service-layer tests: covered by static architecture guard for the new read port boundary.
3. API contract tests: no response shape changed; retained-OA Workbench API regressions cover behavior.
4. Read model/cache/background job tests: not directly changed; read model freshness behavior unchanged.
5. Frontend component and interaction tests: not applicable; no frontend code changed.
6. End-to-end business-flow integration tests: not added for this narrow internal read-port extraction.
7. Existing feature regression tests: covered by retained-OA all-scope API regressions.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_retained_oa_supplemental_relation_read_port.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_retained_oa_supplemental_uses_relation_read_port -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_all_reincludes_old_oa_related_to_recent_bank_after_cutoff -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_all_scopes_mongo_oa_reads_to_retention_months -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this slice is closed. `workbench_relation` remains `implementation-gap-open`.
