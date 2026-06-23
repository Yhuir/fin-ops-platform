# Workbench Relations WorkbenchWriteFacade Cash Special Metadata Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:workbench-write-facade-cash-special-metadata-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move WorkbenchWriteFacade cash special metadata update/clear calls behind an explicit mutation port while preserving cash special validation, stale conflict checks, metadata payloads, history operation names, response shape, pair relation persist scheduling and read model scheduling.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-cash-special-metadata-boundary-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-relation-read-snapshot-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Changes

- Added `WorkbenchWriteRelationSpecialMetadataMutationPort`.
- Moved WorkbenchWriteFacade direct cash special metadata mutations behind the port:
  - `update_special_metadata_for_row_ids(...)`
  - `clear_special_metadata_for_row_ids(...)`
- Injected `WorkbenchWriteRelationSpecialMetadataMutationPort(self._workbench_pair_relation_service)` from `Application._workbench_write_facade(...)`.
- Removed `WorkbenchWriteFacade`'s direct `_pair_relation_service` field.
- Preserved `pair_relation_service` as a constructor parameter only for default port construction and compatibility with direct tests/builders.
- Strengthened the static guard so WorkbenchWriteFacade must use both explicit ports and cannot directly call pair service read/snapshot or cash special mutation methods.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| WorkbenchWriteFacade direct special metadata update/clear calls | removed from facade internals | Calls now go through `_relation_special_metadata_mutation_port`. |
| `WorkbenchWriteRelationSpecialMetadataMutationPort` adapter calls | compat adapter | Adapter is the explicit boundary over existing pair service mutation primitives. |
| `WorkbenchPairRelationService.update_special_metadata_for_row_ids(...)` | canonical in-memory primitive for now | Still used behind the port; future command-service native rewrite remains separate. |
| `WorkbenchPairRelationService.clear_special_metadata_for_row_ids(...)` | canonical in-memory primitive for now | Still used behind the port; future clear/replace command contract remains separate. |

This removes the broad pair service from WorkbenchWriteFacade's business flow. The remaining pair service references in `workbench_write_facade.py` are confined to explicit adapter classes.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice updates only progress/accounting: `workbench-relations:workbench-write-facade-cash-special-metadata-port-extraction` moves from `pending` to `implementation-closed`. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Decision |
| --- | --- | --- |
| Business core unit tests | Regression-applicable | Cash amount, ticket amount, project requirement, row type validation and stale conflict behavior are covered through Workbench write characterization tests. |
| Service-layer tests | Applicable | Ran cash special characterization tests for duplicate update/clear, stale current behavior, stale expected-version rejection and scheduling failure. |
| API contract tests | Regression-applicable | Cash special characterization uses API route posts and verifies status/payload behavior for success/conflict/failure paths. |
| Read model/cache/background job tests | Regression-applicable | Scheduling failure test proves mutation still occurs before read model scheduling failure propagates; pair relation/read model scheduling call counts remain protected by characterization coverage. |
| Frontend component and interaction tests | Not applicable | No frontend code or UI behavior changed. |
| End-to-end business-flow integration tests | Not added for this adapter extraction | Existing backend route characterization covers the affected flow; no browser behavior changed. |
| Existing feature regression tests | Applicable | Static guard and Workbench write characterization protect existing cash special behavior and boundary rules. |

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_write_facade_relation_reads_and_cash_special_mutations_use_ports tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_personal_advance_repayment_uses_relation_command_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_duplicate_cash_special_updates_and_clears_are_replayed_current_behavior tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_stale_cash_special_updates_first_active_relation_for_rows_current_behavior tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_cash_special_with_stale_expected_relation_rejects_all_entrypoints tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_cash_special_scheduling_failure_propagates_after_metadata_mutation -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the WorkbenchWriteFacade cash special metadata mutation port extraction. It does not close `workbench_relation`, does not implement command-service native clear/replace metadata commands, does not validate production PostgreSQL/worker evidence, and does not unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:workbench-write-facade-post-port-local-implementation-closure-audit`
