---
phase: 40-performance-contract-hot-path-closure
reviewed: 2026-08-06T10:43:12Z
depth: standard
files_reviewed: 35
files_reviewed_list:
  - backend/src/fin_ops_platform/services/pending_invoice_canonical_query.py
  - backend/src/fin_ops_platform/services/postgres_repositories/core.py
  - backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py
  - backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
  - backend/src/fin_ops_platform/services/workbench_query_facade.py
  - backend/src/fin_ops_platform/tools/http_slo_probe.py
  - backend/src/fin_ops_platform/tools/sync_slo_baseline.py
  - web/src/components/common/FinanceTable.tsx
  - web/src/pages/ReconciliationWorkbenchPage.tsx
  - web/src/features/workbench/api.ts
  - web/src/features/workbench/exceptionTypes.ts
  - web/e2e/bank-flow-rule-batches-flow.spec.ts
  - web/e2e/drawer-motion.spec.ts
  - web/e2e/fixtures/apiMocks.ts
  - web/e2e/fixtures/operationLatency.ts
  - tests/test_http_slo_probe.py
  - tests/test_invoice_usage_collection_canonical_query.py
  - tests/test_invoice_usage_collection_postgres_integration.py
  - tests/test_pending_invoice_canonical_query.py
  - tests/test_pending_invoice_postgres_integration.py
  - tests/test_playwright_e2e_strict_diagnostics.py
  - tests/test_postgres_repositories_core.py
  - tests/test_postgres_state_store_integration.py
  - tests/test_read_model_architecture_guards.py
  - tests/test_runtime_worker_registry.py
  - tests/test_sync_slo_baseline.py
  - tests/test_workbench_query_facade.py
  - tests/test_workbench_query_postgres_integration.py
  - tests/test_workbench_routes.py
  - tests/test_workbench_source_proof_contract.py
  - tests/test_workbench_sql_runtime.py
  - web/src/test/FinanceTable.test.tsx
  - web/src/test/WorkbenchApi.test.ts
  - web/src/test/WorkbenchApiRuntimePath.test.ts
  - web/src/test/WorkbenchSelection.test.tsx
findings:
  critical: 5
  warning: 4
  info: 0
  total: 9
status: issues_found
---

# Phase 40: Code Review Report

**Reviewed:** 2026-08-06T10:43:12Z
**Depth:** standard
**Files Reviewed:** 35
**Status:** issues_found

## Summary

The scoped Phase 40 implementation does not yet provide a trustworthy performance/correctness closure. Five blockers can either leave the Workbench visibly stale, certify capacity/SLOs that were not actually met, leave a production smoke fixture mutated after an ambiguous submit, or misstate a financial collection status. Four additional test/evidence weaknesses allow production payload-shape drift, unavailable baselines, stale cross-release evidence, and drawer I/O regressions to escape the claimed gates.

Focused unit checks passed (96 Python tests and 128 Vitest tests), which confirms that the defects are gaps in the asserted contracts rather than ordinary red tests.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: First observed fresh generation can be installed as the polling baseline without reloading the page

**Classification:** BLOCKER

**File:** `web/src/pages/ReconciliationWorkbenchPage.tsx:715-765,932-946`

**Issue:** The initial-page path records the displayed generation only in `activeWorkbenchReadModelVersionRef`, while refresh polling compares exclusively against `lastWorkbenchRefreshVersionRef`. That second ref starts empty and is not seeded when initial data is applied. If the first refresh-status response observes `g1` while the page is still displaying `g0`—for example, a writer/worker completes before the first visible poll, or the poll response wins the race with the initial response—lines 936-943 merely store `g1` as the baseline and skip the reload because `previousVersionKey` is empty. Every later poll also sees `g1`, so the page can remain on `g0` indefinitely until an unrelated `g2` is published. This violates the visible-page convergence contract despite the new completion+1s cadence being single-flight.

**Fix:** Synchronize the status baseline with every successfully applied fresh initial generation. Handle both race orders: if initial `g0` is applied first, seed the status ref with `g0`; if status `g1` was observed first and the later initial result is `g0`, schedule the existing 300ms reload instead of overwriting the mismatch. Add tests for both orderings, not only the current failed-v1-then-fresh-v2 sequence.

### CR-02: Capacity reports can pass after exercising fewer clients than the derived target

**Classification:** BLOCKER

**File:** `backend/src/fin_ops_platform/tools/http_slo_probe.py:249-261,450-453,486-501`

**Issue:** `main()` derives and records `target_concurrency`, but `collect_http_slo()` silently clamps actual concurrency to `min(concurrency, iterations, 8)`. With the default five iterations, the mandatory peak tier derives at least `N_peak=8` yet runs only five simultaneous requests. The final report contains `target_concurrency: 8`, `concurrency: 5`, and can still return `status: pass`. A direct reproduction with `iterations=5, concurrency=8` reports five actual workers and `pass`. This is misleading release evidence and defeats the capacity contract.

**Fix:** Fail before sampling when `iterations < target_concurrency`, or raise the per-tier iteration count to at least the target and assert `report["concurrency"] == target_concurrency` before a capacity run can pass. Add a CLI-level regression for the default peak-tier case.

### CR-03: The HTTP release gate ignores the required p99 ceiling

**Classification:** BLOCKER

