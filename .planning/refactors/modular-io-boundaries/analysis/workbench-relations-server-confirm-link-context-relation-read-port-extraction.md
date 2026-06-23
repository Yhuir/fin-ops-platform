# Workbench Relations - Server Confirm-Link Context Relation Read Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:server-confirm-link-context-relation-read-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move `_expand_confirm_link_row_ids_for_existing_context(...)` active relation reads behind an explicit read port, without changing confirm-link preview or submit behavior.

This slice only changes the confirm-link context expansion read boundary. It does not close `workbench_relation` and does not unblock Go hot-path admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-oa-attachment-repair-relation-read-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-repair-precondition-relation-read-port-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_workbench_v2_api.py`
- CodeGraph impact for `_expand_confirm_link_row_ids_for_existing_context`

## Change Summary

- Added `WorkbenchConfirmLinkContextRelationReadPort`.
- Added `Application._workbench_confirm_link_context_relation_read_port(...)` as dependency assembly only.
- Changed `_expand_confirm_link_row_ids_for_existing_context(...)` to call `relation_read_port.active_relations_for_row_ids(...)` instead of reading `_workbench_pair_relation_service.active_relations_for_row_ids(...)` directly.
- Added a static guard proving the method uses the explicit port and still preserves normalization plus cached existing context expansion.

## Preserved Semantics

- Selected row id normalization remains unchanged.
- Active relation context expansion remains unchanged.
- Duplicate/self row exclusion through the `seen` set remains unchanged.
- Cached existing context group expansion remains unchanged.
- Confirm-link preview and submit behavior remain unchanged.
- Relation writes, read model freshness, dirty scope contract, operation barriers, API response shape, frontend behavior and Go/Fiber/Go Worker admission are unchanged.

## Legacy Classification

- Removed from this method: direct app-level broad pair relation service active relation read.
- New owner: `WorkbenchConfirmLinkContextRelationReadPort`.
- Backing reader: `WorkbenchRelationCommandService(require_fresh_relations=False)`.
- Still open and intentionally not changed in this slice:
  - `_auto_pair_conflicts_with_manual_relation(...)`
  - transaction-persist surfaces
  - rollback surfaces
  - case-id allocation surfaces
  - whole-state persistence snapshot surfaces

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:server-confirm-link-context-relation-read-port-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:server-auto-pair-conflict-relation-read-port-extraction`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no relation state transition rule changed.
2. Service-layer tests: covered by static architecture guard for the new read port boundary.
3. API contract tests: covered indirectly by Workbench V2 confirm-link preview/submit regression tests; no response shape changed.
4. Read model/cache/background job tests: not directly changed; confirm-link affected scope behavior is preserved by existing regression coverage.
5. Frontend component and interaction tests: not applicable; no frontend code or UI behavior changed.
6. End-to-end business-flow integration tests: not added for this narrow internal read-port extraction.
7. Existing feature regression tests: covered by confirm-link active relation context and OA attachment context regression tests.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_confirm_link_context_relation_read_port.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_confirm_link_context_uses_relation_read_port -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_includes_active_relation_rows_for_selected_oa_context -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_includes_existing_oa_attachment_context_rows -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this slice is closed. `workbench_relation` remains `implementation-gap-open`.
