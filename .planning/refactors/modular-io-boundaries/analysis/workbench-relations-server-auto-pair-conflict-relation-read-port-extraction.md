# Workbench Relations - Server Auto-Pair Conflict Relation Read Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:server-auto-pair-conflict-relation-read-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move `_auto_pair_conflicts_with_manual_relation(...)` active relation reads behind an explicit read port, without changing auto-pair conflict semantics.

This slice only changes the auto-pair precondition read boundary. It does not close `workbench_relation` and does not unblock Go hot-path admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-confirm-link-context-relation-read-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-repair-precondition-relation-read-port-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_workbench_v2_api.py`
- CodeGraph impact for `_auto_pair_conflicts_with_manual_relation`

## Change Summary

- Added `WorkbenchAutoPairConflictRelationReadPort`.
- Added `Application._workbench_auto_pair_conflict_relation_read_port(...)` as dependency assembly only.
- Changed `_auto_pair_conflicts_with_manual_relation(...)` to call `relation_read_port.get_active_relation_by_row_id(...)` instead of reading `_workbench_pair_relation_service.get_active_relation_by_row_id(...)` directly.
- Added a static guard proving the method uses the explicit port and still preserves `SYSTEM_AUTO_PAIR_RELATION_MODES` conflict semantics.

## Preserved Semantics

- Empty or missing active relation continues to be non-conflicting.
- Existing system auto-pair relation modes continue to be allowed.
- Existing manual/non-system relation modes continue to block auto-pairing.
- `_oa_invoice_offset_desired_relations(...)` and `_sync_oa_invoice_offset_auto_pair_relations(...)` behavior remains unchanged.
- Relation writes, read model freshness, dirty scope contract, operation barriers, API response shape, frontend behavior and Go/Fiber/Go Worker admission are unchanged.

## Legacy Classification

- Removed from this method: direct app-level broad pair relation service row relation read.
- New owner: `WorkbenchAutoPairConflictRelationReadPort`.
- Backing reader: `WorkbenchRelationCommandService(require_fresh_relations=False)`.
- Still open and intentionally not changed in this slice:
  - transaction-persist surfaces
  - rollback surfaces
  - case-id allocation surfaces
  - whole-state persistence snapshot surfaces
  - final `workbench_relation` closure accounting

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:server-auto-pair-conflict-relation-read-port-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:post-server-precondition-local-implementation-closure-audit`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no auto-pair rule changed.
2. Service-layer tests: covered by static architecture guard for the new read port boundary.
3. API contract tests: not applicable; no HTTP contract changed.
4. Read model/cache/background job tests: not directly changed; auto-pair candidate behavior is preserved by existing Workbench API regressions.
5. Frontend component and interaction tests: not applicable; no frontend code or UI behavior changed.
6. End-to-end business-flow integration tests: not added for this narrow internal read-port extraction.
7. Existing feature regression tests: covered by salary and internal transfer auto-match candidate regressions.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_auto_pair_conflict_relation_read_port.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_auto_pair_conflict_uses_relation_read_port -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_keeps_salary_auto_match_as_candidate_until_no_oa_submit -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_keeps_internal_transfer_auto_match_as_candidate_until_no_oa_submit -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this slice is closed. `workbench_relation` remains `implementation-gap-open`.
