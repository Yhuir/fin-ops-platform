# Read Model Module Closure Evidence Ownership Map - 2026-06-25

**Boundary:** `planning:read-model-module-closure-evidence-ownership-map`
**Status:** `planning-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `planning:read-model-module-closure-worker-wave-1-prompts`

## Goal

Convert the clean row245 production read-model matrix and row246 clean scope-contract classification into a controller-owned module evidence and file-ownership map before any worker wave, browser/API smoke, or closure claim.

This slice does not prove module or global closure. It exists to make the next worker wave safe: every worker must have non-overlapping file ownership, a precise evidence type, and an explicit handoff path before it starts.

## Inputs Reviewed

- `analysis/planning-post-scope-contract-runtime-classification-next-boundary-selection-2026-06-25.md`
- `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
- `analysis/commit-backed-state-reconciliation-2026-06-25.md`
- `docs/modules/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/read-models/tests.md`
- `autonomous/STATE.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`
- `12-PARALLEL-ORCHESTRATION.md`
- Test and browser file inventory from `tests/`, `web/e2e/`, and `web/src/test/`

## Row245 And Row246 Facts Available To Map

Row245 production evidence is a clean current read-model runtime baseline:

- `/health/ready` was ready for release `dev-workbench-matching-port-20260625020818`.
- All App Status read-model readiness rows were `fresh`.
- All read-model dirty scopes were `done`.
- Read-model outbox events were all `done`.
- No read-model dead-letter groups remained.
- Current read-model workers had fresh heartbeats.
- Read-model row-count and source-version tables were queryable.
- Workbench high-row tables were visible, including `workbench_group_rows`, `workbench_groups`, and `workbench_rows`.

Row246 scope-contract evidence is also clean:

- `read-model-scope-contract --json` returned `ok=true`, `violation_count=0`, no covered historical outbox failures, and no current uncovered outbox failures.
- `--repair invalid-read-model-scopes --json` returned `ok=true`, `invalid_scope_count=0` in dry-run mode.
- Legacy `cost` and `tax` dirty-scope rows are historical `done` rows only, with no active outbox/readiness residue.

These facts can be attached to module-specific audits. They do not prove authenticated API response shape, browser rendering, operation-barrier behavior against production data, export behavior, high-row visual/performance safety, or final modular IO closure.

## Module Evidence And Ownership Map

