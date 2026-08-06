---
phase: 40-performance-contract-hot-path-closure
fixed_at: 2026-08-06T11:07:58Z
review_path: .planning/phases/40-performance-contract-hot-path-closure/40-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 8
skipped: 1
status: partial
---

# Phase 40: Code Review Fix Report

**Fixed at:** 2026-08-06T11:07:58Z
**Source review:** `.planning/phases/40-performance-contract-hot-path-closure/40-REVIEW.md`
**Iteration:** 1

**Summary:**

- Findings in scope: 9
- Fixed: 8
- Skipped: 1

## Fixed Issues

### CR-01: Workbench startup can display an older generation after a newer refresh-status response

**Status:** fixed: requires human verification
**Files modified:** `web/src/pages/ReconciliationWorkbenchPage.tsx`, `web/src/test/WorkbenchSelection.test.tsx`
**Commit:** `9d2df5050`
**Applied fix:** Reconciled initial payload and refresh-status ordering against the canonical read-model version, seeded the initial status baseline, and retained the bounded reload when either response proves that the other generation is stale. Added deterministic initial-first and status-first race regressions.

### CR-02: Capacity report can claim a target concurrency it never reached

**Status:** fixed: requires human verification
**Files modified:** `backend/src/fin_ops_platform/tools/http_slo_probe.py`, `tests/test_http_slo_probe.py`
**Commit:** `07087be5e`
**Applied fix:** Capacity mode now rejects an iteration budget below the derived target before sampling and requires the actual measured concurrency to equal the target before the report can pass.

### CR-03: The release gate never enforces the documented p99 ceiling

**Status:** fixed: requires human verification
**Files modified:** `backend/src/fin_ops_platform/tools/http_slo_probe.py`, `tests/test_http_slo_probe.py`
**Commit:** `d5b6060f1`
**Applied fix:** Added the 2,000 ms p99 target to default and custom probes, exposed separate p95/p99 results, and made the combined SLO/release decision fail when p99 exceeds its ceiling even if p95 passes.

### CR-04: Visibility evidence can skip recovery after an ambiguous submit outcome

**Status:** fixed: requires human verification
**Files modified:** `web/e2e/bank-flow-rule-batches-flow.spec.ts`
**Commit:** `a3d114805`
**Applied fix:** Marked submit as attempted before the request, moved receipt/convergence failures inside the recovery boundary, recovered by exact batch identity and known state, verified the post-withdraw state, and preserved both primary and recovery errors with `AggregateError`.

### CR-05: Over-collected output invoices are classified as still pending

**Status:** fixed: requires human verification
**Files modified:** `backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py`, `tests/test_invoice_usage_collection_postgres_integration.py`
**Commits:** `1815c2fe5`, `8fb73d0a6`
**Applied fix:** Classified non-zero output invoice groups as collected when inflow plus the 0.01 tolerance reaches or exceeds the absolute invoice total, with pending amount fixed at `0.00`. Added and executed a PostgreSQL integration regression for a 100.00 invoice with 120.00 inflow.

### WR-01: The visibility harness does not parse the production dirty-scope DTO

**Files modified:** `web/e2e/bank-flow-rule-batches-flow.spec.ts`
**Commit:** `5ab37ca5a`
**Applied fix:** `cleanStrings()` now accepts both string scopes and production object entries using `scope_key` or `scopeKey`; an executable Chromium test covers exact and `all` scopes.

### WR-02: The sync baseline declares current production measured even when collection failed

**Files modified:** `backend/src/fin_ops_platform/tools/sync_slo_baseline.py`, `tests/test_sync_slo_baseline.py`
**Commit:** `dcec49785`
**Applied fix:** The current-production band is derived after collection from explicitly named critical sections and now reports `not_measured`, `release_blocked: true`, and the unavailable-section reason when any critical section cannot be collected.

### WR-04: The drawer test hides all status-endpoint traffic while claiming zero close-time I/O

**Files modified:** `web/e2e/drawer-motion.spec.ts`
**Commit:** `aa6c1a388`
**Applied fix:** Narrowed the test title and contract to the behavior its existing assertion proves: no close-triggered non-periodic business I/O. The periodic OA/Workbench status traffic remains explicitly identified and excluded from that narrower contract.

## Skipped Issues

### WR-03: Production smoke can be merged with stale isolated evidence from another release

**File:** `web/e2e/fixtures/operationLatency.ts:270`
**Reason:** Skipped as disproportionate to the requested minimal warning pass. A correct fix requires an approved immutable release/build identifier, fixture-manifest digest propagation, maximum evidence-age policy, caller/environment contract, and operations documentation. The current Phase 40 artifact contains isolated evidence only and no `production_smoke` section, so this merge path is unused by the present artifact. The future production-smoke release path remains blocked on defining that contract rather than inventing it locally.
**Original issue:** Production smoke preserves existing isolated evidence without proving release/build equivalence or enforcing evidence age.

## Verification

- `npx vitest run src/test/WorkbenchSelection.test.tsx` — 73 passed.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe tests.test_sync_slo_baseline tests.test_playwright_e2e_strict_diagnostics -v` — 43 passed.
- Focused Chromium visibility tests for dirty-scope parsing, ambiguous-submit recovery, and dual-error preservation — 3 passed.
- Focused Chromium drawer motion/non-periodic-I/O contract — 1 passed.
- Disposable PostgreSQL database `fin_ops_phase40_review_test` — over-collection integration regression passed; database dropped and absence verified afterward.
- `npx tsc -b --pretty false` — passed.
- `bash scripts/verify.sh lint` — passed.
- `git diff --check` — passed before report creation.

## Documentation Impact

Docs updates are not applicable to the eight applied fixes: they restore existing documented contracts or narrow a test title to its existing assertion. WR-03 is intentionally not implemented because it would require a new documented release-evidence contract.

---

_Fixed: 2026-08-06T11:07:58Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
