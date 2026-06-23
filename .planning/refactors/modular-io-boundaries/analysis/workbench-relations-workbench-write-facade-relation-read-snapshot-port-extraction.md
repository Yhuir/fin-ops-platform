# Workbench Relations WorkbenchWriteFacade Relation Read Snapshot Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:workbench-write-facade-relation-read-snapshot-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move `WorkbenchWriteFacade` active relation reads, withdraw preview fallback and pair snapshot calls behind an explicit read/snapshot port while preserving command-service-backed writes, rollback behavior, API payloads, dirty scope semantics and Workbench active generation behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-pair-service-boundary-audit.md`
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
- CodeGraph status for the current workspace index.

## Changes

- Added `WorkbenchWriteRelationReadSnapshotPort` in `workbench_write_facade.py`.
- Moved these direct `WorkbenchWriteFacade` pair service reads/snapshots behind the port:
  - `active_relations_for_row_ids(...)`
  - `get_active_relation_by_row_id(...)`
  - `preview_withdraw_for_row_ids(...)`
  - `snapshot()`
- Injected `WorkbenchWriteRelationReadSnapshotPort(self._workbench_pair_relation_service)` from `Application._workbench_write_facade(...)`.
- Kept `pair_relation_service` in `WorkbenchWriteFacade` because cash special metadata mutation still uses:
  - `update_special_metadata_for_row_ids(...)`
  - `clear_special_metadata_for_row_ids(...)`
- Added a static guard proving `WorkbenchWriteFacade` no longer directly calls pair service read/snapshot methods outside the new port, while keeping cash special metadata mutation visible for the later boundary.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `WorkbenchWriteFacade` direct active relation reads | removed from facade internals | Calls now go through `_relation_read_snapshot_port`. |
| `WorkbenchWriteFacade` direct withdraw preview fallback | removed from facade internals | Call now goes through `_relation_read_snapshot_port.preview_withdraw_for_row_ids(...)`. |
| `WorkbenchWriteFacade` direct pair snapshots | removed from facade internals | Calls now go through `_relation_read_snapshot_port.snapshot()`. |
| `WorkbenchWriteRelationReadSnapshotPort` adapter calls | compat adapter | Adapter is the explicit boundary over the existing pair relation service until a narrower canonical read repository is selected. |
| Cash special metadata mutation | pending later boundary | Direct `update_special_metadata_for_row_ids(...)` and `clear_special_metadata_for_row_ids(...)` remain intentionally unchanged. |

The old read/snapshot calls no longer pollute the Workbench write facade's business flow. The remaining direct pair service mutation is isolated to cash special metadata and must be audited next before any module closure claim.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice updates only progress/accounting: `workbench-relations:workbench-write-facade-relation-read-snapshot-port-extraction` moves from `pending` to `implementation-closed`. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Decision |
| --- | --- | --- |
| Business core unit tests | Not directly applicable | No relation mode, amount rule, state transition, permission decision or idempotency rule changed. Existing Workbench write characterization tests protect the behavior. |
| Service-layer tests | Applicable | Ran full `tests.test_workbench_write_characterization` to cover confirm/cancel/withdraw/UoW/idempotency/rollback behavior through the facade. |
| API contract tests | Not directly applicable | No HTTP route, status code, response shape or request payload changed. App check was run to verify wiring. |
| Read model/cache/background job tests | Regression-applicable | Dirty scope/read model scheduling behavior is preserved by Workbench write characterization tests for confirm/withdraw invalidation and scheduling failure rollback. No refresh semantics changed. |
| Frontend component and interaction tests | Not applicable | No frontend code or UI behavior changed. |
| End-to-end business-flow integration tests | Not added for this narrow adapter extraction | Existing characterization covers backend flow behavior; no cross-page payload or browser behavior changed. |
| Existing feature regression tests | Applicable | Added a static boundary guard and ran Workbench write characterization to ensure existing behavior remains unchanged. |

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_write_facade.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_write_facade_relation_reads_use_read_snapshot_port tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_personal_advance_repayment_uses_relation_command_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

## Completion Claim

This slice closes only the WorkbenchWriteFacade read/snapshot port extraction. It does not close `workbench_relation`, does not migrate cash special metadata mutation, does not validate production PostgreSQL/worker evidence, and does not unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:workbench-write-facade-cash-special-metadata-boundary-audit`
