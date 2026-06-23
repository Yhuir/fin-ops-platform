# Read Model OA Pending Payment Refresh Freshness Operation Barrier Audit

**Date:** 2026-06-24
**Boundary:** `read-models:oa-pending-payment-refresh-freshness-operation-barrier-audit`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit OA pending payment freshness, force refresh, `all` fan-out/month proof and operation barrier behavior after repository port extraction. If a narrow non-Go gap is found, implement it before any Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/ROADMAP.md`
- `.planning/refactors/README.md`
- `.planning/refactors/modular-io-boundaries/README.md`
- `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-oa-pending-payment-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/oa-pending-payments/README.md`
- `docs/modules/oa-pending-payments/tests.md`
- `docs/modules/oa-pending-payments/implementation-notes.md`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_repository.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `web/src/pages/OaPendingPaymentsPage.tsx`
- `web/src/test/OaPendingPaymentsPage.test.tsx`
- `tests/test_oa_pending_payment_api.py`
- `tests/test_oa_pending_payment_command_service.py`
- `tests/test_invoice_usage_collection_sql_runtime.py`

CodeGraph was used before editing to inspect OA pending payment freshness, refresh, barrier and frontend impact. `codegraph_impact("oaPendingPaymentBarrierTargets")` showed the touched function only feeds `waitForOaPendingPaymentBarrier` and the OA pending payments page.

## Audit Findings

### Fresh Gate

`OaPendingPaymentReadModelService` enforces the expected contract:

- rows derive the query scope from `month` or `all`;
- missing SQL repository, missing payload, stale payload or source-version mismatch returns `read_model_status=refreshing`;
- rows/filter-options/detail do not live scan as fresh in production read-model mode;
- refresh enqueue goes through `ReadModelRefreshGateway`, so scope validation/dedupe is delegated to `ReadModelScopePolicyRegistry`.

### Scope Policy / Force Refresh

`ReadModelScopePolicyRegistry` registers `oa_pending_payment` as month-or-`all`. This matches the current manifest and module docs:

- month scopes are queryable projection shards;
- `all` is accepted as a refresh command/fan-out scope;
- default all queries must prove freshness from actual rows/month scopes and active dirty/outbox state, not from global relation `all`.

### Worker Fan-Out

`InvoiceUsageCollectionReadModelRefreshService` handles `oa_pending_payment.read_model.refresh` as follows:

- checks the runtime event source version before rebuild/fan-out;
- expands non-month scopes such as `all` through `list_oa_pending_payment_scope_shards(...)`;
- prunes orphan scope shards through `prune_oa_pending_payment_scope_shards(...)`;
- enqueues month shards through `ReadModelRefreshGateway`;
- completes the original dirty scope after fan-out.

Existing tests already cover OA all fan-out and source-version staleness behavior.

### Source-Version Proof

Repository/API tests already cover the core OA source-version rules:

- month scope compares base OA pending payment source versions plus corresponding Workbench relation source versions;
- default all scope does not depend on global `workbench_relation:all`;
- default all scope can aggregate actual monthly rows/source versions and ignore stale empty historical scopes;
- Workbench relation source-version lookup is owned by the Workbench relation port, not the OA repository port.

### Operation Barrier Gap Found

The command service correctly returns `readModelRefresh.scopeKeys` containing concrete affected month scopes plus `all`, for example `["2026-05", "all"]`.

Before this slice, `OaPendingPaymentsPage.oaPendingPaymentBarrierTargets(...)` would wait for `oa_pending_payment:all` when the current visible scope was `all` and `all` appeared in the response. That made the frontend prefer the fan-out control scope over the concrete month shard, even when the backend had supplied the exact affected month.

This conflicts with the documented read model rule that fan-out-only `all` must not be treated as the preferred write-after-read freshness proof when concrete month shards are known.

## Implementation

Updated `web/src/pages/OaPendingPaymentsPage.tsx`:

- When the current visible scope is `all` and the mutation response contains one or more concrete non-`all` scope keys, the page now waits for those concrete `oa_pending_payment:<YYYY-MM>` targets.
- If no concrete scope exists, the existing fallback behavior remains: wait for `all`.
- If the current visible scope is a month and that month appears in the response, the page still waits for that visible month.

Updated `web/src/test/OaPendingPaymentsPage.test.tsx`:

- auto-reconcile success now proves `scopeKeys: ["2026-05", "all"]` results in an operation barrier request for `oa_pending_payment:2026-05`;
- link-bank success now proves the same concrete-month target behavior;
- existing rules-save behavior remains unchanged because that callback has no backend `readModelRefresh` response and therefore falls back to the current visible scope.

## Legacy Classification

| Surface | Classification | Reason |
| --- | --- | --- |
| Frontend write-after-read barrier target `oa_pending_payment:all` when concrete month scopes are returned | replaced | Concrete month scope is the real write-after-read target; `all` remains only fallback when no concrete scope is available. |
| Backend command `readModelRefresh.scopeKeys` shape | retained | Existing command/API contract already returns concrete months plus `all`; no API shape change. |
| Rules-save callback without OA backend refresh response | retained fallback | It still waits on the visible scope because no concrete OA affected month is returned by that separate pending-invoice rules path. |

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- `read-models:oa-pending-payment-refresh-freshness-operation-barrier-audit`: `pending` -> `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:oa-pending-payment-local-implementation-closure-audit`
- Go hot-path admissions remain `blocked-by-prerequisite`

Reviewed state files:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/oa-pending-payments/state-machine.md`

Definitions remain unchanged because this slice enforces an existing documented freshness/barrier rule rather than introducing a new state or transition.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no OA payment status, matching, amount, relation or writeback business rule changed.
2. Service-layer tests: not applicable for the implementation change; backend service and repository behavior was audited but not changed.
3. API contract tests: not applicable for implementation; response shape remains unchanged and existing API tests already cover `readModelRefresh.scopeKeys`.
4. Read model/cache/background job tests: applicable as audit evidence; existing tests cover all-scope fan-out, source-version proof and stale-event behavior. No new backend read model behavior changed.
5. Frontend component and interaction tests: applicable; updated `OaPendingPaymentsPage.test.tsx` covers concrete-month operation barrier targets after auto-reconcile and bank-link mutations.
6. End-to-end business-flow integration tests: not run for this narrow frontend target selection change; existing Playwright flows still cover the broader OA pending payment write/read flows.
7. Existing feature regression tests: applicable; updated page tests ensure rows are not reloaded before barrier fresh and rules-save fallback behavior is unchanged.

## Verification

```bash
cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx
```

Final slice verification must additionally run:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only the OA pending payment freshness/operation-barrier audit and concrete-month frontend barrier target slice is closed. `oa_pending_payment` remains `implementation-gap-open` until a local implementation closure audit accounts for any remaining non-Go gaps and records production evidence defer status. Go/Fiber/Go Worker admission remains blocked.
