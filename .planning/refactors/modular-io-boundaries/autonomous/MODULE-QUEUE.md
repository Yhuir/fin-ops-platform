# Autonomous Module Queue

**Purpose:** Ordered queue for unattended modular IO refactor execution.
**Rule:** Each item is a narrow boundary, not an entire product area.
**Correction:** `Status` describes the completed slice, not full module closure. A slice can be closed as analysis, guard, inventory, or regression evidence while the module still has implementation gaps.

## Selection Rule

Pick the first item whose status is `pending`.

Do not select Go hot-path candidates while any prior `pending` implementation/foundation boundary remains. Go candidates stay `blocked-by-prerequisite` until the relevant IO contract, legacy retirement/quarantine, freshness proof, tests, performance evidence, shadow-run plan and rollback gates are satisfied.

| Order | Boundary | Status | Module Closure | Notes |
| ---: | --- | --- | --- | --- |
| 1 | `bank-details:auto-tag-category-boundary` | production-evidence-deferred | not-module-closed | Local contract/code guard/doc slice completed; real production DB/worker evidence deferred because no local PGSQL_URL or staging DB. Broader bank-details module still has open IO/freshness/legacy closure work. |
| 2 | `read-models:manifest-and-boundary-inventory` | analysis-closed | implementation-gap-open | Manifest/owner/IO/state/event/permission/test inventory completed as analysis only; no behavior change. |
| 3 | `read-models:query-gateway-contract-and-status-parity` | contract-guard-closed | implementation-gap-open | Added code-level read model manifest and parity guard covering App Status registry, worker events, RabbitMQ dispatch and scope policy contracts; no runtime behavior change. |
| 4 | `read-models:refresh-gateway-force-refresh-and-operation-barrier` | contract-guard-closed | implementation-gap-open | Added manifest force refresh and operation barrier contract guards; no runtime behavior change. |
| 5 | `read-models:repository-port-and-sql-owner-split-plan` | contract-guard-closed | implementation-gap-open | Added manifest repository port contract owner map and guard tests; no SQL split yet. |
| 6 | `read-models:workbench-active-generation-contract` | contract-guard-closed | implementation-gap-open | Added manifest guard preserving Workbench active generation special-case contract; no Workbench builder migration yet. |
| 7 | `read-models:bank-detail-and-bank-account-balance-contract` | contract-guard-closed | implementation-gap-open | Added manifest guard keeping bank detail and bank account balance scope/repository/test contracts separate; no implementation migration yet. |
| 8 | `read-models:pending-invoice-and-oa-pending-payment-contract` | contract-guard-closed | implementation-gap-open | Added manifest guard preserving pending invoice page-first-screen scope and OA pending payment fan-out contracts; no implementation migration yet. |
| 9 | `read-models:invoice-lifecycle-and-usage-contract` | contract-guard-closed | implementation-gap-open | Added manifest guard preserving invoice lifecycle, input usage and output collection scoped incremental contracts and disjoint repository ports; no implementation migration yet. |
| 10 | `read-models:cost-tax-ledger-summary-contract` | contract-guard-closed | implementation-gap-open | Added manifest guard preserving cost parent aggregate semantics, tax/turnover fan-out contracts and disjoint repository ports; no implementation migration yet. |
| 11 | `read-models:search-and-no-oa-bank-batch-contract` | contract-guard-closed | implementation-gap-open | Added manifest guard preserving search partitioned index ownership and no-OA scoped incremental read-side contracts with disjoint repository ports; no implementation migration yet. |
| 12 | `read-models:legacy-read-path-removal-guards` | static-guard-closed | implementation-gap-open | Added static guard classifying direct read model refresh enqueue wrappers so new legacy producers cannot bypass gateway/scope policy unnoticed; this does not remove every legacy path. |
| 13 | `reconciliation-workbench:amount-check-query-contract` | regression-guard-closed | implementation-gap-open | Added amount-check input priority guard proving explicit `reconciliation_amount` wins over legacy `detail_fields.明细金额合计` fallback; no runtime behavior change. |
| 14 | `batch-accounting:legacy-route-contract` | route-guard-closed | implementation-gap-open | Added route handler static guard preventing GET repair/write/read-model scheduling and submit/withdraw direct relation write bypasses; no runtime behavior change. |
| 15 | `server-py:route-owner-inventory` | inventory-guard-closed | implementation-gap-open | Added static inventory guard proving every existing `routes_*.py` owner is registered/imported/delegated from `server.py`; no runtime behavior change. |
| 16 | `planning:state-reconciliation-and-roadmap-alignment` | planning-closed | not-applicable | Reconciled root page-analysis roadmap, modular IO phase roadmap, autonomous queue, state-machine rules and autonomous prompt completion metrics; no runtime behavior change. |
| 17 | `planning:completion-semantics-and-queue-reclassification` | planning-closed | not-applicable | Reclassified prior `closed-autonomous` entries as analysis/guard/regression/inventory slices rather than module closure; parked Go candidates behind implementation prerequisites. |
| 18 | `read-models:pilot-gap-audit-and-contract-selection` | analysis-closed | implementation-gap-open | Selected `bank_detail` as the first read model implementation pilot and documented candidate comparison, entry points, IO gaps, freshness/force-refresh/operation-barrier gaps, legacy risks and seven-category test plan. No runtime behavior change. |
| 19 | `read-models:bank-detail-repository-port-extraction` | implementation-closed | implementation-gap-open | Added `BankDetailReadModelRepositoryPort`, wired `PostgresStateStore.bank_detail_sql_read_repository` to the narrow port, and made `server.py` legacy SQL helpers delegate to `BankDetailsApplicationService`; tests prove unrelated read model methods are not exposed and old helpers do not bypass the application boundary. Module still needs freshness/barrier and legacy removal. |
| 20 | `read-models:bank-detail-refresh-freshness-operation-barrier` | implementation-closed | implementation-gap-open | Added BankDetails write/force-refresh response `read_model_scope_keys` and `freshness_targets`, kept refresh enqueue behind `ReadModelRefreshGateway`/scope policy, and added tests proving exact month operation barrier targets and other-month outbox isolation. Module still needs legacy removal and pilot verification. |
| 21 | `read-models:bank-detail-legacy-contamination-removal` | implementation-closed | implementation-gap-open | Removed the unused `server.py` bank detail SQL read compat helpers, moved tests to the route/application public boundary, and added a guard proving `Application._get_bank_detail_*_from_sql_read_model` cannot return. Module still needs pilot verification/template revision and production evidence/defer status. |
| 22 | `read-models:bank-detail-pilot-verification-and-template-revision` | pending | implementation-pending | Verify the `bank_detail` pilot module, update templates/runbook based on evidence, and decide the second batch only after the pilot is actually verified or production-evidence-deferred. |
| 23 | `server-py:legacy-handler-extraction-implementation` | pending | implementation-pending | Continue route/service extraction only after pilot read model implementation evidence is available; keep `server.py` thin and test route ownership. |
| 24 | `batch-accounting:legacy-route-implementation` | pending | implementation-pending | Convert one batch-accounting route/legacy boundary from guard-only to actual service/repository/read-model contract implementation. |
| 25 | `go-hot-path:workbench-compute-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for `workbench:matching-grouping-check`; blocked until Workbench/read model IO contracts, legacy isolation, freshness proof, tests and performance evidence are available. |
| 26 | `go-hot-path:workbench-read-model-builder-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for active generation / scoped incremental Go Worker candidate after read model implementation contracts are stable. |
| 27 | `go-hot-path:import-parser-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for parse/normalize/preview Go Processor candidate after import IO contract and performance evidence are available. |
| 28 | `go-hot-path:cost-summary-rollup-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for summary/rollup candidate after cost read model implementation contract is stable. |

## Status Values

- `pending`
- `in-progress`
- `analysis-closed`
- `contract-guard-closed`
- `static-guard-closed`
- `regression-guard-closed`
- `route-guard-closed`
- `inventory-guard-closed`
- `implementation-closed`
- `planning-closed`
- `production-evidence-deferred`
- `deferred-module-failure`
- `deferred-scope-too-large`
- `go-candidate-deferred`
- `blocked-by-prerequisite`
- `needs-human-production-gate`

## Module Closure Values

- `implementation-pending`
- `implementation-gap-open`
- `not-module-closed`
- `not-applicable`
- `go-admission-not-started`
- `closed`
