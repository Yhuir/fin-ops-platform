---
phase: 40
slug: performance-contract-hot-path-closure
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-06
revised: 2026-08-06
---

# Phase 40 — Validation Strategy

> 八个小计划共享一个 correctness/performance/release gate；40-08 是唯一允许 push/deploy 的计划。

## Test Infrastructure

| Property | Value |
| --- | --- |
| Backend | pytest 8.0.1 |
| Frontend | Vitest 2.1.4 + Testing Library |
| Browser | existing Playwright 1.60.0 Chromium, `web/e2e/bank-flow-rule-batches-flow.spec.ts` |
| Browser clock helper | existing `web/e2e/fixtures/operationLatency.ts`; Node monotonic integer microseconds owns t0..t4 |
| Browser report | `.planning/phases/40-performance-contract-hot-path-closure/40-workbench-visibility-p99.json` |
| Full suite | `bash scripts/verify.sh lint && bash scripts/verify.sh all && bash scripts/verify.sh runtime-check && bash scripts/verify.sh infra-smoke` |

## Sampling Rate

- After 40-01: probe + FinanceTable targeted tests.
- After 40-02: three SQL owner tests with real test PostgreSQL.
- After 40-03: import repository query-count + PostgreSQL transaction tests.
- After 40-04: docs/registry/no-OA guards then full local gates; no push/deploy.
- After 40-05: refresh-status service/API/gateway quick gate.
- After 40-06: frontend fake-timer/visibility/single-flight gate.
- After 40-07 Task 1: real writer-proof + bank-flow queue/worker closure.
- After 40-07 Task 2: DTO guards + deterministic Chromium correctness flow.
- Before 40-08 release: named concurrency derivation, both capacity tiers, >=100 isolated same-clock Playwright samples, exact segment sum and total p99, then full suite.
- Production: exactly one approved reversible Browser smoke; it cannot be used as p99.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat | Test / Evidence | Automated Command | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 40-01-01 | 01 | 1 | D-04,D-05,D-07 | T-40-01-01,02 | bounded probe + measured/not_measured | `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_http_slo_probe.py tests/test_sync_slo_baseline.py` | pending |
| 40-01-02 | 01 | 1 | D-05,D-06 | T-40-01-03 | constant pagination + exact/aria | `npm --prefix web test -- --run src/test/FinanceTable.test.tsx` | pending |
| 40-02-01 | 02 | 1 | D-04,D-06 | T-40-02-01..03 | three SQL owners, real PostgreSQL equivalence | `test -n "${FIN_OPS_TEST_DATABASE_URL:-}" && PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_pending_invoice_canonical_query.py tests/test_pending_invoice_postgres_integration.py tests/test_invoice_usage_collection_canonical_query.py tests/test_invoice_usage_collection_postgres_integration.py tests/test_workbench_sql_runtime.py tests/test_workbench_query_postgres_integration.py` | pending |
| 40-03-01 | 03 | 1 | D-04,D-06 | T-40-03-01..03 | import batch query-count/owner/rollback | `test -n "${FIN_OPS_TEST_DATABASE_URL:-}" && PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_postgres_repositories_core.py tests/test_postgres_state_store_integration.py` | pending |
| 40-04-01 | 04 | 2 | D-01..D-09 | T-40-04-01,02 | Search/no-OA current facts and guards | `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_read_model_architecture_guards.py tests/test_runtime_worker_registry.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_routes.py && bash scripts/verify.sh docs` | pending |
| 40-04-02 | 04 | 2 | D-09 | T-40-04-03 | full local candidate; no remote mutation | `bash scripts/verify.sh lint && bash scripts/verify.sh all && bash scripts/verify.sh runtime-check && bash scripts/verify.sh infra-smoke` | pending |
| 40-05-01 | 05 | 1 | D-10,D-11,D-13,D-16 | T-40-05-01..03 | status exact self-heal/API shape | `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_workbench_query_facade.py tests/test_workbench_routes.py tests/test_read_model_refresh_gateway.py` | pending |
| 40-06-01 | 06 | 1 | D-12,D-13,D-15,D-16 | T-40-06-01..03 | visible settle+1s/hidden/single-flight/reload-once | `npm --prefix web test -- --run src/test/WorkbenchSelection.test.tsx src/test/WorkbenchApiRuntimePath.test.ts` | pending |
| 40-07-01 | 07 | 2 | D-10,D-11,D-16,D-17 | T-40-07-01,02,04 | all writer proofs + bank-flow real worker closure | `test -n "${FIN_OPS_TEST_DATABASE_URL:-}" && PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_workbench_source_proof_contract.py tests/test_postgres_repositories_boundaries.py tests/test_bank_flow_rule_batch_backend_boundary.py tests/test_bank_flow_rule_batch_application_service.py tests/test_bank_flow_rule_batch_routes.py tests/test_runtime_worker_read_model_refresh_scopes.py` | pending |
| 40-07-02 | 07 | 2 | D-10,D-14,D-16 | T-40-07-03 | dead local target removal + deterministic Browser correctness | `npm --prefix web test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchSelection.test.tsx && npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium` | pending |
| 40-08-01 | 08 | 3 | D-10..D-17 | T-40-08-05 | long-term contract/docs guards | `bash scripts/verify.sh docs && PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_read_model_architecture_guards.py tests/test_runtime_worker_registry.py` | pending |
| 40-08-02 | 08 | 3 | D-04,D-05,D-07,D-13,D-15 | T-40-08-01..04 | derived capacity + same-clock Browser p99 | `PYTHONPATH=backend/src:. python3 -m pytest -q tests/test_http_slo_probe.py tests/test_playwright_e2e_strict_diagnostics.py && test -n "${FIN_OPS_E2E_WORKBENCH_SLO_FIXTURE_MANIFEST:-}" && FIN_OPS_E2E_WORKBENCH_VISIBILITY_SLO=1 FIN_OPS_E2E_WORKBENCH_VISIBILITY_SLO_SAMPLES=100 npm --prefix web run e2e -- e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium --grep "commit-to-visible same-clock"` | pending |
| 40-08-03 | 08 | 3 | D-02,D-07,D-09,D-13,D-15,D-16 | T-40-08-05,06 | full gates + only release + rollback | `bash scripts/verify.sh lint && bash scripts/verify.sh all && bash scripts/verify.sh runtime-check && bash scripts/verify.sh infra-smoke` | pending |

