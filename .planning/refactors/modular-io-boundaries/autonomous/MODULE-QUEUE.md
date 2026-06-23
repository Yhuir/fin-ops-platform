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
| 22 | `read-models:bank-detail-pilot-verification-and-template-revision` | analysis-closed | implementation-gap-open | Verified local pilot evidence and template/runbook adequacy, but did not close the module: remaining `server.py` bank detail scope/cache/refresh/callback helpers still need owner/caller/deletion-condition classification, migration or compat-only quarantine; production DB/worker evidence remains deferred. |
| 23 | `read-models:bank-detail-server-helper-quarantine` | implementation-closed | implementation-gap-open | Removed unused `server.py` bank detail read/cache/payload helpers, proved `BankDetailsApplicationService` owns those helpers, and guarded the retained refresh wrapper as gateway-backed. Module still needs category side-effect callback extraction/quarantine and production evidence/defer status. |
| 24 | `read-models:bank-detail-category-side-effect-port-extraction` | implementation-closed | implementation-gap-open | Removed `Application._after_bank_category_confirmation_mutation(...)`, added `BankDetailCategoryMutationSideEffectPort`, injected it into `BankDetailsApplicationService`, and guarded the old callback from returning. Suggestion provider remains classified as compat-only read callback; production worker evidence remains deferred. |
| 25 | `planning:queue-semantics-and-master-goal-prompt-revision` | planning-closed | not-applicable | Corrected autonomous controller semantics before the next implementation run: queue status is slice status, module closure stays separate, `bank_detail` remains implementation-gap-open, and every future slice must reconcile state/queue/prompt before implementation. |
| 26 | `server-py:legacy-handler-extraction-implementation` | implementation-closed | implementation-gap-open | Removed definition-only ETC business-batch legacy handlers from `server.py`, kept active `/api/etc/business-batches*` wrappers delegated to `EtcBusinessBatchApiRoutes`, and added a static guard preventing old handlers/direct actor construction from returning. Broader `server.py` legacy cleanup remains open. |
| 27 | `batch-accounting:legacy-route-implementation` | implementation-closed | implementation-gap-open | Extracted read-only `GET /api/batch-accounting` query/error mapping into `BatchAccountingApiRoutes` while preserving `BatchAccountingService.build_payload(..., use_sql_read_model=True)` as the read contract owner. Submit/withdraw and broader batch-accounting module closure remain open. |
| 28 | `batch-accounting:submit-withdraw-route-side-effect-port` | implementation-closed | implementation-gap-open | Extracted submit/withdraw mutation DTO/service/error mapping and write-after side-effect orchestration into `BatchAccountingApiRoutes` with explicit callbacks; `server.py` keeps session/JSON/response mapping. Repair compat quarantine and broader module closure remain open. |
| 29 | `batch-accounting:repair-compat-quarantine` | implementation-closed | implementation-gap-open | Removed unused app-level `_repair_batch_accounting_relation_case_ids`; service-level `repair_legacy_case_id_collisions` remains tested and command-service backed. Module closure audit and production evidence/defer accounting remain open. |
| 30 | `batch-accounting:module-closure-audit-and-production-evidence-defer` | production-evidence-deferred | not-module-closed | Local IO/route/service/legacy/read-model freshness/operation-barrier/test/docs evidence is sufficient for local closure, but real PostgreSQL/worker/App Status/history/high-row production evidence is unavailable without production validation. |
| 31 | `read-models:bank-detail-module-closure-audit-and-production-evidence-defer` | pending | implementation-pending | Return to the first read model pilot and audit whether bank_detail can move toward closure or explicit production evidence defer without PGSQL_URL/staging dependency. |
| 32 | `go-hot-path:workbench-compute-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for `workbench:matching-grouping-check`; blocked until Workbench/read model IO contracts, legacy isolation, freshness proof, tests and performance evidence are available. |
| 33 | `go-hot-path:workbench-read-model-builder-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for active generation / scoped incremental Go Worker candidate after read model implementation contracts are stable. |
| 34 | `go-hot-path:import-parser-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for parse/normalize/preview Go Processor candidate after import IO contract and performance evidence are available. |
| 35 | `go-hot-path:cost-summary-rollup-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for summary/rollup candidate after cost read model implementation contract is stable. |

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