| Module | Route/API surface | Read-model key(s) | Local implementation/test evidence owners | Row245/246 evidence that applies | Remaining closure gaps | Evidence type still needed |
|---|---|---|---|---|---|---|
| `reconciliation-workbench` | `/`, `/api/workbench/*`, Workbench actions/rows/groups/detail | `workbench` | `docs/modules/reconciliation-workbench/`; `tests/test_workbench_sql_runtime.py`, `tests/test_workbench_query_facade.py`, `tests/test_workbench_routes.py`, `tests/test_workbench_api.py`, `tests/test_workbench_*`; `web/e2e/workbench-*.spec.ts` | `workbench` readiness fresh; dirty scopes done; outbox done; worker heartbeat fresh; high-row counts visible: `workbench_group_rows=737314`, `workbench_groups=378422`, `workbench_rows=661224`; source-version availability sampled | Authenticated API response-shape sweep; browser first-screen/high-row scroll smoke; operation-barrier behavior against production readiness/source-version proof; export/detail paths where applicable | Worker local evidence plus T0 production read-only/API/browser smoke planning |
| `workbench-relations` | Relation command/read APIs used by Workbench, invoice, tax, OA and no-OA flows | `workbench_relation` | `docs/modules/workbench-relations/`; `tests/test_workbench_relation_*`, `tests/test_workbench_pair_relation_*`, `tests/test_workbench_relation_read_facade.py`, `tests/test_workbench_relation_sql_projection.py`; `web/e2e/workbench-relations-*.spec.ts` | `workbench_relation` readiness fresh for 38 scopes; dirty scopes done; outbox done; relation rows/scopes queryable; source-version dependencies sampled | Authenticated relation detail/command smoke; fan-out checks across Workbench, tax, OA and pending invoices; browser diagnostics/nonfresh behavior against production-style data | Worker local evidence plus later T0 smoke |
| `bank-details` | `/bank-details`, `/api/bank-details/*` | `bank_detail` | `docs/modules/bank-details/`; `tests/test_bank_details_sql_runtime.py`, `tests/test_bank_details_routes.py`, `tests/test_bank_details_service.py`, `tests/test_bank_detail_*`; `web/e2e/bank-details-*.spec.ts` | `bank_detail` readiness fresh for 41 scopes; dirty scopes done; outbox done; 814 read rows across 42 scopes; source-version evidence sampled | Authenticated page/API response shape; high-row table scroll/export; stale/refreshing UI against fresh gate; auto-tag side-effect audit against production evidence | Worker local evidence plus browser smoke |
| `bank-account-balance` | Account/balance reads behind bank-details account views and APIs | `bank_account_balance` | `docs/modules/bank-account-balance/`; `tests/test_bank_account_balance_read_model.py`, `tests/test_bank_account_balance_derived_lifecycle_executor.py` | readiness fresh for 1 scope; dirty scopes done; outbox done; 6 balance rows queryable | API/page consumers must be linked to balance freshness; no standalone browser flow is enough without bank-details integration | Worker local evidence, likely paired with bank-details |
| `pending-invoices` | `/pending-invoices`, pending invoice relation/detail/export APIs | `pending_invoice`, relation dependencies | `docs/modules/pending-invoices/`; `tests/test_pending_invoice_api.py`, `tests/test_pending_invoice_service.py`, `tests/test_pending_invoice_*`; `web/e2e/pending-invoices-*.spec.ts` | `pending_invoice` readiness fresh for 126 scopes; dirty scopes done; outbox done; 804 rows; source-version dependencies sampled | Authenticated page/filter/sort/export/API response shape; relation fan-out and operation barrier against production-style data; unavailable/stale states | Worker local evidence plus browser smoke |
| `input-invoice-usage` | `/input-invoice-usage`, usage rows/filter/detail/export/relation APIs | `input_invoice_usage`, `invoice_lifecycle` | `docs/modules/input-invoice-usage/`; `tests/test_input_invoice_usage_api.py`, `tests/test_input_invoice_usage_service.py`, `tests/test_invoice_usage_collection_sql_runtime.py`; `web/e2e/input-invoice-usage-flow.spec.ts`, `web/e2e/input-invoice-relation-fanout.spec.ts` | `input_invoice_usage` readiness fresh for 33 scopes; dirty scopes done; outbox done; 742 rows across 10 scopes; invoice lifecycle readiness fresh for 32 scopes | Authenticated rows/filter/detail API sweep; browser relation fan-out; operation barrier with invoice lifecycle source-version proof | Worker local evidence plus browser smoke |
| `output-invoice-collections` | `/output-invoice-collections`, collection rows/filter/detail/export/relation APIs | `output_invoice_collection`, `invoice_lifecycle` | `docs/modules/output-invoice-collections/`; `tests/test_output_invoice_collection_api.py`, `tests/test_output_invoice_collection_service.py`, `tests/test_output_invoice_collection_lifecycle.py`, `tests/test_invoice_usage_collection_sql_runtime.py`; `web/e2e/output-invoice-collections-flow.spec.ts`, `web/e2e/output-invoice-red-relation-fanout.spec.ts` | `output_invoice_collection` readiness fresh for 33 scopes; dirty scopes done; outbox done; 20 rows across 6 scopes; invoice lifecycle readiness fresh | Authenticated rows/detail/filter/export API sweep; browser flow; red relation fan-out; source-version/operation barrier proof | Worker local evidence plus browser smoke |
| `oa-pending-payments` | `/oa-pending-payments`, pending payment rows/detail/command/relation APIs | `oa_pending_payment`, `invoice_lifecycle`, relation dependencies | `docs/modules/oa-pending-payments/`; `tests/test_oa_pending_payment_api.py`, `tests/test_oa_pending_payment_service.py`, `tests/test_oa_pending_payment_command_service.py`, `tests/test_invoice_usage_collection_sql_runtime.py`; `web/e2e/oa-pending-payments-*.spec.ts` | `oa_pending_payment` readiness fresh for 34 scopes; dirty scopes done; outbox done; 267 rows across 7 scopes; invoice lifecycle fresh | Authenticated command/API flow; browser confirm-paid/bank-link/nonfresh states; relation source-version proof and operation barrier | Worker local evidence plus browser smoke |
| `invoice_lifecycle` shared family | Shared lifecycle projection consumed by invoice usage/collection/OA/pending flows | `invoice_lifecycle` | `docs/modules/read-models/`; invoice modules above; `tests/test_invoice_lifecycle_read_model_refresh.py`, `tests/test_invoice_lifecycle_read_facade.py`, `tests/test_invoice_lifecycle_derived_lifecycle_executor.py`, `tests/test_invoice_lifecycle_page_integration.py` | readiness fresh for 32 scopes; dirty scopes done; outbox done; 1044 rows; source-version availability sampled | Shared dependency must be explicitly mapped in each invoice-family closure audit; no standalone module doc exists, so evidence belongs to read-models plus consuming modules | Worker local evidence split across invoice-family ownership |
| `tax-offset` | `/tax-offset`, tax offset APIs/cache warmup/read model | `tax_offset`; historical legacy `tax` classified | `docs/modules/tax-offset/`; `tests/test_tax_offset_api.py`, `tests/test_tax_offset_sql_runtime.py`, `tests/test_tax_offset_service.py`, `tests/test_tax_offset_read_model_service.py`, `tests/test_tax_offset_*`; `web/e2e/tax-offset-flow.spec.ts`, `web/e2e/workbench-relations-tax-offset-fanout.spec.ts` | `tax_offset` readiness fresh for 19 scopes; dirty scopes done; outbox done; 793 items and 18 read models; legacy `tax` rows are historical done only | Authenticated API/page/browser proof; cache warmup/runtime behavior; Workbench relation fan-out; high-row/refreshing states | Worker local evidence plus browser smoke |
| `cost-statistics` | `/cost-statistics`, cost statistics APIs/read model | `cost_statistics`; historical legacy `cost` classified | `docs/modules/cost-statistics/`; `tests/test_cost_statistics_api.py`, `tests/test_cost_statistics_sql_runtime.py`, `tests/test_cost_statistics_runtime_service.py`, `tests/test_cost_statistics_read_model_service.py`; `web/e2e/cost-statistics-*.spec.ts` | `cost_statistics` readiness fresh for 66 scopes; dirty scopes done; outbox done; 68 read models and 8705 rows; scope contract dry-run clean; legacy `cost` rows historical done only | Authenticated API/page/browser proof; parent aggregate/source-version evidence; high-row and relation fan-out behavior | Worker local evidence plus browser smoke |
| `turnover-ledger` | `/turnover-ledger`, turnover ledger APIs/export/grouping | `turnover_ledger`, relation dependencies | `docs/modules/turnover-ledger/`; `tests/test_turnover_ledger_api.py`, `tests/test_turnover_ledger_query_service.py`, `tests/test_turnover_ledger_read_model_refresh.py`, `tests/test_turnover_ledger_source_versions.py`; `web/e2e/turnover-ledger-flow.spec.ts` | readiness fresh for 1 scope; dirty scopes done; outbox done; 20 rows; source-version tables queryable | Authenticated API/export/browser flow; relation fan-out and operation-barrier proof; high-row grouped ledger evidence remains absent | Worker local evidence plus browser smoke |
| `no-oa-bank-batches` | `/no-oa-bank-batches`, no-OA batch APIs/tag selection/workbench integration | `no_oa_bank_batch` | `docs/modules/no-oa-bank-batches/`; `tests/test_no_oa_bank_batch_api.py`, `tests/test_no_oa_bank_batch_application_service.py`, `tests/test_no_oa_bank_batch_read_model_refresh.py`, `tests/test_no_oa_bank_batch_routes.py`, `tests/test_no_oa_bank_batch_workbench_integration.py`; `web/e2e/no-oa-bank-batches-flow.spec.ts` | readiness fresh for 8 scopes; dirty scopes done after FK fix convergence; outbox done; 65 rows; no dead letters remain | Authenticated API/browser proof after production convergence; relation/workbench integration; regression that FK delete-order fix remains covered | Worker local evidence plus T0 production baseline attachment |
| `search` | `/api/search`, global search read API and upstream fan-out | `search` | `docs/modules/search/`; `tests/test_search_api.py`, `tests/test_search_service.py`, `tests/test_search_pending_sql_runtime.py`; shared upstream producer tests | readiness fresh for 33 scopes; dirty scopes done; outbox done; 2245 index rows; worker heartbeat fresh | Authenticated API response shape; fail-closed behavior under stale/unavailable projection; high-row query smoke and upstream fan-out attachment | Worker local evidence plus API smoke |