## Browser Same-Clock Contract

The existing Playwright spec/helper are the only timing owner:

1. `g0`: visible Workbench baseline fresh generation.
2. `t0`: immediately before existing authenticated bank-flow submit POST through `workbenchPage.context().request` (Playwright `APIRequestContext` sharing the browser-context cookies).
3. `t1`: submit response resolves with canonical 2xx receipt.
4. `t2`: raw existing refresh-status response first binds the expected exact scope as stale/enqueue-observed or refreshing; broad `all` fails.
5. `t3`: raw status becomes fresh at `g1 != g0`.
6. `t4`: combined payload for `g1` contains submitted transaction/relation identity and its unique business label is visible in Workbench DOM after the existing 300ms debounce.

Sample key: `{sample_id,batch_id,transaction_ids,business_identity,exact_scope,g0,g1}`. All marks are integer microseconds from the same Node monotonic source in `operationLatency.ts`; each report row asserts adjacent segment sum equals `t4-t0` exactly before percentile aggregation.

## Wave 0 Requirements

- Extend existing probe/FinanceTable/SQL/import tests; no wildcard-owned test directory.
- Add only `tests/test_workbench_source_proof_contract.py` as a new test-owned matrix.
- Extend the existing Workbench frontend tests and bank-flow Playwright spec; do not add an endpoint, runner, correlation field, worker, table, cache or dependency.
- Root-owned Browser fixture manifest must declare `fixture_ownership=test_owned`, exact batch/transaction/business identity/scope, existing submit and exact withdraw recovery operations. Production manifest has exactly one sample; isolated prod-equivalent manifest has at least 100.
- Browser report is fail-closed for missing marks, non-monotonic marks, identity/scope/generation mismatch, segment-sum mismatch, insufficient samples, missing recovery or p99>3000ms.

## Manual / Evidence-Gated Verifications

| Behavior | Blocking Evidence |
| --- | --- |
| Target concurrency | named recent 14-day source/window/method with `C_normal=p95`,`C_peak=max`, or approved versioned contract; else NOT_MEASURED |
| Capacity | `N_normal=max(4,C_normal)`,`N_peak=max(8,C_peak)`; refresh-status p95<=1000ms,error=0,SQL/pool/DB/queue/worker no saturation |
| Commit-to-visible p99 | >=100 isolated recovered Playwright samples, one Node clock, exact sample binding and segment identity, total p99<=3000ms |
| Production smoke | one approved test-owned reversible sample via `scripts/with-production-admin-token.sh`; smoke only |
| Release | one local/origin/main/active SHA, official deploy, T+0/T+60/T+300, 6/2 topology, queue/Audit/page evidence, previous release anchor |

## Validation Sign-Off

- [x] 8 plans / 13 tasks; every task has automated verification.
- [x] Same-wave plans have no modified-file overlap.
- [x] No plan has 5+ tasks or more than 15 modified files.
- [x] All directory wildcards removed; every action-owned file is exact.
- [x] Only 40-08 Task 3 may push/deploy.
- [x] Browser t0..t4 wiring names exact existing spec/helper/report and one monotonic clock.
- [x] Seven categories, D-10..D-17, proof coverage, legacy preservation, threats and rollback remain blocking.

**Approval:** pending plan-checker and execution evidence
