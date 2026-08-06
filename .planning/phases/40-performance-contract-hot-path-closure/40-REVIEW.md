---
phase: 40-performance-contract-hot-path-closure
reviewed: 2026-08-06T11:36:23Z
depth: standard
files_reviewed: 37
files_reviewed_list:
  - backend/src/fin_ops_platform/services/pending_invoice_canonical_query.py
  - backend/src/fin_ops_platform/services/postgres_repositories/core.py
  - backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py
  - backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
  - backend/src/fin_ops_platform/services/workbench_query_facade.py
  - backend/src/fin_ops_platform/tools/http_slo_probe.py
  - backend/src/fin_ops_platform/tools/runtime_sync_closure_gate.py
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
  - tests/test_runtime_sync_closure_gate.py
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
  critical: 0
  warning: 1
  info: 0
  total: 1
status: passed_with_warnings
---

# Phase 40: Final Code Review Report

**Reviewed:** 2026-08-06T11:36:23Z
**Depth:** standard
**Files Reviewed:** 37
**Status:** passed_with_warnings

## Summary

All five original Critical findings are now resolved. Commit `70c1d756d` closes the remaining CR-02 by synchronizing capacity waves, measuring lock-protected in-flight requests around the real request call, reporting `observed_peak_concurrency`, and requiring both configured and observed concurrency to equal the derived target before capacity evidence can pass.

Follow-up commit `f8d26a9cf` closes the runtime closure blocker introduced by the expanded `_with_target` signature. The only cross-module caller, `runtime_sync_closure_gate._http_slo_check`, now passes `http_slo_probe.DEFAULT_P99_TARGET_MS`; the module-local caller already passes the CLI p99 target. No stale production caller remains. The release status is still derived from `passes_p95 and passes_p99`, so the closure gate cannot pass on p95 alone.

Direct collector/CLI reproductions confirmed the gate rather than relying only on mocked report fields:

- Real eight-request overlap: configured `8`, observed `8`, target `8`, gate `true`, `status=pass`, exit `0`.
- Immediate-response/low-overlap run: configured `8`, observed `1`, target `8`, gate `false`, `status=fail`, `release_blocked=true`, exit `1`.
- Configured-width mismatch: configured `7`, observed `8`, target `8`, gate `false`, `status=fail`, `release_blocked=true`, exit `1`.

WR-03 remains the accepted non-blocking warning. The checked-in artifact still has `production_smoke: null`; its 100-sample isolated section explicitly sets `production_p99_claim: false`, so no false production claim is made.

## Narrative Findings (AI reviewer)

### Original Critical disposition

| Original | Final result | Evidence |
| --- | --- | --- |
| CR-01 | Resolved | Initial-page and refresh-status generation races reconcile in both response orders. |
| CR-02 | Resolved | Real capacity collection reports the measured peak; configured and observed values are independently required to equal target, and low-peak runs fail closed. |
| CR-03 | Resolved | Independent p95 and p99 ceilings both participate in the release decision. |
| CR-04 | Resolved | Ambiguous submit outcomes always enter exact-fixture recovery, with post-withdraw verification and dual-error preservation. |
| CR-05 | Resolved | Over-collected output invoices use the canonical greater-than-or-equal rule with zero pending amount and consistent counts. |

### Follow-up blocker disposition

| Blocker | Final result | Evidence |
| --- | --- | --- |
| Runtime closure `_with_target` stale caller | Resolved | Commit `f8d26a9cf` supplies `DEFAULT_P99_TARGET_MS` at the sole cross-module call; the focused test asserts every closure probe has the requested p95 target and the default p99 target. Production-call scanning found no other stale caller. |

### Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe -v` — 29 passed.
- Direct real-collector capacity CLI reproduction — eight overlapping calls observed and passed at target 8.
- Direct immediate-response capacity CLI reproduction — observed peak 1 and correctly blocked release.
- Direct configured-mismatch capacity CLI reproduction — configured 7 versus target 8 and correctly blocked release despite observed peak 8.
- `_with_target` production caller scan — one module-local caller and one cross-module caller; both pass p95 and p99 targets.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_sync_closure_gate -v` — 25 passed.
- `bash scripts/verify.sh lint` — passed.
- `git diff --check` — passed before report update and rechecked afterward.

## Warnings

### WR-03: Production smoke can be merged with stale isolated evidence from another release

**Classification:** WARNING

**File:** `web/e2e/fixtures/operationLatency.ts:270-299`

**Issue:** The future production-smoke merge path still validates an existing isolated section only by sample count and pass flag; it does not bind the two sections to one immutable release/build, fixture-manifest digest, or evidence-age policy. This is accepted as non-blocking for Phase 40 because the path remains unused by the current artifact and `production_p99_claim` is explicitly false.

**Fix:** Before enabling production-smoke evidence for a release, add the approved release/build identifier, fixture-manifest digest, separate section timestamps, and maximum evidence age, then reject mismatched or expired evidence.

---

_Reviewed: 2026-08-06T11:36:23Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
