# Workbench Relations Pending Invoice Unused Pair Service Removal

**Date:** 2026-06-24
**Boundary:** `workbench-relations:pending-invoice-unused-pair-service-removal`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove unused `pair_relation_service` injection from pending invoice query/application services without changing pending invoice relation read/write behavior.

## Changes

- Removed `pair_relation_service` constructor parameter and `_pair_relation_service` field from `PendingInvoiceQueryService`.
- Removed `pair_relation_service` constructor parameter and `_pair_relation_service` field from `PendingInvoiceApplicationService`.
- Removed pending invoice `pair_relation_service=...` wiring from `Application` service construction.
- Updated pending invoice service tests and invoice lifecycle integration tests to stop passing pair services into pending invoice services.
- Strengthened `test_downstream_relation_query_services_do_not_accept_pair_relation_service` so `pending_invoice_service.py` cannot import or accept `WorkbenchPairRelationService`.
- Removed stale pending invoice allowed-context entries from `_ForbiddenRelationReadVisitor`.

## Preserved Behavior

- Pending invoice relation reads still use `relation_facade.get_by_row_ids(...)`.
- Pending invoice relation writes still use `WorkbenchRelationCommandService.confirm_relation(...)`.
- Test relation facades and command repositories may still use `WorkbenchPairRelationService` as a fake backing store, but pending invoice services no longer receive it.
- No pending invoice attach/manual invoice rules, API payloads, dirty scopes, read model refresh semantics, audit, finalizer or production state changed.

## Legacy Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `PendingInvoiceQueryService.pair_relation_service` | removed | Constructor parameter and field removed. |
| `PendingInvoiceApplicationService.pair_relation_service` | removed | Constructor parameter and field removed. |
| `Application` pending invoice pair service wiring | removed | `PendingInvoiceQueryService` and `PendingInvoiceApplicationService` construction no longer passes `_workbench_pair_relation_service`. |
| `tests/test_pending_invoice_service.py` fake pair services | test fixture only | Retained only as backing store for `LiveWorkbenchRelationFacade` and `WorkbenchRelationCommandService` repository fixtures, not injected into pending invoice services. |
| `PendingInvoiceQueryService.relation_facade` | canonical read dependency | Kept. |
| `PendingInvoiceApplicationService.relation_facade` | canonical read dependency | Kept. |
| `PendingInvoiceApplicationService.relation_command_service` | canonical write dependency | Kept. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/pending-invoices/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This implementation removes one unused legacy injection path. `workbench_relation` remains `implementation-gap-open`; no-OA, ETC and WorkbenchWriteFacade relation dependencies still need classification.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. Business rules did not change. |
| Service-layer tests | Covered by pending invoice query/application service tests. |
| API contract tests | Not applicable. No HTTP/API shape changed. |
| Read model/cache/background job tests | Not applicable. No refresh, dirty scope, cache or worker behavior changed. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this dependency removal. |
| Existing feature regression tests | Covered by pending invoice service tests, invoice lifecycle integration test, boundary guard and app check. |

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service.PendingInvoiceQueryServiceTests tests.test_pending_invoice_service.PendingInvoiceApplicationServiceTests tests.test_invoice_lifecycle_page_integration.InvoiceLifecyclePageIntegrationTests.test_pending_invoice_rows_delegate_acquisition_status_to_lifecycle_policy -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_downstream_relation_query_services_do_not_accept_pair_relation_service -v
```

Pending before commit:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only pending invoice unused pair service removal. It does not close `workbench_relation`, validate production evidence, migrate no-OA/ETC/WorkbenchWriteFacade relation dependencies, or unblock Go admission.
