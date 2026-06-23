# Workbench Relations WorkbenchWriteFacade Cash Special Metadata Boundary Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:workbench-write-facade-cash-special-metadata-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit the remaining WorkbenchWriteFacade cash special metadata direct pair service mutations and select the smallest safe implementation boundary without changing cash special semantics, relation write semantics, dirty scope behavior, read model refresh behavior, or API response shape.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-relation-read-snapshot-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-pair-service-boundary-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for Workbench cash special metadata symbols.
- Text search for `update_special_metadata_for_row_ids`, `clear_special_metadata_for_row_ids`, `confirm_cash_pass_through`, `confirm_cash_ticket_purchase`, `cancel_cash_special`, and `_active_relation_for_cash_special`.

## Current Call Sites

| WorkbenchWriteFacade method | Direct mutation | Current behavior |
| --- | --- | --- |
| `confirm_cash_pass_through(...)` | `_pair_relation_service.update_special_metadata_for_row_ids(...)` | Validates active OA+bank relation, merges `cash_pass_through` metadata, records `update_special_relation` history, schedules pair relation persist and read model refresh. |
| `confirm_cash_ticket_purchase(...)` | `_pair_relation_service.update_special_metadata_for_row_ids(...)` | Validates active OA+bank+invoice relation, validates ticket/cash amount/project requirements, merges `cash_ticket_purchase` metadata, records `update_special_relation` history, schedules pair relation persist and read model refresh. |
| `cancel_cash_special(...)` | `_pair_relation_service.clear_special_metadata_for_row_ids(...)` | Validates active relation identity, clears all special metadata, records `clear_special_relation` history, schedules pair relation persist and read model refresh. |

## Existing Protection

- `_active_relation_for_cash_special(...)` already reads through `WorkbenchWriteRelationReadSnapshotPort`.
- `_cash_special_stale_conflict(...)` protects stale expected relation/version conflicts.
- `tests.test_workbench_write_characterization` covers:
  - duplicate cash special update/clear current behavior.
  - stale cash special current-relation behavior without expected versions.
  - stale expected relation rejection for pass-through, ticket purchase and cancel.
  - scheduling failure propagating after metadata mutation.
- `tests.test_platform_runtime_boundary_guards` now keeps cash special direct mutations visible as the next boundary instead of silently hiding them.

## Command-Service Fit Check

`WorkbenchRelationCommandService.update_relation_metadata_for_case_id(...)` already provides a command boundary for case-id metadata merge with idempotency, freshness precondition, history, changed case ids and repository save behavior.

It is not a drop-in replacement for this slice because:

- Cash special entrypoints currently resolve the active relation by row ids, then apply stale expected-version checks before mutation.
- `confirm_cash_pass_through(...)` and `confirm_cash_ticket_purchase(...)` merge special metadata by row ids and rely on `update_special_relation` history semantics.
- `cancel_cash_special(...)` clears all `special_metadata`; the command service's current update method merges metadata and does not express clear/replace semantics.
- WorkbenchWriteFacade still owns cash-specific validation, metadata construction, response payload and read-model scheduling.
- Switching directly to command service would need a new clear/replace command contract plus regression tests for idempotency, freshness, history operation type, changed case ids and scheduling behavior.

Therefore the next implementation should not force a broad command-service rewrite in one slice.

## Decision

Next boundary:

`workbench-relations:workbench-write-facade-cash-special-metadata-port-extraction`

Scope:

- Add an explicit `WorkbenchWriteRelationSpecialMetadataMutationPort` near `WorkbenchWriteRelationReadSnapshotPort`.
- Move these pair service mutation calls behind that port:
  - `update_special_metadata_for_row_ids(...)`
  - `clear_special_metadata_for_row_ids(...)`
- Inject the port from `Application._workbench_write_facade(...)`.
- Preserve the existing cash special validation, stale conflict checks, metadata payloads, history operation names, response shape, pair relation persist scheduling and read model scheduling.
- Keep the read/snapshot port unchanged.
- Strengthen static guards so `WorkbenchWriteFacade` no longer directly calls pair service special metadata mutation methods.

Not in scope for the next implementation:

- Do not remove the read/snapshot port.
- Do not change cash special API payloads or messages.
- Do not change special metadata merge/clear semantics.
- Do not add Go/Fiber/Go Worker.
- Do not declare `workbench_relation` closed.

Later optional boundary:

- After the explicit mutation port exists and tests prove no behavior change, evaluate whether `WorkbenchRelationCommandService` should grow a native special-metadata update/clear command with explicit replace semantics.

## Legacy Path Classification

| Surface | Classification | Owner | Deletion condition |
| --- | --- | --- | --- |
| Direct pair service special metadata calls inside `WorkbenchWriteFacade` | implementation-pending removal | WorkbenchWriteFacade cash special metadata port extraction | Delete once `WorkbenchWriteRelationSpecialMetadataMutationPort` is injected and static guard proves direct calls are gone. |
| `WorkbenchPairRelationService.update_special_metadata_for_row_ids(...)` | canonical in-memory mutation primitive for now | Workbench relation service | Can be hidden behind command service only after a clear/replace command contract exists. |
| `WorkbenchPairRelationService.clear_special_metadata_for_row_ids(...)` | canonical in-memory mutation primitive for now | Workbench relation service | Can be hidden behind command service only after clear semantics and tests exist. |

Forbidden writes for future compat/port path:

- It must not write dirty scopes, outbox events, read model readiness, cache or App Status directly.
- It must not bypass stale expected-version checks.
- It must not change relation row ownership or relation mode.
- It must not publish Workbench active generation directly.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This audit closes only the cash special metadata boundary classification and selects the next narrow implementation boundary. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not changed in this audit slice | Next implementation must preserve cash amount, ticket amount, project requirement, row type validation and stale conflict behavior. |
| Service-layer tests | Not changed in this audit slice | Next implementation should run Workbench write characterization tests covering cash special update/clear and scheduling failure. |
| API contract tests | Not changed in this audit slice | No HTTP response shape changed. Existing characterization uses API routes for cash special endpoints. |
| Read model/cache/background job tests | Not changed in this audit slice | Next implementation must preserve pair relation persist scheduling and read model refresh scheduling. |
| Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this analysis-only slice | Backend characterization covers the targeted cash special flow. |
| Existing feature regression tests | Existing tests identified | `tests.test_workbench_write_characterization` is the required regression suite for the next implementation. |

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only cash special metadata boundary audit and next-boundary selection. It does not migrate the mutation calls, does not close `workbench_relation`, does not validate production PostgreSQL/worker evidence, and does not unblock Go/Fiber/Go Worker admission.
