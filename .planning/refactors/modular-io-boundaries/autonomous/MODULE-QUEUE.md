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
| 31 | `read-models:bank-detail-module-closure-audit-and-production-evidence-defer` | analysis-closed | implementation-gap-open | Closure audit completed: bank_detail cannot be marked closed or merely production-evidence-deferred because local implementation gaps remain in suggestion provider, refresh/wakeup wrappers, available-month scope helper, lifecycle executor and service factory injection. |
| 32 | `read-models:bank-detail-suggestion-provider-port-extraction` | implementation-closed | implementation-gap-open | Removed the app-level latest suggestion callback, added `BankDetailAutoCategorySuggestionProvider`, moved row shaping to a public service-owned method, and guarded the old callback from returning. |
| 33 | `read-models:bank-detail-refresh-producer-port-extraction` | implementation-closed | implementation-gap-open | Removed app-level bank detail refresh/wakeup wrappers, added `BankDetailReadModelRefreshProducer`, kept enqueue behind `ReadModelRefreshGateway`, and preserved Redis as optional wakeup. |
| 34 | `read-models:bank-detail-available-month-scope-provider-extraction` | implementation-closed | implementation-gap-open | Removed app-level available-month scope helper, added `BankDetailAvailableMonthScopeProvider`, preserved import-transaction date-field month extraction and `all` fallback. |
| 35 | `read-models:bank-detail-derived-lifecycle-executor-port-extraction` | implementation-closed | implementation-gap-open | Removed app-level bank detail derived lifecycle executor, added `BankDetailDerivedLifecycleExecutor`, preserved explicit month/all/default scope selection and enqueue payload shape. |
| 36 | `read-models:bank-detail-service-factory-collaborator-closure-audit` | production-evidence-deferred | not-module-closed | Audit found remaining service factory code is dependency assembly only. Current local implementation support slices are complete through this audit, but this is not full module closure; real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred. |
| 37 | `planning:semantic-queue-state-and-master-goal-refresh` | planning-closed | not-applicable | Corrected state/queue wording and regenerated the master goal controller prompt so future autonomous runs start from current queue facts and cannot confuse slice completion with module closure. |
| 38 | `read-models:next-pilot-selection-after-bank-detail` | analysis-closed | implementation-gap-open | Selected `workbench_relation` as the next read model implementation pilot after comparing remaining manifest candidates; queued repository port extraction as the first narrow implementation boundary. |
| 39 | `read-models:workbench-relation-repository-port-extraction` | implementation-closed | implementation-gap-open | Added `WorkbenchRelationReadModelRepositoryPort`, wired app/worker/projection builder relation read-model paths through it, and tested that unrelated read model methods are not exposed. |
| 40 | `read-models:workbench-relation-derived-lifecycle-executor-port-extraction` | implementation-closed | implementation-gap-open | Removed the app-level workbench relation derived lifecycle refresh enqueue helper, added `WorkbenchRelationDerivedLifecycleExecutor`, preserved explicit scope/default all/gateway-backed enqueue payload shape, and guarded the old helper from returning. |
| 41 | `read-models:workbench-relation-local-implementation-closure-audit` | analysis-closed | implementation-gap-open | Audited remaining local workbench relation gaps and selected transaction persist repository owner split as the next narrow implementation boundary; module remains open. |
| 42 | `workbench-relations:transaction-persist-repository-owner-split` | implementation-closed | implementation-gap-open | Transaction pair relation persist now uses `PostgresWorkbenchRelationRepository.save_workbench_pair_relations(...)` instead of broad `PostgresWorkbenchRepository`, with a static guard and relation/UoW regression tests. |
| 43 | `workbench-relations:command-repository-snapshot-adapter-audit` | pending | implementation-pending | Audit app-level callback repository and snapshot merge/apply helpers before extracting them into an explicit adapter/port or selecting a smaller persist/schedule helper boundary. |
| 44 | `go-hot-path:workbench-compute-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for `workbench:matching-grouping-check`; blocked until Workbench/read model IO contracts, legacy isolation, freshness proof, tests and performance evidence are available. |
| 45 | `go-hot-path:workbench-read-model-builder-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for active generation / scoped incremental Go Worker candidate after read model implementation contracts are stable. |
| 46 | `go-hot-path:import-parser-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for parse/normalize/preview Go Processor candidate after import IO contract and performance evidence are available. |
| 47 | `go-hot-path:cost-summary-rollup-admission` | blocked-by-prerequisite | go-admission-not-started | Admission review only for summary/rollup candidate after cost read model implementation contract is stable. |

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
