---
phase: 27-read-model-fan-out
plan: "04"
subsystem: invoice-family-access-convergence
tags: [pending-invoice, input-invoice-usage, oa-pending-payment, output-invoice-collection, invoice-lifecycle, drawer, zero-fanout]

requires:
  - phase: 27-03
    provides: canonical-only ordinary writes, current-page GET reconciliation and hidden-page I/O suppression
provides:
  - Canonical-only ordinary invoice-family commands and writable Drawers with zero downstream read-model jobs
  - Access-time exact-scope convergence for pending, input usage, OA pending and output collection pages
  - Bounded, manifest-declared and acyclic invoice-lifecycle dependency convergence
  - Direction-specific pending-invoice rule versions and OA authoritative-snapshot isolation
affects: [27-05, 27-06, 27-07]

tech-stack:
  added: []
  patterns: [canonical-only invoice command, visible-page normal-GET reconcile, declared exact dependency fan-in]

key-files:
  created:
    - .planning/phases/27-read-model-fan-out/27-04-SUMMARY.md
  modified:
    - backend/src/fin_ops_platform/services/pending_invoice_service.py
    - backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py
    - backend/src/fin_ops_platform/services/oa_pending_payment_command_service.py
    - backend/src/fin_ops_platform/services/output_invoice_collection_lifecycle_service.py
    - backend/src/fin_ops_platform/services/output_invoice_collection_receipt_service.py
    - backend/src/fin_ops_platform/services/invoice_lifecycle_read_facade.py
    - backend/src/fin_ops_platform/services/read_model_manifest.py
    - backend/src/fin_ops_platform/services/runtime_worker.py
    - web/src/pages/PendingInvoicesPage.tsx
    - web/src/pages/InputInvoiceUsagePage.tsx
    - web/src/pages/OaPendingPaymentsPage.tsx
    - web/src/pages/OutputInvoiceCollectionsPage.tsx
    - docs/architecture/module-boundaries/read-model-contracts.md

key-decisions:
  - "Rules, relation attachment/reversal, status, reminder, red-relation and receipt commands commit only owner facts/version/audit; affected scopes are informational and freshness/barrier target arrays are empty."
  - "The active page reloads through its normal query owner after a successful command; a hidden or unvisited page performs no I/O until its own access."
  - "OA authoritative integration snapshots retain their explicit exact-month durable refresh contract; incremental page writeback does not inherit that snapshot fan-out."
  - "InvoiceLifecycleReadFacade submits all non-fresh manifest-declared exact-month dependencies before lifecycle; the worker rejects graph-external dependency errors."

patterns-established:
  - "Writable Drawer I/O ends at the owning command API; Drawer code never coordinates cross-page rebuilds."
  - "Invoice-family access I/O is GET -> freshness/source-version proof -> exact gateway enqueue -> fresh payload."
  - "Lifecycle dependency work is bounded by one acyclic manifest graph and concrete month scopes, never a write-time global all fallback."

requirements-completed: []
requirements-advanced: [RMF-02, RMF-03, RMF-04, RMF-05, RMF-06, RMF-08]

duration: 44min
completed: 2026-07-23
---

# Phase 27 Plan 04: Invoice-Family Access Convergence Summary

**Pending invoices, input usage, OA pending payments and output collections now stop ordinary writes at their canonical owner; the accessed page alone performs exact freshness convergence.**

## Performance

- **Duration:** 44 min
- **Completed:** 2026-07-23T05:09:00+08:00
- **Final affected backend gate:** 725 passed / 7 environment-gated skipped / 280 subtests passed
- **Lifecycle dependency focused gate:** 65 passed / 229 subtests passed
- **Affected frontend:** 8 suites / 111 tests passed
- **Affected Chromium:** 35 scenarios passed
- **Production build:** passed
- **Production latency:** intentionally not claimed; exact deployed fixture p50/p95/p99 and every-page/every-operation validation remain Phase 27-07 gates

## Accomplishments

- Removed pending-invoice rule lifecycle callbacks, relation/status write finalizers and forced refreshing responses. Expense and income rules now carry independent expected versions, while attachment and income-status commands return exact hints with zero downstream jobs.
- Removed payment-rule save callbacks and OA reverse statistics/read-model invalidators. Draft, submit, status and clear operations retain owner persistence, audit, idempotency and permission boundaries.
- Removed OA pending page-command refresh callbacks. Paid writeback and bank linking update owner facts/version/audit and reload only the current visible page. The authoritative OA integration snapshot remains a separately classified explicit integration operation.
- Removed output collection status/reminder/red-relation/receipt queue dependencies. Receipt create, void, reissue and numbering settings retain validation, numbering, audit and idempotency without rebuilding list pages during the command.
- Converted all four React pages from ordinary mutation operation barriers to current-page normal GET reconciliation. Existing access-time non-fresh barriers remain only for genuine `202` query convergence; hidden pages do not refetch.
- Declared the invoice-lifecycle read graph in the existing manifest, proved it complete and acyclic, and reused `InvoiceLifecycleReadFacade` to enqueue all non-fresh exact-month dependencies before lifecycle. The existing runtime worker now rejects lifecycle dependency names outside the declared graph.
- Updated module boundaries, read-model contracts, runtime governance, coverage matrix, UI feedback and API expectations. No new worker, table, queue, cache, transport or compatibility branch was introduced.

