# Workbench Relations Server Repair Precondition Relation Read Port Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:server-repair-precondition-relation-read-port-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit remaining write-adjacent repair/precondition direct active relation reads in `server.py`, classify each surface, and choose the next smallest safe extraction boundary.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-source-version-relation-snapshot-provider-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-relation-read-helper-boundary-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_platform_runtime_boundary_guards.py`
- Text search for `_sync_oa_invoice_offset_auto_pair_relations`, `_repair_active_relations_with_oa_attachment_context`, `_expand_confirm_link_row_ids_for_existing_context`, `_auto_pair_conflicts_with_manual_relation`, `list_active_relations`, `active_relations_for_row_ids`, and `get_active_relation_by_row_id`.

## Findings

- `_sync_oa_invoice_offset_auto_pair_relations(...)` reads all active relations only to find existing `OA_INVOICE_OFFSET_AUTO_MATCH_MODE` relations, then creates/cancels via `WorkbenchRelationCommandService`. This is a narrow auto-repair/sync precondition read with existing focused tests.
- `_repair_active_relations_with_oa_attachment_context(...)` reads all active relations, filters out dedicated-withdraw relations, calculates missing attachment invoice rows, preserves full before relation payload and upgrades via `confirm_relation(..., replace_existing=True)`. This is more complex and should not be coupled to OA invoice offset sync extraction.
- `_expand_confirm_link_row_ids_for_existing_context(...)` reads active relations for selected row ids to preserve existing context during confirm-link preview/write. This is confirm-link precondition/context expansion and should be separate from repair sync.
- `_auto_pair_conflicts_with_manual_relation(...)` reads one active relation per row id to block auto-pairing over manual relations. This is auto-pair conflict precondition and should be separate from both repair sync and confirm context expansion.
- Existing static guard already proves repair functions use command boundary for writes; this audit is about remaining read dependencies only.

## Decision

Next boundary:

`workbench-relations:server-oa-invoice-offset-relation-read-port-extraction`

Scope:

- Add or reuse an explicit relation read port for OA invoice offset auto-pair sync precondition reads.
- Move `_sync_oa_invoice_offset_auto_pair_relations(...)` direct `list_active_relations()` call behind that port.
- Preserve relation filtering by `OA_INVOICE_OFFSET_AUTO_MATCH_MODE`, create/cancel behavior, changed case ids, changed scope keys, derived lifecycle event metadata and persistence scheduling.
- Add static guard coverage for this method and run existing OA invoice offset sync tests.

Not in scope:

- Do not change `_repair_active_relations_with_oa_attachment_context(...)`.
- Do not change `_expand_confirm_link_row_ids_for_existing_context(...)`.
- Do not change `_auto_pair_conflicts_with_manual_relation(...)`.
- Do not change relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Legacy Path Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| OA invoice offset auto-pair sync active relation read | next explicit-port candidate | Narrow mode-specific list read with existing tests. |
| OA attachment context repair active relation read | later repair port candidate | More complex before-relation/replace-existing repair path. |
| Confirm-link context expansion relation read | later confirm precondition port candidate | Confirm preview/write context preservation. |
| Auto-pair manual conflict relation read | later auto-pair precondition port candidate | Conflict prevention for automatic relations. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice closes only repair/precondition read audit. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Decision |
| --- | --- | --- |
| Business core unit tests | Not changed in this audit slice | Next implementation should preserve OA invoice offset relation sync behavior. |
| Service-layer tests | Not changed in this audit slice | Next implementation should use focused Workbench API/helper regression tests and static guard. |
| API contract tests | Not changed in this audit slice | No HTTP/API behavior changed. |
| Read model/cache/background job tests | Not changed in this audit slice | No read model, dirty scope or worker behavior changed. |
| Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this analysis-only slice | No runtime behavior changed. |
| Existing feature regression tests | Existing tests identified | `test_oa_invoice_offset_sync_does_not_cancel_relations_outside_current_payload` and `test_oa_invoice_offset_sync_only_uses_attachment_source_link_not_case_id` cover next boundary. |

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only repair/precondition relation read audit. It does not remove direct repair/precondition reads, close `workbench_relation`, validate production PostgreSQL/worker evidence, or unblock Go/Fiber/Go Worker admission.

## Next Boundary

`workbench-relations:server-oa-invoice-offset-relation-read-port-extraction`
