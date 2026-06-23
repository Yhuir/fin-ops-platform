# Workbench Relations WorkbenchWriteFacade Pair Service Boundary Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:workbench-write-facade-pair-service-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit every `WorkbenchWriteFacade._pair_relation_service` call site after the no-OA extractions, classify each remaining direct pair relation dependency, and select the next narrow implementation boundary.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-no-oa-local-implementation-closure-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for Workbench relation read/command facade boundaries.
- AST enumeration of `WorkbenchWriteFacade._pair_relation_service` call sites.

## Call-Site Inventory

| Method | Pair service usage | Classification | Notes |
| --- | --- | --- | --- |
| `__init__` | stores `_pair_relation_service` | broad dependency | Should be replaced by explicit ports over multiple slices. |
| `preview_confirm_link(...)` | `active_relations_for_row_ids(...)` | read/preflight | Candidate for relation read/snapshot port. |
| `_already_active_relation_preview(...)` | `preview_withdraw_for_row_ids(...)` | read/preflight compat | Candidate for relation read/snapshot port; command preview path is preferred when available. |
| `confirm_link(...)` | `active_relations_for_row_ids(...)` | read/preflight | Needed for history before-relations and existing-case expansion. |
| `confirm_link(...)` | `snapshot()` | snapshot/rollback | Used before command-service update for rollback. |
| `cancel_link(...)` | `get_active_relation_by_row_id(...)` | read/preflight | Used before command-service cancellation and stale conflict check. |
| `cancel_link(...)` | `snapshot()` | snapshot/rollback | Used before command-service cancellation for rollback. |
| `_cancel_link_with_uow(...)` | `snapshot()` | snapshot/rollback | Used before UoW cancellation for rollback. |
| `_ignore_row_stale_conflict(...)` | `get_active_relation_by_row_id(...)` | read/preflight | Should move behind read port. |
| `withdraw_link(...)` | `snapshot()` | snapshot/rollback | Used before withdraw flow rollback. |
| `_withdraw_link_with_uow(...)` | `snapshot()` | snapshot/rollback | Used before UoW withdraw flow rollback. |
| `confirm_cash_pass_through(...)` | `update_special_metadata_for_row_ids(...)` | direct special metadata mutation | Needs a separate command-service/port boundary; not safe to fold into read/snapshot extraction. |
| `confirm_cash_ticket_purchase(...)` | `update_special_metadata_for_row_ids(...)` | direct special metadata mutation | Needs a separate command-service/port boundary. |
| `cancel_cash_special(...)` | `clear_special_metadata_for_row_ids(...)` | direct special metadata mutation | Needs a separate command-service/port boundary. |
| `confirm_personal_advance_repayment(...)` | `active_relations_for_row_ids(...)` | read/preflight | Relation creation already uses command service. |
| `confirm_personal_advance_repayment(...)` | `snapshot()` | snapshot/rollback | Used for rollback. |
| `_active_relation_for_cash_special(...)` | `active_relations_for_row_ids(...)` | read/preflight for special metadata flow | Can move to read port before mutation boundary. |
| `_apply_exception_payload(...)` | `snapshot()` | snapshot/rollback | Used for exception rollback; exception writes already use application service/command boundary. |

## Findings

WorkbenchWriteFacade is still the largest remaining broad pair relation service holder. Existing guards already prevent direct pair write fallback in core `confirm_link`, `_confirm_link_with_uow`, `cancel_link`, and `_cancel_link_with_uow`; those methods use `WorkbenchRelationCommandService` for canonical relation writes where available and fail fast when unavailable.

The remaining direct usages split into two implementation groups:

1. Read/snapshot/preflight/rollback usage:
   - active relation by row id.
   - active relations for row ids.
   - withdraw preview fallback.
   - pair relation snapshot for rollback.
   - These are numerous and low-risk to move behind a facade-local relation read/snapshot port.

2. Cash special metadata mutation usage:
   - `update_special_metadata_for_row_ids(...)`.
   - `clear_special_metadata_for_row_ids(...)`.
   - These are direct pair relation writes. They need a separate command-service capability or explicit special-metadata mutation port with tests and rollback classification.

Moving all of WorkbenchWriteFacade in one implementation slice would be too broad because it spans confirm/cancel, withdraw, exception apply, cash special flows, idempotency, UoW rollback, read model scheduling and special metadata writes.

## Decision

The next boundary should be:

`workbench-relations:workbench-write-facade-relation-read-snapshot-port-extraction`

Scope:

- Add an explicit WorkbenchWriteFacade relation read/snapshot port.
- Move these pair service reads/snapshots behind the port:
  - `active_relations_for_row_ids(...)`.
  - `get_active_relation_by_row_id(...)`.
  - `preview_withdraw_for_row_ids(...)`.
  - `snapshot()`.
- Inject the port into `WorkbenchWriteFacade` from `Application._workbench_write_facade(...)`.
- Preserve command-service-backed writes.
- Preserve core Workbench confirm/cancel/withdraw/idempotency/UoW behavior.
- Strengthen static guards so WorkbenchWriteFacade no longer directly calls pair service read/snapshot methods outside the new port.

Not in scope for the next slice:

- Do not migrate cash special metadata mutation methods yet.
- Do not remove `pair_relation_service` from WorkbenchWriteFacade entirely if special metadata mutation still needs it; classify it as pending special metadata mutation only.
- Do not change API payloads, dirty scope semantics, read model refresh semantics or Workbench active generation behavior.
- Do not implement Go/Fiber/Go Worker.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This audit classifies WorkbenchWriteFacade pair service surfaces and selects the next implementation boundary. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not changed in this audit slice. |
| Service-layer tests | Not changed in this audit slice. Next implementation must run Workbench write characterization tests. |
| API contract tests | Not applicable. No HTTP/API shape changed. |
| Read model/cache/background job tests | Not applicable. No refresh, dirty scope, cache or worker behavior changed. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this analysis-only slice. |
| Existing feature regression tests | Existing Workbench write characterization and boundary guard tests were inspected as next-slice coverage candidates. |

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only WorkbenchWriteFacade pair service dependency classification. It does not migrate the facade, close `workbench_relation`, resolve cash special metadata mutation, validate production PostgreSQL/worker evidence, or unblock Go admission.