## Writable Drawer Coverage

- Pending rules and attach-existing invoice Drawers: success, failure recovery, conflict and zero write-time barrier.
- Input payment-rule and OA reverse Drawers: save/create/submit behavior, permissions, current-page reload and zero downstream callback.
- OA relation/bank linking Drawers: link/writeback success, rejected mutation recovery and current-page reload.
- Output status, reminder, red relation, receipt create/history/void/reissue and receipt-settings Drawers: owner command, retry/recovery, permission and zero operation-barrier coverage.
- Read-only details and exports retain strict non-fresh behavior and never treat refreshing dependencies as empty/fresh.

## Verification Evidence

- Invoice-family, lifecycle, runtime worker, manifest and architecture backend set — **725 passed / 7 skipped / 280 subtests**, 0 failed.
- Lifecycle facade/refresh/projection/runtime/manifest focused set — **65 passed / 229 subtests**, 0 failed.
- Eight affected frontend suites — **111 passed**, 0 failed.
- Affected Chromium business flows — **35 passed**, 0 failed.
- `npm run build` — passed; only pre-existing CSS minification/chunk-size warnings remained.
- `bash scripts/verify.sh lint` — passed.
- `bash scripts/verify.sh docs` — passed.
- `git diff --check` — passed.

## Seven-Category Test Assessment

1. **Business core:** direction-specific rule versions, attachment conflicts, OA reverse state transitions, paid/link semantics, collection status/reminders, red relations and receipt numbering/lifecycle are covered.
2. **Service layer:** persistence, audit/idempotency, owner-fact isolation, zero ordinary-write queue I/O, authoritative snapshot separation and lifecycle dependency ordering are covered.
3. **API contract:** success/error/version/permission payloads retain business receipts and informational scopes while ordinary freshness/barrier targets are empty; strict non-fresh exports remain asserted.
4. **Read model/cache/background job:** access mismatch enqueue, stale/refreshing states, current-source CAS, declared dependency fan-in, active/fresh dedupe, graph-external rejection and no live fallback are covered.
5. **Frontend interaction:** loading/empty/error/refreshing, current-page reload, hidden-page suppression, every writable Drawer family, form recovery, permission rendering and zero ordinary operation-barrier calls are covered.
6. **End-to-end business flow:** pending rule/attach/income status, input payment rules/OA reverse, OA paid/link and output status/reminder/red-relation/receipt flows converge through current-page access.
7. **Existing regression:** affected backend modules, public DTOs, runtime worker behavior, page/API suites, build and Chromium flows protect unrelated pages and existing strict export/detail contracts.

## Grill-me / Ponytail Review

- No new coordinator was added. The existing lifecycle query owner, manifest, refresh gateway, durable queue and runtime worker are reused.
- Dependency fan-in is five declared read models with exact month mapping; pending is limited to two direction scopes. Unknown and dependency `all` scopes do not expand.
- Ordinary write paths delete callbacks and queue dependencies instead of keeping compatibility fallbacks.
- UI writes call one owner API and then one current-page reload; hidden consumers retain zero I/O.
- Command, query, repository, worker and DTO responsibilities remain directional and separately tested.

## Deviations from Plan

- Final review found that the existing worker could discover lifecycle dependencies one at a time from exceptions, with a defer between discoveries. The minimal production fix was to submit all declared non-fresh exact dependencies in the existing lifecycle facade and bound the worker fallback by the manifest; no second orchestrator was created.
- `server.py` still contains the pre-existing derived-data lifecycle entry used by import/settings/explicit repair paths. All Phase 27-04 ordinary invoice command callers were removed. The remaining import/settings ownership and deletion decision belongs to Plan 27-05 and the mechanical old-code gate in 27-06.
- Real PostgreSQL/RabbitMQ/Redis/systemd latency was not inferred from deterministic tests. Production SLO remains unproven until the exact release is deployed and measured in 27-07.

## Next Phase Readiness

- Plan 27-05 can remove import/search/settings ordinary fan-out and add the minimal 17-page activation contract without changing the invoice command boundary.
- Plan 27-06 must prove zero unmapped old callbacks/fan-out symbols and run full-repository regression.
- No production deployment, production database change or backup operation occurred in this plan.

---
*Phase: 27-read-model-fan-out*
*Completed: 2026-07-23*
