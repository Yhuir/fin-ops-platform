---
phase: 27-read-model-fan-out
plan: "03"
subsystem: relation-heavy-access-convergence
tags: [workbench, relation, turnover, bank-flow, batch-accounting, read-model, zero-fanout]

requires:
  - phase: 27-02
    provides: bank/cost vertical access-time freshness pattern and ordinary-write zero-fanout gate
provides:
  - Canonical-only ordinary relation writes with zero read-model dirty/outbox targets
  - Access-time Workbench, workbench-relation, bank-flow, no-OA, batch-accounting and turnover convergence
  - Workbench publish isolation from Cost and a two-stage Workbench-to-Cost access dependency gate
  - Current-page normal-GET reconciliation with hidden-page I/O suppression
affects: [27-04, 27-05, 27-06, 27-07]

tech-stack:
  added: []
  patterns: [canonical-only relation commit, access-time exact-scope freshness, two-stage dependency convergence]

key-files:
  created:
    - .planning/phases/27-read-model-fan-out/27-03-SUMMARY.md
  modified:
    - backend/src/fin_ops_platform/services/workbench_uow.py
    - backend/src/fin_ops_platform/services/workbench_write_facade.py
    - backend/src/fin_ops_platform/services/workbench_relation_read_facade.py
    - backend/src/fin_ops_platform/services/workbench_read_model_refresh.py
    - backend/src/fin_ops_platform/services/cost_statistics_query_service.py
    - backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py
    - backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py
    - backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py
    - web/src/pages/ReconciliationWorkbenchPage.tsx
    - web/src/pages/BankFlowRuleBatchPage.tsx
    - web/src/pages/BatchAccountingPage.tsx
    - web/src/pages/TurnoverLedgerPage.tsx
    - web/src/pages/CostStatisticsPage.tsx
    - docs/architecture/module-boundaries/read-model-contracts.md

key-decisions:
  - "Ordinary relation, bank-flow, no-OA, batch-accounting and turnover commands persist canonical facts/history/idempotency/audit only; affected scopes are informational and both freshness target arrays are empty."
  - "The current visible page reconciles through its normal GET; hidden pages perform no page I/O until visible, and another visible window independently GETs after the existing lightweight notification."
  - "Workbench active-generation atomic publish remains, but a successful Workbench shard publish never enqueues Cost or another consumer."
  - "Cost access is dependency ordered: stale Workbench enqueues only the exact Workbench month; only a later GET with fresh Workbench may enqueue the exact Cost scope."

patterns-established:
  - "Write I/O boundary: canonical database transaction only, with zero page projection queue amplification."
  - "Read I/O boundary: expected canonical version versus published proof, then one normalized/deduped exact-scope enqueue on mismatch."
  - "Frontend boundary: command latency is not coupled to read-model rebuild latency; visible-page freshness is a normal query state."

requirements-completed: []
requirements-advanced: [RMF-02, RMF-03, RMF-04, RMF-05, RMF-06, RMF-08]

duration: 119min
completed: 2026-07-23
---

# Phase 27 Plan 03: Relation-Heavy Access Convergence Summary

**Workbench, bank-flow/no-OA, batch-accounting and Turnover ordinary writes now stop at the canonical transaction; only an accessed consumer performs an exact freshness check and rebuild request.**

## Performance

- **Duration:** 119 min
- **Completed:** 2026-07-23T04:24:02+08:00
- **Focused backend topology/regression:** Workbench pattern 730 passed / 1 skipped; Turnover pattern 361 passed / 1 skipped; bank-flow 60 passed; no-OA 139 passed; batch 47 passed / 1 skipped; Cost 133 passed / 7 skipped
- **Final combined affected backend gate:** 639 passed, 76 subtests passed, 0 failed
- **Affected frontend:** 10 suites / 224 tests passed; production build passed
- **Affected Chromium:** 38 scenarios passed
- **Production latency:** intentionally not claimed; exact deployed fixture p50/p95/p99 and every-page/every-operation validation remain Phase 27-07 gates

## Accomplishments

- Deleted Workbench UoW/facade/repository write-time refresh planners, downstream discovery and hidden relation scope expansion from the ordinary relation chain. Confirm, withdraw, split, exception, ignore/unignore and cash actions retain relation semantics, version preconditions, idempotency, history and audit.
- Added canonical source-version detection to Workbench and workbench-relation access paths while preserving active-generation atomic publication.
- Converted bank-flow rule saves, submit/withdraw/reset, legacy no-OA mutations and batch-accounting submit/withdraw to informational affected scopes plus empty freshness/barrier targets. No fixed `all` fallback or duplicate lifecycle call remains in these ordinary paths.
- Removed Turnover UoW/facade/adapters downstream page fan-out. Closure, relation, tag and extra writes retain Phase 26 selected-member, frozen requirement and repair-safety contracts.
- Removed Workbench publish-to-Cost fan-out. `CostStatisticsQueryService` now fail-closes on a stale Workbench dependency, enqueues only that exact Workbench month, and waits for a later normal GET before it can enqueue Cost.
- Migrated affected React pages from operation barriers to current-page normal GET convergence. The existing lightweight domain notification is only a refetch hint; hidden pages suppress I/O until activation.
- Updated API contracts, state machines, E2E specs/coverage, seven-category test matrices, runtime governance, module boundaries and the Phase 27 coverage matrix so current documentation cannot reintroduce the old write-time topology.

