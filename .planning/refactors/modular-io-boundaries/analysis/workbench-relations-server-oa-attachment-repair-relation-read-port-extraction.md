# Workbench Relations - Server OA Attachment Repair Relation Read Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:server-oa-attachment-repair-relation-read-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move `_repair_active_relations_with_oa_attachment_context(...)` active relation reads behind an explicit read port, without changing relation repair semantics or canonical write paths.

This is a narrow implementation slice. It does not close the `workbench_relation` module and does not unblock Go hot-path admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-repair-precondition-relation-read-port-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-oa-invoice-offset-relation-read-port-extraction.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_workbench_v2_api.py`

## Change Summary

- Added `WorkbenchOaAttachmentRepairRelationReadPort`.
- Added `Application._workbench_oa_attachment_repair_relation_read_port(...)` as dependency assembly only.
- Changed `_repair_active_relations_with_oa_attachment_context(...)` to call `relation_read_port.list_active_relations()` instead of reading `_workbench_pair_relation_service.list_active_relations()` directly.
- Added a static guard proving the repair method uses the explicit port and still preserves `replace_existing=True` and `before_relations=[before_relation]`.

## Preserved Semantics

- Dedicated-withdraw relation filtering remains unchanged.
- Missing OA attachment invoice detection remains unchanged.
- Full before-relation payload capture remains unchanged.
- `WorkbenchRelationCommandService.confirm_relation(..., replace_existing=True)` remains the canonical write path.
- Changed case ids and changed read model scope keys remain unchanged.
- Derived lifecycle event metadata and persistence scheduling remain unchanged.
- API response shape, dirty scope contract, operation barrier behavior, frontend behavior and Go/Fiber/Go Worker admission are unchanged.

## Legacy Classification

- Removed from this method: direct app-level broad pair relation service active relation read.
- New owner: `WorkbenchOaAttachmentRepairRelationReadPort`.
- Retained canonical writer: `WorkbenchRelationCommandService`.
- Still open and intentionally not changed in this slice:
  - `_expand_confirm_link_row_ids_for_existing_context(...)`
  - `_auto_pair_conflicts_with_manual_relation(...)`
  - transaction-persist surfaces
  - rollback surfaces
  - case-id allocation surfaces
  - whole-state persistence snapshot surfaces

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:server-oa-attachment-repair-relation-read-port-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:server-confirm-link-context-relation-read-port-extraction`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business rule or state transition changed.
2. Service-layer tests: covered by static architecture guard for the new read port boundary.
3. API contract tests: not applicable; no HTTP contract changed.
4. Read model/cache/background job tests: not directly changed; preserved by Workbench repair regression.
5. Frontend component and interaction tests: not applicable; no frontend behavior changed.
6. End-to-end business-flow integration tests: not added for this narrow internal read-port extraction.
7. Existing feature regression tests: covered by the existing Workbench V2 repair regression for missing OA attachment invoice context.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_oa_attachment_repair_relation_read_port.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_oa_attachment_repair_uses_relation_read_port -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_read_model_repairs_active_relation_missing_oa_attachment_invoice -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this slice is closed. `workbench_relation` remains `implementation-gap-open`.
