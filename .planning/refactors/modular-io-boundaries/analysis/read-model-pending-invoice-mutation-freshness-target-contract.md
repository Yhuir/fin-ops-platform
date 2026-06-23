# Read Model Pending Invoice Mutation Freshness Target Contract

**Date:** 2026-06-24
**Boundary:** `read-models:pending-invoice-mutation-freshness-target-contract`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit pending invoice mutation freshness behavior and close the narrow gap where income-status mutations refreshed rows without waiting for the pending invoice read model barrier.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-scope-policy-filter-allowlist.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-refresh-freshness-operation-barrier-audit.md`
- `docs/modules/read-models/README.md`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/pending-invoices/tests.md`
- `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `web/src/pages/PendingInvoicesPage.tsx`
- `web/src/features/operationBarrier/api.ts`
- `web/src/features/pendingInvoices/api.ts`
- `web/src/test/PendingInvoicesPage.test.tsx`
- `web/src/test/PendingInvoicesRulesSaveTimeout.test.tsx`

## Findings

Rules update and attach-existing confirm already wait for operation barrier targets in `PendingInvoicesPage`:

- rules update waits for `pending_invoice:<direction>:<current-filter>`;
- attach-existing waits for `workbench_relation:<month>` and `pending_invoice:<direction>:<filter>:<month>`.

Income-status batch update returned `affectedMonths` but only updated optimistic rows and triggered a refetch token. It did not wait for a `pending_invoice` operation barrier target before reloading rows.

## Implementation

Changed `PendingInvoicesPage.handleMarkSelectedIncomeStatus(...)`:

- after `savePendingInvoiceIncomeStatuses(...)`, it now uses the existing global operation overlay;
- it waits for `pending_invoice` freshness targets derived from the current income filter and response `affectedMonths`;
- it tolerates `OperationBarrierTimeoutError` the same way rules update and attach-existing do, then refetches rows;
- it keeps existing validation/retry behavior for failed income-status writes.

Backend API shape was not changed.

## Scope Decision

This slice intentionally avoids adding `freshness_targets` to backend pending invoice mutation responses. Existing frontend contracts already compute correct targets from stable response fields:

- `affectedMonths`
- current page direction/filter state

Changing backend response shape across rules, attach-existing and income-status operations is broader than needed to close the observed gap. If a future shared response target contract is desired, it should be a separate cross-page API contract slice.

## Legacy Classification

| Surface | Classification | Reason |
| --- | --- | --- |
| Rules update barrier | retained valid path | Already waits for pending invoice barrier target. |
| Attach-existing barrier | retained valid path | Already waits for workbench relation and pending invoice barrier targets. |
| Income-status refresh-token-only path | replaced | Now waits for pending invoice barrier and actively refetches rows. |
| Backend response without `freshness_targets` | retained current contract | `affectedMonths` remains the stable API field consumed by the page. |

## State Machine Impact

No global state definition changed.

Queue transition:

- `read-models:pending-invoice-mutation-freshness-target-contract`: `pending` -> `implementation-closed`
- Next queue item: `read-models:pending-invoice-local-implementation-closure-audit`
- `pending_invoice` remains `implementation-gap-open`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no pending invoice status business rules changed.
2. Service-layer tests: not applicable; backend services were not changed.
3. API contract tests: existing API contract remains unchanged; no backend response shape changed.
4. Read model/cache/background job tests: applicable through frontend operation barrier target coverage.
5. Frontend component and interaction tests: applicable; `PendingInvoicesPage.test.tsx` now asserts income batch status waits for `pending_invoice:income:all:YYYY-MM`.
6. End-to-end business-flow integration tests: not run in this slice; component-level interaction test covers the changed behavior.
7. Existing feature regression tests: applicable; existing rules save timeout and PendingInvoicesPage tests were rerun.

## Verification

```bash
cd web && npm test -- --run src/test/PendingInvoicesPage.test.tsx src/test/PendingInvoicesRulesSaveTimeout.test.tsx
```

Final slice verification must additionally run:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only the mutation freshness target contract slice is closed. `pending_invoice` still needs a local implementation closure audit before any Go admission can be considered.