## Worker Wave Ownership Design

The next safe worker boundary is not implementation yet. It should create prompts and ownership files for one bounded worker wave from this map, then create worker threads only after those prompts are controller-reviewed.

Proposed wave 1 size: 4 workers. Workers must produce handoff files only and must not edit controller-only files.

| Worker | Scope | Owned docs/tests/evidence files | Forbidden files | Expected handoff |
|---|---|---|---|---|
| W1 | Workbench and relation-heavy closure map | `docs/modules/reconciliation-workbench/**`, `docs/modules/workbench-relations/**`, `docs/modules/turnover-ledger/**`, matching `tests/test_workbench*`, `tests/test_turnover*`, `web/e2e/workbench-*.spec.ts`, `web/e2e/workbench-relations-*.spec.ts`, `web/e2e/turnover-ledger-flow.spec.ts` | controller files; production mutation; unrelated module docs/tests | `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-workbench-relations-turnover.md` |
| W2 | Invoice and OA usage/collection family | `docs/modules/input-invoice-usage/**`, `docs/modules/output-invoice-collections/**`, `docs/modules/oa-pending-payments/**`, invoice lifecycle notes under `docs/modules/read-models/**`, matching `tests/test_input_invoice_usage*`, `tests/test_output_invoice_collection*`, `tests/test_oa_pending_payment*`, `tests/test_invoice_lifecycle*`, `tests/test_invoice_usage_collection*`, `web/e2e/input-invoice-*.spec.ts`, `web/e2e/output-invoice-*.spec.ts`, `web/e2e/oa-pending-payments-*.spec.ts` | controller files; production mutation; Workbench implementation files except read-only references | `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-invoice-oa-family.md` |
| W3 | Bank, pending invoice, no-OA and search evidence map | `docs/modules/bank-details/**`, `docs/modules/bank-account-balance/**`, `docs/modules/pending-invoices/**`, `docs/modules/no-oa-bank-batches/**`, `docs/modules/search/**`, matching `tests/test_bank*`, `tests/test_pending_invoice*`, `tests/test_no_oa_bank_batch*`, `tests/test_search*`, `web/e2e/bank-details-*.spec.ts`, `web/e2e/pending-invoices-*.spec.ts`, `web/e2e/no-oa-bank-batches-flow.spec.ts` | controller files; production mutation; invoice usage module files | `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-bank-pending-nooa-search.md` |
| W4 | Cost and tax evidence map | `docs/modules/cost-statistics/**`, `docs/modules/tax-offset/**`, matching `tests/test_cost_statistics*`, `tests/test_tax_offset*`, `web/e2e/cost-statistics-*.spec.ts`, `web/e2e/tax-offset-flow.spec.ts`, `web/e2e/workbench-relations-tax-offset-fanout.spec.ts` | controller files; production mutation; unrelated financial modules | `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-cost-tax.md` |

