# Read Model Browser Data Harness Coverage Map - 2026-06-25

**Boundary:** `planning:read-model-browser-data-harness-coverage-map`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `browser:read-model-browser-data-targeted-smoke-runbook`

## Goal

Map read-model-heavy modules to existing deterministic browser/Vitest evidence, Row262 local API harness evidence, Row245-257 production evidence, and remaining external-risk gaps.

This slice is an evidence map only. It does not run browser tests, production commands, authenticated HTTP smoke, deploys, worker replay, queue repair or module/global closure.

## Inputs Reviewed

- `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
- `analysis/read-model-module-closure-worker-wave-1-acceptance-2026-06-25.md`
- `analysis/contract-read-model-internal-api-contract-harness-implementation-2026-06-25.md`
- `analysis/planning-post-internal-api-contract-harness-next-boundary-selection-2026-06-25.md`
- `docs/dev/testing.md`
- `docs/dev/spec-first-e2e-audit.md`
- `web/package.json`
- `web/e2e/*.spec.ts` targeted inventory
- `web/src/test/*` targeted inventory
- `tests/test_read_model_api_contract_harness.py`
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/NEXT-PROMPT.md`

## Reconciled Browser Evidence Classes

| Evidence class | Meaning in this map | Closure implication |
| --- | --- | --- |
| `browser-local-covered` | Existing deterministic Playwright spec exists and is part of `npm run e2e:smoke`; it uses Chromium, Vite and deterministic API mocks. | Useful local browser-data evidence, not production/browser closure. |
| `browser-local-partial` | Browser evidence exists but does not cover every first-screen/detail/export/freshness/high-row path for the module. | Needs a targeted rerun or a narrow new spec before closure evidence can be strengthened. |
| `vitest-local-covered` | Existing Vitest component/API mapper tests cover response mapping, freshness metadata, permissions, error or export handling. | Useful local contract evidence, not browser evidence. |
| `api-local-covered` | Row262 local `Application.handle_request(...)` harness covers representative GET envelopes and auth guard negatives. | Useful local API evidence, not authenticated production HTTP closure. |
| `production-controlled` | Existing T0 read-only production evidence exists for readiness, dirty scopes, outbox, worker heartbeats, row counts or Workbench high-row query plans. | Shared runtime evidence only; it must be tied to module-specific API/browser behavior before closure. |
| `production-evidence-deferred` | Authenticated production API/browser path, worker-drain write path or module-specific production high-row evidence is still missing. | No module/global closure. |
| `external-risk` | Requires real credentials/session, real PostgreSQL/RabbitMQ/Redis/systemd worker drain, production data shape, real XLSX/browser download behavior, or bounded write operation. | Must not be represented as deterministic local CI coverage. |

## Coverage Map

| Module | Browser local evidence | Vitest/API local evidence | Row262 API harness | Production/shared evidence | Remaining gap |
| --- | --- | --- | --- | --- | --- |
| `reconciliation-workbench` | `browser-local-covered`: `workbench-stale-error-flow`, `workbench-network-recovery-flow`, `workbench-large-scroll-flow`, `workbench-permissions-flow`, `workbench-withdraw-flow`, `workbench-exception-flow`, `workbench-cash-special-flow`, `workbench-candidate-split-flow`, `workbench-relation-fanout` are all in `e2e:smoke`. | `vitest-local-covered`: `WorkbenchApi.test.ts`, selection/render/model tests. | `api-local-covered` for `/api/workbench/settings` and local unavailable envelope for `/api/workbench/summary?month=all`. | `production-controlled`: Row257 active-generation high-row query plan; Row245 readiness/dirty/outbox/worker matrix. | `production-evidence-deferred`: authenticated browser/API first-screen over real session, high-row scroll in real browser, write-operation barrier against production source-version proof. |
| `workbench-relations` | `browser-local-covered`: `workbench-relations-nonfresh-diagnostics`, `workbench-relations-candidate-semantics`, OA/tax fan-out specs, plus Workbench relation flow specs in smoke. | `vitest-local-covered`: Workbench relation API/service/backend tests from W1 handoff. | Not independently represented in Row262 route list beyond Workbench/pending/tax consumers. | `production-controlled`: relation readiness/dirty/outbox rows fresh/done in Row245 matrix. | `production-evidence-deferred`: authenticated relation detail/command smoke and production-like fan-out behavior. |
| `bank-details` + `bank-account-balance` | `browser-local-covered`: `bank-details-initial-state`, `bank-details-stale-refreshing`, `bank-details-large-scroll-flow`, `bank-details-category-flow`, `bank-details-auto-tag-rules-flow`, `bank-details-export-download`, `bank-details-filtered-export-permissions` are in smoke. | `vitest-local-covered`: `BankDetailsPage.test.tsx`, `BankDetailsApi.test.ts`, backend route/read-model tests. | Not directly covered in Row262 representative route list; covered indirectly by page/browser evidence and existing backend tests. | `production-controlled`: Row245 matrix has fresh readiness/done dirty/outbox/queryable row counts for bank detail and account balance. | `production-evidence-deferred`: authenticated API/page smoke against real session, bank-account-balance consumer freshness proof on real browser, high-row/export production evidence. |
| `pending-invoices` | `browser-local-covered`: filter/sort, rules save, attach existing, income status, export download and fan-out specs are in smoke. | `vitest-local-covered`: `PendingInvoicesPage.test.tsx`, `PendingInvoicesApi.test.ts`, backend API/service tests. | `api-local-covered`: rules and rows representative GET envelopes plus unavailable envelope guard. | `production-controlled`: Row245 readiness/dirty/outbox/row-count evidence. | `production-evidence-deferred`: authenticated browser/API response shape over real session and relation/export/freshness proof against production-style data. |
| `input-invoice-usage` | `browser-local-covered`: `input-invoice-usage-flow` covers transient recovery, filter/sort/page-size, read-only export, rules save refresh, non-fresh rows/detail/export, relation detail and export; `input-invoice-relation-fanout` covers downstream relation evidence. | `vitest-local-covered`: `InputInvoiceUsagePage.test.tsx`, filter/drawer tests, backend API/runtime tests. | `api-local-covered`: payment status rules and rows representative GET envelopes. | `production-controlled`: Row245 readiness/dirty/outbox/row-count evidence. | `production-evidence-deferred`: authenticated rows/detail/export API sweep, production-style browser fan-out, invoice lifecycle source-version proof. |
| `output-invoice-collections` | `browser-local-covered`: `output-invoice-collections-flow` covers recovery, filter/sort/page-size, save/receipt recovery, non-fresh rows, read-only/export; `output-invoice-red-relation-fanout` covers relation/downstream evidence. | `vitest-local-covered`: `OutputInvoiceCollectionsPage.test.tsx`, backend API/service/lifecycle tests. | `api-local-covered`: status rules and rows representative GET envelopes. | `production-controlled`: Row245 readiness/dirty/outbox/row-count evidence. | `production-evidence-deferred`: authenticated rows/detail/export API sweep and red relation fan-out with production source-version proof. |
| `oa-pending-payments` | `browser-local-covered`: `oa-pending-payments-flow`, `oa-pending-payments-nonfresh-flow`, confirm-paid, bank-link and relation fan-out specs are in smoke. | `vitest-local-covered`: `OaPendingPaymentsPage.test.tsx`, backend API/service/command tests. | Not directly in Row262 representative route list; covered by accepted W2 local evidence and browser inventory. | `production-controlled`: Row245 readiness/dirty/outbox/row-count evidence. | `production-evidence-deferred`: authenticated command/API flow, production-like nonfresh/detail source-version proof and operation barrier evidence. |
| `tax-offset` | `browser-local-covered`: `tax-offset-flow` covers permission matrix, non-fresh false-empty prevention, plan conflict, large/narrow table, recalculate/save/certified import; `workbench-relations-tax-offset-fanout` covers relation fan-out. | `vitest-local-covered`: `TaxOffsetPage.test.tsx`, `TaxApi.test.ts`, backend tax API/read-model/service tests. | `api-local-covered`: `/api/tax-offset/summary?month=2026-03`. | `production-controlled`: Row245 readiness/dirty/outbox/row-count evidence; Row246 clean scope-contract and legacy `tax` historical-done classification. | `production-evidence-deferred`: authenticated browser/API over real session, cache warmup/runtime proof, high-row table/export production evidence. |
| `cost-statistics` | `browser-local-covered`: `cost-statistics-flow` covers transient recovery, non-fresh false-empty prevention, export preview/download, row-limit feedback, drilldown and nonfresh export/detail; `cost-statistics-relation-fanout` is in smoke. | `vitest-local-covered`: `CostStatisticsPage.test.tsx`, `CostStatisticsApi.test.ts`, backend runtime/read-model tests. | `api-local-covered`: `/api/cost-statistics?month=2026-03&project_scope=active`. | `production-controlled`: Row245 readiness/dirty/outbox/row-count evidence; Row246 clean scope-contract and legacy `cost` historical-done classification. | `production-evidence-deferred`: authenticated API/page/browser proof, parent aggregate/source-version proof and high-row production behavior. |
| `turnover-ledger` | `browser-local-covered`: `turnover-ledger-flow` covers recovery, stale grouped ledger write gate, tag save barrier, manual closure/withdraw barriers and downstream cost freshness. | `vitest-local-covered`: `TurnoverLedgerPage.test.tsx`, `TurnoverLedgerApi.test.ts`, backend API/query/source-version tests. | Not directly in Row262 representative route list. | `production-controlled`: Row245 readiness/dirty/outbox/row-count evidence. | `production-evidence-deferred`: authenticated export/browser flow, relation fan-out, operation barrier and high-row grouped ledger evidence. |
| `no-oa-bank-batches` | `browser-local-covered`: `no-oa-bank-batches-flow` covers transient recovery, stale-to-fresh list behavior, tag-scope save barrier, submit/withdraw barrier and downstream cost freshness. | `vitest-local-covered`: `NoOaBankBatchPage.test.tsx`, `NoOaBankBatchApi.test.ts`, backend API/application/read-model tests. | Not directly in Row262 representative route list. | `production-controlled`: Row245 readiness/dirty/outbox/row-count evidence and prior convergence/dead-letter cleanup. | `production-evidence-deferred`: authenticated browser/API proof after convergence and mutation path production barrier evidence. |
| `batch-accounting` | `browser-local-covered`: `batch-accounting-flow` covers load recovery, stale relation diagnostics, submit/withdraw through relation freshness barrier. | `vitest-local-covered`: `BatchAccountingPage.test.tsx`, backend API/route tests. | Not directly in Row262 representative route list. | Shared `workbench_relation` production readiness is fresh/done in Row245 matrix. | `production-evidence-deferred`: production-style relation barrier and write-after-read closure evidence. |
| `search` | `browser-not-applicable-partial`: no standalone search page route exists in the smoke inventory; search is a backend/API and upstream fan-out surface. | `vitest/backend-local-covered`: `tests/test_search_api.py`, `tests/test_search_service.py`, search pending SQL/runtime tests. | `api-local-covered`: `/api/search?q=...&scope=all&month=all&limit=5`. | `production-controlled`: Row245 search readiness/dirty/outbox/index-row and worker-heartbeat evidence. | `production-evidence-deferred`: authenticated production query response shape, high-row query smoke and upstream fan-out attachment. |

## Smoke Script Impact

`web/package.json` already includes the mapped read-model-heavy browser specs in `npm run e2e:smoke`. A full smoke run would be broad and expensive, and Row263 explicitly rejected running it blindly before a committed map.

The next executable boundary should rerun a small existing subset that maximizes coverage of:

- rows/filter/sort/refreshing false-empty behavior;
- export/row-limit behavior;
- relation or operation-barrier fan-out;
- shared Workbench status/network recovery.

## Selected Next Boundary

Select `browser:read-model-browser-data-targeted-smoke-runbook`.

The runbook should execute existing deterministic Playwright specs only, with no production auth and no new browser harness yet:

```bash
cd web && npx playwright test \
  e2e/workbench-stale-error-flow.spec.ts \
  e2e/pending-invoices-filter-sort-flow.spec.ts \
  e2e/input-invoice-usage-flow.spec.ts \
  e2e/output-invoice-collections-flow.spec.ts \
  e2e/cost-statistics-flow.spec.ts \
  e2e/tax-offset-flow.spec.ts \
  --project=chromium
```

This subset is intentionally not a closure proof. It is the smallest useful local browser-data rerun across shared Workbench/freshness, invoice rows/detail/export, cost/tax read model status, and filter/sort surfaces. If it is too slow or environment-dependent, the runbook must classify the failure precisely and keep production/browser closure deferred.

## Rejected Candidates

| Candidate | Decision | Reason |
| --- | --- | --- |
| Full `npm run e2e:smoke` immediately | Rejected for next slice | Valuable later, but too broad for the first post-map executable boundary. |
| Add a new browser harness now | Rejected | Current inventory shows strong existing specs; rerun a targeted subset before adding new tests. |
| Authenticated production browser smoke | Rejected | No non-secret auth/session path is proven. |
| Authenticated production API retry | Rejected | Row252/259 already proved the missing-auth and unauthenticated-401 conditions. |
| Module/global closure audit | Rejected | Production authenticated API/browser/high-row/module-specific evidence remains open. |

## State-Machine Impact

- Row264 closes as `planning-closed`.
- Row265 is inserted as `pending`.
- No module status changes to `closed`.
- Production authenticated API/browser evidence remains deferred.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

No module docs or long-term architecture docs change in this planning slice because it maps existing evidence and selects the next local browser rerun boundary. If Row265 changes smoke script membership, module coverage status or test facts, that slice must update the relevant docs.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: Row262 existing local API harness evidence is mapped; no new API contract changed.
4. Read model/cache/background job tests: applicable as evidence mapping only; production/worker convergence remains open.
5. Frontend component and interaction tests: applicable; existing Vitest and Playwright evidence is mapped, and Row265 will rerun a targeted browser subset.
6. End-to-end business-flow integration tests: applicable through existing deterministic Playwright specs; no e2e was executed in this planning slice.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- secret scan over changed files
- `git diff --cached --check` after staging

No production command or browser test is executed in this planning slice.
