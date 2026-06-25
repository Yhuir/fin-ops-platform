# Read Model Main Closure Reconciliation - 2026-06-25

## Run Context

- Branch: `main`
- Reconciliation commit: `0bead534`
- Backup branch: `codex/backup-main-before-read-model-closure-20260625-230543`
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
- Main override: user-authorized direct `main` execution; this supersedes the older dev-only autonomous workflow for this read-model closure run.
- Production/server access: not used in this reconciliation. No secret, production DB mutation, queue mutation, readiness mutation, or worker replay was performed.

## Evidence Read

- Long-term facts: `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, `docs/index.md`, `docs/app-architecture/README.md`, `docs/app-architecture/pages.md`, `docs/app-architecture/runtime-and-ownership.md`, `docs/modules/README.md`, `docs/modules/read-models/README.md`, `docs/modules/read-models/state-machine.md`, `docs/modules/read-models/tests.md`, `docs/operations/runtime-worker-governance.md`.
- Refactor facts: `.planning/refactors/README.md`, `.planning/refactors/modular-io-boundaries/README.md`, `00-REQUIREMENTS.md`, `01-CURRENT-STATE-AUDIT.md`, `02-MODULE-IO-CONTRACT-TEMPLATE.md`, `03-REFACTOR-STATE-MACHINE.md`, `04-IMPLEMENTATION-ROADMAP.md`, `05-IMPACT-AND-TEST-GATES.md`, `07-DOCS-GOVERNANCE.md`, `10-AUTONOMOUS-STOP-GATES.md`, `autonomous/STATE.md`, `autonomous/MODULE-QUEUE.md`, `autonomous/JOURNAL.md`, `autonomous/NEXT-PROMPT.md`.
- CodeGraph:
  - `codegraph_status`: index healthy, 1064 files, 36384 nodes, 91256 edges.
  - `codegraph_context`: read model architecture entry points are `ReadModelScopePolicyRegistry`, `ReadModelScopePolicy`, `ReadModelQueryGateway`.
  - `codegraph_trace`: `ReadModelQueryGateway.load -> _enqueue_refresh -> ReadModelRefreshGateway.enqueue_many_events`, proving query miss/stale routes through scope policy and gateway before durable queue enqueue.
  - `codegraph_impact READ_MODEL_MANIFEST`: direct impact is manifest/test contract surface.

## Current Global Finding

The codebase has a strong shared contract layer but is not globally closed at PSCIP-L4.

- L1/L2 shared gates are present and green: manifest, App Status registry, worker registry, RabbitMQ dispatch event list, scope policy registry, query gateway, refresh gateway, operation barrier and static architecture guards all pass current local tests.
- Most read models have local implementation support slices recorded as complete or production-evidence-deferred in `MODULE-QUEUE.md`.
- PSCIP-L4 is not proven for any read model in this run because no production or equivalent runtime App Status/dirty/outbox/readiness/worker/high-row query evidence was collected.
- Several manifest entries still pointed at shared `PostgresReadModelRepository.*` repository owners even though narrow repository ports already exist and are wired. This is a global contract drift and is selected as Wave 1.
- Workbench remains the explicit exception: active generation scoped publish is not mechanically converted into an ordinary projection gateway.

## Closure Matrix

| key | page/domain | strategy | exception | query owner | route/API owner | repository port owner | physical SQL owner | refresh producer owner | worker owner | freshness proof | PSCIP level | partition proof | scoped query proof | incremental builder proof | performance proof | force refresh | operation barrier | frontend behavior | legacy status | production evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `workbench` | Reconciliation workbench | active generation scoped publish | active generation exception | `WorkbenchQueryFacade` | workbench routes / legacy server route owners | `PostgresReadModelRepository.workbench` | `read_model.workbench_*` active generation tables via shared repository | `WorkbenchReadModelRefreshService` | `workbench` | active generation metadata + matching rule source versions + dirty/outbox current-effective state | L2 local-runtime, L4 missing | month active generation + all aggregate | active scope/generation query path | affected month generation rebuild, all aggregate from month shards | bounded page query guard exists; production sample missing | gateway active generation force refresh | App Status target | workbench must wait for active generation or operation projection contract | special retained path, not ordinary legacy | needs production App Status/worker/API/perf sample |
| `workbench_relation` | Workbench relation distribution | scoped incremental distribution | none | `WorkbenchRelationReadFacade` | downstream page APIs | `WorkbenchRelationReadModelRepositoryPort` | shared SQL methods behind port | `WorkbenchRelationDerivedLifecycleExecutor` / refresh service | `workbench-relation` | relation scope source versions + readiness + dirty/outbox | L3 local implementation support, L4 missing | month scope, all fan-out only | port/facade scoped reads | affected month distribution rebuild | local tests; production high-row sample missing | gateway force refresh | App Status target | downstream pages must not treat non-fresh empty relation as fresh | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `bank_detail` | Bank Details | partitioned scoped incremental | none | `BankDetailsApplicationService` | bank detail route owner | `BankDetailReadModelRepositoryPort` | shared SQL methods behind port | `BankDetailReadModelRefreshProducer` | `bank-detail` | month shard source summary + dirty/outbox | L3 local support, L4 missing | bank transaction month shard | range queries use month shard proof | affected transaction/tag/account month rebuild | local guard/tests; production query plan missing | gateway force refresh | exact month App Status target | page must show refreshing when shard not fresh | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `bank_account_balance` | Bank account balance/accounts API | all-only scoped projection | all-only scoped projection | `BankDetailsApplicationService` | bank details accounts API | `BankAccountBalanceReadModelRepositoryPort` | shared SQL methods behind port | `BankAccountBalanceReadModelRefreshProducer` | `bank-account-balance` | `bank_account_balance:all` readiness + dirty/outbox | L3 local support, L4 missing | global `all` only | all-only policy rejects month/account scopes | affected bank import refreshes all-only snapshot | local operation barrier regression; production sample missing | gateway force refresh | `bank_account_balance:all` target | accounts target waits for all-only freshness | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `pending_invoice` | Pending invoices | page-first scoped incremental | bare `all` forbidden | `PendingInvoiceReadModelService` | pending invoice routes | `PendingInvoiceReadModelRepositoryPort` | shared SQL methods behind port | pending invoice read model service/lifecycle | `pending-invoice` + `search-pending` compatibility | pending source summary + bank_detail/workbench_relation versions | L3 local support, L4 missing | direction/filter/month page scope | scope policy rejects bare month/global all | affected page scopes and mutation barrier targets | source-version regressions; production sample missing | page-first gateway force refresh | App Status target | mutation waits for pending_invoice targets | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `search` | Search index/API | partitioned scoped index | none | Search read API / `SearchQueryFreshnessService` | search API | `SearchReadModelRepositoryPort` | shared SQL methods behind port | `SearchReadModelRefreshProducer` | `search`, `search-secondary`, `search-tertiary`, `search-pending` compatibility | index source versions + dirty/outbox | L3 local support, L4 missing | search source month shard | search API fresh gate service | OA/import/worker fan-out routes through producer | local tests; production query plan missing | gateway force refresh | App Status target | search API must fail closed when SQL repo unavailable | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `invoice_lifecycle` | Invoice lifecycle shared read model | scoped incremental | none | `InvoiceLifecycleReadFacade` | lifecycle/page APIs | `InvoiceLifecycleReadModelRepositoryPort` | shared SQL methods behind port | `InvoiceLifecycleDerivedLifecycleExecutor` | `invoice-lifecycle`, `invoice-lifecycle-secondary` | lifecycle source versions + dirty/outbox | L3 local support, L4 missing | invoice lifecycle month shard | facade scoped reads | affected invoice subject month rebuild | local barrier regression; production sample missing | gateway force refresh | exact month App Status target | downstream pages must wait on lifecycle freshness | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `input_invoice_usage` | Input invoice usage | scoped incremental | none | `InputInvoiceUsageReadModelService` | input usage routes | `InputInvoiceUsageReadModelRepositoryPort` | shared SQL methods behind port | invoice usage collection refresh service | `invoice-usage-collection` | usage + workbench_relation source versions | L3 local support, L4 missing | month shard | SQL repository fail-closed path | affected month rows/detail rebuild and prune | local fail-closed tests; production sample missing | gateway force refresh | App Status target | frontend combined freshness must not fake fresh | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `output_invoice_collection` | Output invoice collection | scoped incremental | none | `OutputInvoiceCollectionService` | output collection routes | `OutputInvoiceCollectionReadModelRepositoryPort` | shared SQL methods behind port | invoice usage collection refresh service | `invoice-usage-collection` | output + relation/lifecycle/receipt source versions | L3 local support, L4 missing | month shard | SQL repository fail-closed path | affected month rows/detail/lifecycle overlay rebuild and prune | local fail-closed tests; production sample missing | gateway force refresh | App Status target | frontend combined freshness must not fake fresh | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `oa_pending_payment` | OA pending payments | scoped incremental | none | `OaPendingPaymentReadModelService` | OA pending payment routes | `OaPendingPaymentReadModelRepositoryPort` | shared SQL methods behind port | invoice usage collection refresh service | `invoice-usage-collection` | OA projection + workbench_relation source versions | L3 local support, L4 missing | month shard | concrete month preferred over fan-out all | affected month rows/detail rebuild and prune | local tests; production sample missing | gateway force refresh | App Status target | write-after-read barrier uses concrete month where available | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `cost_statistics` | Cost statistics | partitioned scoped parent rollup | queryable parent aggregate | `CostStatisticsQueryService` | cost routes | `CostStatisticsReadModelRepositoryPort` | shared SQL methods behind port | `CostStatisticsDerivedLifecycleExecutor` / refresh service | `cost-statistics`, `cost-tax` compatibility | gateway expected schema/source + shard/parent readiness | L3 local support, L4 missing | active/all month shards + parent rollup | parent scope waits for shards | month shard rebuild then parent aggregate publish | local bounded tests; production query plan missing | gateway force refresh with scope normalization | App Status target | page must not treat parent refreshing as fresh | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `tax_offset` | Tax offset | partitioned scoped incremental | none | `TaxOffsetQueryService` | tax routes | `TaxOffsetReadModelRepositoryPort` | shared SQL methods behind port | `TaxOffsetDerivedLifecycleExecutor` / worker executor | `tax-offset`, `cost-tax` compatibility | gateway expected schema/source + dirty/outbox | L3 local support, L4 missing | invoice month shard | gateway fresh gate | affected month rows/summary rebuild | local tests; production query plan missing | gateway force refresh | App Status target | page must show refreshing/stale through fresh gate | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `no_oa_bank_batch` | No-OA bank batches | scoped incremental | none | `NoOaBankBatchApplicationService` | no-OA routes | `NoOaBankBatchReadModelRepositoryPort` | shared SQL methods behind port | `NoOaBankBatchReadModelRefreshProducer` / derived executor | `no-oa-bank-batch` | no-OA source versions + readiness + dirty/outbox | L3 local support, L4 missing | month shard | list path uses port | affected no-OA month public rows and snapshot persistence | local FK/order regressions; production sample missing | gateway force refresh | App Status target | page must not treat non-fresh list as true empty | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |
| `turnover_ledger` | Turnover ledger | partitioned scoped incremental | none | `TurnoverLedgerQueryService` | turnover routes | `TurnoverLedgerReadModelRepositoryPort` | shared SQL methods behind port | `TurnoverLedgerReadModelRefreshProducer` | `turnover-ledger` | gateway expected schema/source + workbench_relation versions | L3 local support, L4 missing | month shard | grouped/list query preserves freshness metadata | affected grouped/list rows rebuild; clear via port | local metadata/source-version regressions; production sample missing | gateway force refresh | App Status target | grouped API must preserve read_model metadata | local support accounted, production evidence deferred | needs production App Status/worker/API/perf sample |

## Module Classification

- `local-implementation-closed-production-evidence-needed`: `bank_detail`, `bank_account_balance`, `pending_invoice`, `search`, `invoice_lifecycle`, `input_invoice_usage`, `output_invoice_collection`, `oa_pending_payment`, `cost_statistics`, `tax_offset`, `no_oa_bank_batch`, `turnover_ledger`.
- `needs-repository-physical-split`: all non-workbench read models still execute physical SQL through shared `postgres_repositories/read_models.py` even when a narrow port exists. Wave 1 starts by reconciling manifest ownership to the ports; later waves can split physical SQL files.
- `needs-query-fresh-gate-convergence`: no shared failure found in baseline tests; per-page production evidence still missing.
- `needs-worker-readiness-closure`: no shared registry gap found; production worker/readiness evidence missing.
- `needs-frontend-freshness-closure`: frontend production/browser evidence missing; combined invoice freshness is locally guarded.
- `closed`: none at PSCIP-L4 in this run.
- `blocked`: none for code-level progress.

## Legacy Pollution Inventory

- `server.py`: static guards are green for many extracted route/helper boundaries, but it remains a large assembly/compat surface. No new read model implementation should add server-owned query/refresh logic.
- `postgres_repositories/read_models.py`: remains the main physical SQL concentration. Narrow ports exist for non-workbench read models, but physical SQL is not fully split into per-read-model repository owners.
- Direct `ReadModelRefreshGateway` call sites: static guard classifies gateway-backed producers; no baseline failure found.
- Direct dirty/outbox SQL: platform guard passed; allowed owners remain `RuntimeQueueRepository`, transaction-equivalent repository writers and repair tooling.
- Legacy/local/live scan fallback: multiple local slices removed production fallback for specific pages; production smoke still required.
- Stale-as-fresh paths: shared query gateway and architecture guards passed; production/API evidence still missing.
- Frontend default fresh assumptions: operation barrier API test coverage exists; full browser evidence missing.

## High-Efficiency Wave Plan

1. Wave 1 - Global repository owner contract reconciliation:
   - Align manifest `repository_owner` with existing narrow read model repository ports for every non-workbench read model.
   - Add a manifest guard so only `workbench` can continue to declare shared `PostgresReadModelRepository.workbench` as the repository owner.
   - This is a contract/guard wave; it does not move physical SQL yet.
2. Wave 2 - Physical SQL owner split planning by family:
   - Split or isolate `postgres_repositories/read_models.py` methods by coherent read model families: invoice usage/OA, cost/tax/turnover, bank/search/no-OA, workbench/workbench_relation.
   - Preserve port APIs and tests.
3. Wave 3 - Production evidence tooling/runbook:
   - Add or tighten read-only production evidence commands for App Status, dirty/outbox/readiness and query latency without printing secrets.
4. Wave 4 - Per-family high-row performance proof:
   - Add local fake/contract query-bound tests where real `EXPLAIN` is unavailable; execute production sampling only through approved read-only runbook.

## Verification Performed

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
```

All commands passed before Wave 1 implementation.

## Seven Test Category Decision For Reconciliation

- Business core unit tests: not applicable; no business rule or amount/state behavior changed.
- Service-layer tests: applicable for later implementation waves; this reconciliation itself is analysis plus contract alignment.
- API contract tests: not applicable for this report; no HTTP shape changed.
- Read model/cache/background job tests: applicable; baseline manifest/gateway/barrier/worker/architecture tests were run.
- Frontend component/interaction tests: not applicable for this report; no frontend code changed.
- E2E business-flow tests: not applicable for this report; production/browser evidence remains a later L4 gate.
- Existing feature regression tests: applicable; baseline shared regression/architecture tests were run.

## Production Evidence Status

No PSCIP-L4 production evidence was collected in this reconciliation. The next production evidence sweep must be read-only by default and must not mutate production DB, queue, readiness, worker state, files, or secrets. If production access is unavailable, code-level PSCIP-L3 can continue, but L4 must remain `production-evidence-needed`.