## Evidence Classification Rules For Workers

- `row245-production-baseline`: cite the row245 matrix only for current production readiness/dirty/outbox/row-count/source-version/worker heartbeat facts.
- `row246-scope-contract-baseline`: cite row246 only for clean scope-contract and legacy `cost`/`tax` classification.
- `local-test-evidence`: cite exact unit/API/e2e files and gaps; do not claim passing unless the worker or T0 runs the command.
- `browser-smoke-needed`: identify exact Playwright spec or missing spec needed for first-screen, stale/refreshing, high-row scroll, export or operation-barrier evidence.
- `api-smoke-needed`: identify exact endpoint classes and response fields that need authenticated or production-style proof.
- `t0-production-read-only-needed`: request only read-only production evidence, with proposed command categories and stop gates. Workers must not execute root SSH.
- `closure-not-claimed`: every handoff must end with an explicit statement that no module/global closure is proven until T0 accepts evidence and runs required verification.

## Exact Next Boundary

Select `planning:read-model-module-closure-worker-wave-1-prompts`.

This boundary should:

1. Turn the four worker scopes above into concrete prompts.
2. Record base commit, forbidden files, exact handoff paths, required docs, and verification expectations.
3. Use thread tools to create at most four worker threads only after the prompts and ownership are written.
4. Track thread ids and statuses in a controller analysis file.
5. Avoid production mutation and avoid module/global closure claims.

The next boundary is planning/parallel-orchestration, not final closure and not Go admission.

## Docs Impact Assessment

This slice changes controller accounting only:

- `autonomous/STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md` need updates so the next T0 run starts from row249.
- Module facts, API contracts, state machines and test matrices are not changed in this slice.
- `docs/modules/*` updates are not required now; workers may propose module doc updates in their handoffs if they find stale module-specific facts.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule or calculation changed.
2. Service-layer tests: not applicable; no service/repository/worker behavior changed.
3. API contract tests: not applicable for this planning-only slice; API gaps are mapped for workers.
4. Read model/cache/background job tests: evidence-only; row245/246 are attached but no runtime path changed.
5. Frontend component and interaction tests: not applicable for this slice; browser gaps are assigned to the next worker wave.
6. End-to-end business-flow integration tests: not applicable for this slice; cross-module flow gaps are mapped.
7. Existing feature regression tests: planning-only regression is covered by docs verification and diff checks; no product behavior changed.

## Verification Plan

Run before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check` after staging

No production command, browser run, or runtime test is required for this planning-only ownership map.
