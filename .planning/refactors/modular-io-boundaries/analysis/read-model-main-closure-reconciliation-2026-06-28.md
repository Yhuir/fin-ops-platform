# Read Model Main Closure Reconciliation - 2026-06-28

## Run Context

- Branch: `main`
- Current commit at reconciliation start: `5eb09bb9`
- Backup branch: `codex/backup-main-before-read-model-closure-20260628-190532`
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
- Scope: complete read model modularization closure, preserving read models as PSCIP systems. This is not the Direct API removal track.
- Production mutation status: none in this reconciliation. No production DB write, queue mutation, readiness mutation, worker replay, service restart, deploy or secret print occurred.

## Evidence Read

- Required docs: `AGENTS.md`, `docs/modules/read-models/README.md`, `docs/modules/read-models/state-machine.md`, `docs/modules/read-models/tests.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/architecture/module-boundaries/inventory.md`, existing `read-model-main-*` analysis files and `autonomous/JOURNAL.md`.
- CodeGraph: index healthy with 1065 indexed files, 36644 nodes and 95747 edges. `ReadModelRefreshGateway`, `ReadModelScopePolicy` and `ReadModelFreshness` remain the shared architecture entry points.
- CodeGraph trace note: `ReadModelRefreshGateway.enqueue_many -> RuntimeQueueRepository.enqueue_read_model_refresh` crosses dynamic dispatch, so static trace alone is insufficient. Current proof must remain tests + guards + runtime evidence.
- Current local tests:
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v` passed, 41 tests.
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_query_gateway tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier -v` passed, 39 tests.
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v` passed, 174 tests.

## Global Finding

Current `main` already contains the previously recorded local owner-split waves. The current code is materially ahead of the initial 2026-06-25 reconciliation:

- `READ_MODEL_MANIFEST` covers 14 App Status read models.
- Manifest keys match `ReadModelScopePolicyRegistry` registered scope types.
- Manifest/App Status/worker/RabbitMQ/scope-policy guard tests pass.
- Every non-Workbench read model declares a narrow repository port owner in manifest.
- Current physical SQL owner split classes exist in `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`:
  - `PostgresInvoiceUsageCollectionReadModelRepository`
  - `PostgresPendingInvoiceLifecycleReadModelRepository`
  - `PostgresBankReadModelRepository`
  - `PostgresSearchWorkbenchRelationReadModelRepository`
  - `PostgresSummaryReadModelRepository`
- `PostgresReadModelRepository` remains as compatibility/delegation surface plus Workbench active-generation exception owner.
- Shared stale-as-fresh gates are locally guarded by query gateway, refresh gateway, operation barrier and architecture tests.

The remaining global closure gap is PSCIP-L4 production or equivalent runtime evidence. Local PSCIP-L3 support is proved for the known non-Workbench read models by current code/tests, but L4 is not proven until production/current-code runtime evidence is collected.

## Closure Matrix

| key | page/domain | strategy | exception | query owner | repository port owner | physical SQL owner | worker owner | freshness proof | PSCIP level | production evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `workbench` | Reconciliation workbench | active generation scoped publish | active generation exception | `WorkbenchQueryFacade` | `PostgresReadModelRepository.workbench` | `PostgresReadModelRepository` active-generation surfaces | `workbench` | active generation metadata + source versions + dirty/outbox | L3-equivalent local, L4 missing | needed |
| `workbench_relation` | Relation distribution | scoped incremental distribution | none | `WorkbenchRelationReadFacade` | `WorkbenchRelationReadModelRepositoryPort` | `PostgresSearchWorkbenchRelationReadModelRepository` | `workbench-relation` | scope source versions + readiness + dirty/outbox | L3 local, L4 missing | needed |
| `bank_detail` | Bank Details | partitioned scoped incremental | none | `BankDetailsApplicationService` | `BankDetailReadModelRepositoryPort` | `PostgresBankReadModelRepository` | `bank-detail` | month source summary + dirty/outbox | L3 local, L4 missing | needed |
| `bank_account_balance` | Bank accounts/balance | all-only scoped projection | all-only exception | `BankDetailsApplicationService` | `BankAccountBalanceReadModelRepositoryPort` | `PostgresBankReadModelRepository` | `bank-account-balance` | `bank_account_balance:all` readiness + dirty/outbox | L3 local, L4 missing | needed |
| `pending_invoice` | Pending invoices | page-first scoped incremental | bare `all` forbidden | `PendingInvoiceReadModelService` | `PendingInvoiceReadModelRepositoryPort` | `PostgresPendingInvoiceLifecycleReadModelRepository` | `pending-invoice` + compat `search-pending` | pending source + bank/relation versions | L3 local, L4 missing | needed |
| `search` | Search index/API | partitioned scoped index | none | Search API / `SearchQueryFreshnessService` | `SearchReadModelRepositoryPort` | `PostgresSearchWorkbenchRelationReadModelRepository` | `search` + secondary lanes | index source versions + dirty/outbox | L3 local, L4 missing | needed |
| `invoice_lifecycle` | Invoice lifecycle | scoped incremental | none | `InvoiceLifecycleReadFacade` | `InvoiceLifecycleReadModelRepositoryPort` | `PostgresPendingInvoiceLifecycleReadModelRepository` | `invoice-lifecycle` + secondary lane | lifecycle source versions + dirty/outbox | L3 local, L4 missing | needed |
| `input_invoice_usage` | Input invoice usage | scoped incremental | none | `InputInvoiceUsageReadModelService` | `InputInvoiceUsageReadModelRepositoryPort` | `PostgresInvoiceUsageCollectionReadModelRepository` | `invoice-usage-collection` | usage + relation source versions | L3 local, L4 missing | needed |
| `output_invoice_collection` | Output invoice collection | scoped incremental | none | `OutputInvoiceCollectionService` | `OutputInvoiceCollectionReadModelRepositoryPort` | `PostgresInvoiceUsageCollectionReadModelRepository` | `invoice-usage-collection` | output + relation/lifecycle/receipt versions | L3 local, L4 missing | needed |
| `oa_pending_payment` | OA pending payments | scoped incremental | none | `OaPendingPaymentReadModelService` | `OaPendingPaymentReadModelRepositoryPort` | `PostgresInvoiceUsageCollectionReadModelRepository` | `invoice-usage-collection` | OA projection + relation versions | L3 local, L4 missing | needed |
| `cost_statistics` | Cost statistics | partitioned scoped parent rollup | queryable parent aggregate | `CostStatisticsQueryService` | `CostStatisticsReadModelRepositoryPort` | `PostgresSummaryReadModelRepository` | `cost-statistics` + compat `cost-tax` | expected schema/source + shard/parent readiness | L3 local, L4 missing | needed |
| `tax_offset` | Tax offset | partitioned scoped incremental | none | `TaxOffsetQueryService` | `TaxOffsetReadModelRepositoryPort` | `PostgresSummaryReadModelRepository` | `tax-offset` + compat `cost-tax` | expected schema/source + dirty/outbox | L3 local, L4 missing | needed |
| `no_oa_bank_batch` | No-OA bank batches | scoped incremental | none | `NoOaBankBatchApplicationService` | `NoOaBankBatchReadModelRepositoryPort` | `PostgresSummaryReadModelRepository` | `no-oa-bank-batch` | no-OA source versions + readiness + dirty/outbox | L3 local, L4 missing | needed |
| `turnover_ledger` | Turnover ledger | partitioned scoped incremental | none | `TurnoverLedgerQueryService` | `TurnoverLedgerReadModelRepositoryPort` | `PostgresSummaryReadModelRepository` | `turnover-ledger` | expected schema/source + relation versions | L3 local, L4 missing | needed |

## Classification

- `local-implementation-closed-production-evidence-needed`: all 14 read models.
- `needs-repository-physical-split`: none currently known for non-Workbench read models. Workbench remains the explicit active-generation exception.
- `needs-refresh-producer-convergence`: no global shared gap found by current guard tests.
- `needs-query-fresh-gate-convergence`: no global shared gap found by query gateway and architecture tests.
- `needs-operation-barrier-closure`: no global shared gap found by operation barrier tests.
- `needs-frontend-freshness-closure`: no current-code global proof gap found locally, but production/browser evidence is still missing.
- `needs-worker-readiness-closure`: no registry gap found locally, but production worker/readiness evidence is missing.
- `needs-legacy-removal`: no unclassified global read model pollution found by current guards; `server.py` and shared repository remain compatibility surfaces only.
- `closed`: none at PSCIP-L4.
- `blocked`: none for local code progress; L4 remains evidence-gated.

## Shared Pollution Inventory

- `server.py`: remains large assembly/compat surface. Current architecture guards pass; no new read-model owner should be added here.
- `postgres_repositories/read_models.py`: still one file, but physical SQL ownership is split into family-specific classes. `PostgresReadModelRepository` is compatibility/delegation plus Workbench exception surface.
- Direct `ReadModelRefreshGateway` call sites: allowed producer/service/tooling surfaces are guard-classified.
- Direct dirty/outbox SQL: platform guard passes; durable queue owners remain the allowed write boundary.
- Legacy/local/live scan fallback: production SQL runtime guards and fail-closed tests exist for key pages; production evidence still required.
- Stale-as-fresh paths: current shared tests pass. Production API smoke is still required before L4.
- Frontend default fresh assumptions: local operation-barrier and page guards exist; production/browser evidence still required.

## Macro-Wave Plan From Current State

1. Wave 1, production evidence sweep:
   - Collect deployed commit, health/ready, App Status read model scopes, dirty/outbox blockers, readiness rows, worker status/logs and read-only page API smoke.
   - Use root SSH when needed; do not print secrets.
   - Use admin token only through a secure prompt if admin HTTP probes are required.
2. Wave 2, evidence-driven local fixes:
   - If production/current-code evidence exposes stale-as-fresh, missing readiness, worker drift, source-version mismatch or hot-path scan risk, fix the shared owner once and rerun grouped tests.
3. Wave 3, final closure report:
   - Record PSCIP-L4 evidence per read model or mark exact deferred/hard-stop items.

## Seven Test Category Decision

- Business core unit tests: not changed in this reconciliation; existing read-model source/scope tests remain relevant.
- Service-layer tests: applicable and run through query/refresh/barrier/architecture suites.
- API contract tests: production/API smoke still required for L4; no HTTP shape changed locally.
- Read model/cache/background job tests: applicable and run through manifest, worker registry, query gateway, refresh gateway and barrier suites.
- Frontend component/interaction tests: no frontend code changed; production/browser evidence still needed for L4.
- End-to-end business-flow integration tests: no mutating E2E run yet; production write/apply evidence remains gated.
- Existing feature regression tests: applicable and run through platform/read-model architecture guards.

## Current Decision

Proceed directly to production or equivalent runtime evidence. Additional local code changes before production evidence would be speculative unless the evidence sweep finds a real gap.