## Verification Evidence

- Cost + Workbench SQL focused set — 242 passed.
- Platform/runtime architecture guards — 219 passed.
- Workbench pattern — 730 passed / 1 environment-gated skipped.
- Turnover pattern — 361 passed / 1 environment-gated skipped.
- Bank-flow pattern — 60 passed.
- Legacy no-OA pattern — 139 passed.
- Batch-accounting pattern — 47 passed / 1 environment-gated skipped.
- Cost pattern — 133 passed / 7 environment-gated skipped.
- Final combined affected backend command — **639 passed + 76 subtests**, 0 failed.
- Ten affected frontend suites — **224 passed**.
- Production frontend build — passed; only pre-existing CSS selector and chunk-size warnings remained.
- Affected Chromium business flows — **38 passed**.
- `bash scripts/verify.sh lint` — passed.
- `bash scripts/verify.sh docs` — passed.
- `git diff --check` — passed.

## Seven-Category Test Assessment

1. **Business core:** existing relation membership/mode/withdrawal, Turnover zero-difference/frozen-requirement, batch ownership, rule version and invalid-input contracts remain covered.
2. **Service layer:** canonical-only UoWs, rollback/idempotency, zero queue I/O, Workbench source-version proof, Cost dependency ordering and no-OA/bank-flow isolation are covered.
3. **API contract:** ordinary mutations retain business receipts and informational scopes while returning empty freshness/barrier targets; errors, versions and permissions remain asserted.
4. **Read model/cache/background job:** access miss/stale enqueue, normalize/dedupe, active-generation publish, Workbench publish isolation, two-stage Cost dependency and zero ordinary-write dirty/outbox are covered.
5. **Frontend interaction:** loading/refreshing/error, current-page normal GET, hidden-page suppression, another visible window refetch, Drawer saves, command feedback and zero ordinary operation-barrier calls are covered.
6. **End-to-end business flow:** Workbench confirm/withdraw, bank-flow submit/reset, batch submit/withdraw and Turnover confirm/withdraw recover their current page and independently access Cost without a write-time fan-out.
7. **Existing regression:** affected backend patterns, frontend suites, production build, Chromium flows and architecture guards protect unrelated pages, Phase 26 semantics, legacy no-OA isolation and public DTOs.

## Grill-me / Ponytail Review

- No coordinator, dependency graph, new worker, queue, table, cache, transport, polling service or compatibility path was added.
- Existing query facades, source-version providers, refresh gateway, PostgreSQL durable queue and workers remain the only read-model boundaries.
- Workbench active generation is preserved as the sole special publication model; it is not copied into ordinary read models.
- Old write planners, downstream discovery, hidden enqueue and frontend barrier calls were deleted instead of wrapped.
- Cost dependency ordering uses two existing providers and one existing enqueuer; it does not introduce a general-purpose orchestration layer.
- API, module and frontend I/O remain directional: command -> canonical owner; GET -> query owner -> freshness gateway; worker -> owned projection.

## Deviations from Plan

- Focused testing found a false-fresh hole in Cost: removing Workbench publish fan-out meant Cost could compare against an old Workbench generation and appear fresh. The minimal fix was an explicit two-stage dependency check in the existing Cost query service, not a new coordinator.
- The existing `cost_statistics_relation_delta` worker/repository implementation is now unreachable from ordinary writes but still exists. It is not a fallback; Phase 27-06 will either delete it or classify a concrete explicit-operations owner under the mechanical old-code gate.
- A route-unit fake and several current long-term documents still encoded old barrier/fan-out responses although runtime tests were green. They were corrected; historical dated implementation notes remain as traceability and are explicitly superseded.
- Real PostgreSQL/RabbitMQ/Redis/systemd performance was not inferred from deterministic tests. Production SLO remains unproven until the exact release is deployed and tested in 27-07.

## Next Phase Readiness

- Plan 27-04 can migrate pending/input/OA/output invoice-family writes and all affected right-side Drawers using the same canonical-write/current-page-GET contract.
- Plan 27-06 must remove legacy delta/SLO tooling expectations and prove zero unmapped old fan-out symbols.
- No production deployment, production database change or backup operation occurred in this plan.

---
*Phase: 27-read-model-fan-out*
*Completed: 2026-07-23*
