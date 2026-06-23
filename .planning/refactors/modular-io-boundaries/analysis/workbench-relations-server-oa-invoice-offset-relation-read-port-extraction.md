# Workbench Relations Server OA Invoice Offset Relation Read Port Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:server-oa-invoice-offset-relation-read-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move OA invoice offset auto-pair sync precondition active relation reads behind an explicit read port without changing command-service writes, relation filtering, changed scopes, persistence scheduling, derived lifecycle events, API response shape or frontend behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-repair-precondition-relation-read-port-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_platform_runtime_boundary_guards.py`
- Text search for `_sync_oa_invoice_offset_auto_pair_relations`, `OA_INVOICE_OFFSET_AUTO_MATCH_MODE`, `list_active_relations`, and OA invoice offset sync tests.

## Changes

- Added `WorkbenchOaInvoiceOffsetRelationReadPort`.
- Added `Application._workbench_oa_invoice_offset_relation_read_port(...)`.
- `_sync_oa_invoice_offset_auto_pair_relations(...)` now reads active OA invoice offset relations through `active_relations_for_mode(OA_INVOICE_OFFSET_AUTO_MATCH_MODE)`.
- Existing command-service `confirm_relation(...)` and `cancel_relation(...)` writes remain unchanged.
- Added static guard coverage for `_sync_oa_invoice_offset_auto_pair_relations(...)`.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| OA invoice offset sync active relation read | explicit-port extracted | `_sync_oa_invoice_offset_auto_pair_relations(...)` uses `WorkbenchOaInvoiceOffsetRelationReadPort`. |
| OA attachment context repair active relation read | next implementation candidate | Still direct `list_active_relations()` and write-adjacent; selected next. |
| Confirm-link context expansion relation read | later confirm precondition port candidate | Still direct `active_relations_for_row_ids(...)`. |
| Auto-pair manual conflict relation read | later auto-pair precondition port candidate | Still direct `get_active_relation_by_row_id(...)`. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice closes only OA invoice offset sync read port extraction. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Decision |
| --- | --- | --- |
| Business core unit tests | Applies indirectly | Existing OA invoice offset sync tests preserve relation filtering and cancellation behavior. |
| Service-layer tests | Applies | Static guard verifies the method uses the explicit read port. |
| API contract tests | Not changed | No HTTP/API response shape changed. |
| Read model/cache/background job tests | Not changed | Derived lifecycle event metadata and persistence scheduling are unchanged. |
| Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| End-to-end business-flow integration tests | Not added for this narrow boundary | Existing Workbench V2 helper regression tests cover the affected behavior. |
| Existing feature regression tests | Applies | OA invoice offset sync regression tests and static guard prevent behavior drift. |

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/workbench_oa_invoice_offset_relation_read_port.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_oa_invoice_offset_sync_uses_relation_read_port -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_oa_invoice_offset_sync_does_not_cancel_relations_outside_current_payload tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_oa_invoice_offset_sync_only_uses_attachment_source_link_not_case_id -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only OA invoice offset sync relation read port extraction. It does not close `workbench_relation`, remove OA attachment repair reads, remove confirm/auto-pair precondition reads, validate production PostgreSQL/worker evidence, or unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:server-oa-attachment-repair-relation-read-port-extraction`