**File:** `backend/src/fin_ops_platform/tools/http_slo_probe.py:621-670`

**Issue:** `_summarize_probe()` computes p50/p95/p99 but gates only `p95 <= probe.target_ms`. The production contract independently requires p99 <= 2000ms. A 100-sample probe with 95 samples at 1ms and five samples at 3000ms produces p95=1ms, p99=3000ms, and `status: pass`. The tool can therefore approve a release that explicitly violates the blocking p99 contract.

**Fix:** Give each probe an explicit p99 target (default 2000ms), report separate `p95_pass`/`p99_pass`, and require both for status pass. Add a distribution test where p95 passes and p99 fails.

### CR-04: An ambiguous submit skips recovery and can leave the production fixture mutated

**Classification:** BLOCKER

**File:** `web/e2e/bank-flow-rule-batches-flow.spec.ts:908-953`

**Issue:** Recovery is conditional on `submitCommitted`, but that flag is set only after a successful 2xx response has been parsed and validated. If the server commits and the client loses the response, JSON parsing fails, or the server returns an error after commit, the flag remains false and the `finally` block performs no state check or withdrawal. This is exactly the ambiguous-commit case in which recovery is most important, and production-smoke mode operates against a real approved fixture.

**Fix:** Mark the submit as attempted immediately before sending it. In `finally`, query the exact test-owned batch whenever a submit was attempted; withdraw only if its canonical status is active/submitted, accept an already-withdrawn state, and fail closed if the state cannot be determined. Preserve the original error while still surfacing recovery failure.

### CR-05: Over-collected output invoices are classified as pending collection

**Classification:** BLOCKER

**File:** `backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py:729-758`

**Issue:** The `collected` branch requires the linked inflow to equal the invoice total within one cent. The authoritative module state machine says a positive invoice is collected when linked income is greater than or equal to the total. When inflow exceeds the invoice total, the equality branch is false and the partial branch is also false, so the row becomes `pending_collection` while `pending_amount` is simultaneously calculated as `0`. This produces internally contradictory financial output and incorrect summary counts.

**Fix:** Treat `bank_inflow_total + tolerance >= abs(total_with_tax)` as collected in both the status and pending-amount branches. Add a PostgreSQL integration fixture for over-collection and assert `collected`, pending `0.00`, and consistent collected/uncollected counts.

## Warnings

### WR-01: The visibility harness does not parse the production dirty-scope DTO

**Classification:** WARNING

**File:** `web/e2e/bank-flow-rule-batches-flow.spec.ts:123-125,879-889`

**Issue:** `cleanStrings()` stringifies array members. Production refresh-status returns `dirty_scopes` as objects such as `{scope_key, status}`, so the harness turns them into `"[object Object]"` and cannot recognize an exact refreshing scope or reject a broad `all` scope in that branch. The checked-in mock uses the real object shape, but the source-presence tests never exercise this parser. If another visible poll has already enqueued the refresh, the evidence run can miss t2 and hang rather than recording the required stale/refreshing observation.

**Fix:** Parse both string scopes and object entries (`scope_key`/`scopeKey`) and add an executable test using the production object DTO for exact and `all` values.

### WR-02: The sync baseline declares current production measured even when collection failed

**Classification:** WARNING

**File:** `backend/src/fin_ops_platform/tools/sync_slo_baseline.py:91-135,139-143`

**Issue:** `evidence_bands.current_production.status` is hard-coded to `measured` before any section is collected. `_safe_section()` converts every database/runtime failure to `unavailable`, but the band remains measured even if all critical sections failed. This can label a connection/auth/schema failure as current-production evidence.

**Fix:** Derive the band status after collection. Require the named critical sections to be available (and include a top-level failure/release-blocked reason); otherwise mark current production `not_measured`.

### WR-03: Production smoke can be merged with stale isolated evidence from another release

**Classification:** WARNING

**File:** `web/e2e/fixtures/operationLatency.ts:270-299`

**Issue:** A production-smoke run preserves any existing `isolated` object and validates only `sample_count >= 100` and `pass`. The report carries no release identifier, build SHA, fixture-manifest digest, or maximum evidence age. A smoke for release N can therefore be merged with an old isolated run for release N-1 and written with a fresh top-level `generated_at`, making the combined artifact look coherent without proving it is release-equivalent.

**Fix:** Bind both sections to an immutable release/build identifier plus fixture-manifest digest and reject merges when they differ. Preserve separate section timestamps and enforce the approved evidence-age policy.

### WR-04: The drawer test hides all status-endpoint traffic while claiming zero close-time I/O

**Classification:** WARNING

**File:** `web/e2e/drawer-motion.spec.ts:137-178`

**Issue:** `businessCallCount()` removes every OA-sync and Workbench refresh-status call before comparing open/close counts. This avoids periodic-poller flakiness, but it also makes a new drawer-close-triggered request to either endpoint invisible. The test title claims “without ... close-time I/O,” while the assertion proves only that no non-status request occurred.

**Fix:** Keep periodic traffic distinguishable rather than deleting it wholesale—for example, record request timestamps/initiators around the close action or use controlled timers so the expected periodic request count is known—and assert that close itself triggers no request. Alternatively narrow the test title/contract to non-periodic business I/O.

---

_Reviewed: 2026-08-06T10:43:12Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
