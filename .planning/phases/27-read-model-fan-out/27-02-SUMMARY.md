---
phase: 27-read-model-fan-out
plan: "02"
subsystem: bank-details-cost-statistics
tags: [read-model, access-time-freshness, zero-fanout, cache-gate, drawers]

requires:
  - phase: 27-01
    provides: complete page/API/Drawer/read-model/direct-call coverage contract
provides:
  - Current canonical freshness proof before Redis payload reuse
  - Zero write-time downstream refresh for ordinary bank category and auto-tag rule mutations
  - Explicit bounded month-shard reapply contract for bank auto-tag rules
  - Query-time cost tag eligibility save with no read-model barrier
  - Visible-page reconcile and hidden-page I/O suppression for the first vertical slice
affects: [27-03, 27-04, 27-05, 27-06, 27-07]

tech-stack:
  added: []
  patterns: [canonical-signature freshness proof, access-time exact-scope reconcile, explicit-batch exception]

key-files:
  created: []
  modified:
    - backend/src/fin_ops_platform/services/read_model_query_gateway.py
    - backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
    - backend/src/fin_ops_platform/services/bank_details_application_service.py
    - backend/src/fin_ops_platform/services/bank_transaction_category_mutation_writer.py
    - backend/src/fin_ops_platform/services/cost_statistics_query_service.py
    - web/src/pages/BankDetailsPage.tsx
    - web/src/pages/CostStatisticsPage.tsx
    - docs/modules/bank-details/boundary-io.md
    - docs/modules/cost-statistics/boundary-io.md

key-decisions:
  - "Redis is payload-only: each request proves the current owner metadata before a cache hit can be accepted."
  - "Ordinary bank category/rule writes return exact affected scopes but no freshness target or operation barrier; only explicit reapply enqueues bounded bank_detail month shards."
  - "Cost tag selection is a query/export rule and therefore saves settings/audit only, then invalidates the current browser query nonce."
  - "A canonical bank category/confirmation signature closes direct PostgreSQL drift without restoring write-time downstream fan-out."

patterns-established:
  - "Write path: canonical fact/settings CAS plus audit, with no unrelated read-model queue I/O."
  - "Read path: owner proof -> optional fresh Redis payload -> bounded SQL payload -> exact-scope refresh when stale."
  - "Frontend: visible current page reconciles after save; inactive pages perform no page I/O until activation."

requirements-completed: []
requirements-advanced: [RMF-02, RMF-03, RMF-04, RMF-05, RMF-08]

duration: 61min
completed: 2026-07-23
---

# Phase 27 Plan 02: Bank/Cost Access-Time Freshness Summary

**The first production-runtime slice now performs fast canonical writes without ordinary cross-page fan-out, while bank and cost reads prove current ownership before accepting cached or projected data.**

## Performance

- **Duration:** 61 min
- **Completed:** 2026-07-23T02:25:00+08:00
- **Backend full regression:** 4359 tests passed, 51 environment-gated skipped
- **Frontend full regression:** 75 files / 886 tests passed; production build passed
- **Focused Chromium:** 24/24 bank, cost and permission scenarios passed
- **Production/reference distribution:** intentionally not claimed here; p50/p95/p99 and real access-to-fresh are release gates in 27-06 and 27-07

## Accomplishments

- Extended the existing `ReadModelQueryGateway` with a narrow owner-proof loader. Redis is consulted only after current canonical/schema/dirty proof passes; stale/missing targets enqueue through the existing normalized refresh gateway.
- Raised bank-detail schema to v11 and persisted a stable category/confirmation source signature. The query repository recomputes it with one set-based PostgreSQL query, so direct canonical category drift cannot remain falsely fresh.
- Removed ordinary bank auto-tag save, category confirm/revoke/assign/clear downstream lifecycle, Turnover `all`, search/cache callbacks and operation-barrier targets. No `affected_months or ["all"]` fallback remains on these writes.
- Kept “重新应用规则” as the explicit batch exception: concrete existing month shards are enqueued in a bounded batch, returned as formal barrier targets and waited by the current page.
- Converted cost tag-rule save to its real classification: settings CAS/version/audit plus current query reload. It no longer fabricates a cost read-model rebuild or presents “保存并同步”.
- Updated BankDetails/CostStatistics visible/hidden lifecycle tests, API DTOs, permission E2E and boundary documentation.
- Closed full-suite regressions without compatibility fallbacks: historical no-OA relations now persist explicit frozen `requires_oa=false` / `requires_invoice=false`; the bank-flow list route maps only its known missing read repository boundary to sanitized 503; stale migration/schema fixtures now consume the current contract; an API test no longer calls the removed broad state-store persistence path.

## Verification Evidence

- `bash scripts/verify.sh lint` — passed.
- `bash scripts/verify.sh backend` — **4359 passed / 51 skipped / 0 failed** in 73.381s.
- `bash scripts/verify.sh frontend` — **75 test files / 886 tests passed**, production build succeeded; only existing HeroUI empty-`:is()` and large-chunk warnings remained.
- `npx playwright test e2e/bank-details-auto-tag-rules-flow.spec.ts e2e/bank-details-category-flow.spec.ts e2e/cost-statistics-flow.spec.ts e2e/permissions-role-matrix.spec.ts` — **24 passed**.
- `bash scripts/verify.sh docs` — passed.
- `git diff --check` — passed.

## Seven-Category Test Assessment

1. **Business core:** bank category/rule CAS, no-OA frozen requirement and invalid/concurrent contracts remain covered by the full backend suite.
2. **Service layer:** query gateway, canonical category writer, settings, audit, exact-scope source proof, zero-enqueue and explicit-reapply paths are covered.
3. **API contract:** ordinary save response removed barriers, explicit reapply retains them, known bank-flow read unavailability returns sanitized 503, and existing response shapes remain regression-tested.
4. **Read model/cache/background job:** current owner proof before Redis, stale-cache bypass, category-signature drift, exact enqueue, queue-zero ordinary writes and bounded reapply are covered.
5. **Frontend interaction:** loading/fresh/refreshing behavior, Drawer save/reapply, visible reload, hidden-page suppression, permission-disabled controls and absence of ordinary operation-barrier calls are covered.
6. **End-to-end business flow:** Chromium covers ordinary rule save -> visible-page reload, explicit reapply -> barrier -> reload, category mutations and cost page behavior.
7. **Existing regression:** full backend/frontend/build plus focused permission/browser flows protect unrelated pages, historical no-OA grouping, imports, pending invoice lifecycle and manifest/migration contracts.

## Grill-me / Ponytail Review

- No coordinator, event bus, dependency graph, per-page SSE, cache tier, worker or service layer was added.
- Existing query gateway, refresh gateway, durable PostgreSQL queue, projection repository and page activation context remain the only runtime boundaries.
- Ordinary writes return exact informational scopes but own zero downstream page jobs; explicit full-history work remains visibly separate.
- Old constructor callbacks and frontend barrier fallback logic were deleted rather than retained behind compatibility branches.
- The signature query is set-based and month-scoped; no per-row job or Python full-table scan was introduced.
- Real SLO compliance is not inferred from unit/E2E wall time. It remains blocked from completion until 27-06 reference-data distributions and 27-07 production evidence pass.

## Deviations from Plan

- Focused E2E found the old ordinary-save barrier expectation still present. The test and deterministic mock were migrated to zero barrier for ordinary save while preserving the explicit reapply barrier.
- Full backend discovery exposed five adjacent stale-contract fixtures and one historical no-OA metadata gap. They were corrected at their owning boundary; no assertion was relaxed and no fallback was added.
- Production performance was not run in this plan because the phase contract reserves every-page/every-operation distribution and production fixture execution for 27-06/27-07. This plan records deterministic topology and browser latency evidence only.

## Next Phase Readiness

- Plan 27-03 can apply the same deletion gate to Workbench, bank-flow/no-OA, batch-accounting and Turnover relation commands.
- Phase 26 correctness remains frozen: requirement metadata is explicit, Workbench active-generation semantics are unchanged, and no production deployment has occurred yet.
- RMF-02/03/04/05/08 stay phase-level pending until all vertical slices and measured release gates pass.

---
*Phase: 27-read-model-fan-out*
*Completed: 2026-07-23*
