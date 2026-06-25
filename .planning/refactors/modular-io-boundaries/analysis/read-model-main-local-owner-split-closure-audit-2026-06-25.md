# Read Model Main Local Owner Split Closure Audit

Date: 2026-06-25

Branch: `main`

Controller: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`

## Result

Local physical SQL owner split is complete for all known non-Workbench App Status read models.

This is a local PSCIP-L3 owner-split closure, not PSCIP-L4 global closure. No production/server/DB access, secret access, production DB mutation, queue mutation, readiness mutation, worker replay, or production performance run occurred.

## Owner Matrix

| Read model | Repository port owner | Physical SQL owner | Local PSCIP status |
| --- | --- | --- | --- |
| `workbench` | `PostgresReadModelRepository.workbench` | `PostgresReadModelRepository` | Exception: active generation model |
| `workbench_relation` | `WorkbenchRelationReadModelRepositoryPort` | `PostgresSearchWorkbenchRelationReadModelRepository` | PSCIP-L3 local owner split |
| `bank_detail` | `BankDetailReadModelRepositoryPort` | `PostgresBankReadModelRepository` | PSCIP-L3 local owner split |
| `bank_account_balance` | `BankAccountBalanceReadModelRepositoryPort` | `PostgresBankReadModelRepository` | PSCIP-L3 local owner split |
| `pending_invoice` | `PendingInvoiceReadModelRepositoryPort` | `PostgresPendingInvoiceLifecycleReadModelRepository` | PSCIP-L3 local owner split |
| `search` | `SearchReadModelRepositoryPort` | `PostgresSearchWorkbenchRelationReadModelRepository` | PSCIP-L3 local owner split |
| `invoice_lifecycle` | `InvoiceLifecycleReadModelRepositoryPort` | `PostgresPendingInvoiceLifecycleReadModelRepository` | PSCIP-L3 local owner split |
| `input_invoice_usage` | `InputInvoiceUsageReadModelRepositoryPort` | `PostgresInvoiceUsageCollectionReadModelRepository` | PSCIP-L3 local owner split |
| `output_invoice_collection` | `OutputInvoiceCollectionReadModelRepositoryPort` | `PostgresInvoiceUsageCollectionReadModelRepository` | PSCIP-L3 local owner split |
| `oa_pending_payment` | `OaPendingPaymentReadModelRepositoryPort` | `PostgresInvoiceUsageCollectionReadModelRepository` | PSCIP-L3 local owner split |
| `cost_statistics` | `CostStatisticsReadModelRepositoryPort` | `PostgresSummaryReadModelRepository` | PSCIP-L3 local owner split |
| `tax_offset` | `TaxOffsetReadModelRepositoryPort` | `PostgresSummaryReadModelRepository` | PSCIP-L3 local owner split |
| `no_oa_bank_batch` | `NoOaBankBatchReadModelRepositoryPort` | `PostgresSummaryReadModelRepository` | PSCIP-L3 local owner split |
| `turnover_ledger` | `TurnoverLedgerReadModelRepositoryPort` | `PostgresSummaryReadModelRepository` | PSCIP-L3 local owner split |

## Shared Repository Residual Scan

AST/string scan of `PostgresReadModelRepository` found remaining `read_model.*` references only under Workbench-owned tables:

- `read_model.workbench_generations`
- `read_model.workbench_generation_stats`
- `read_model.workbench_snapshots`
- `read_model.workbench_summary`
- `read_model.workbench_rows`
- `read_model.workbench_groups`
- `read_model.workbench_group_rows`
- `read_model.workbench_candidate_matches`
- `read_model.workbench_reconciliation_decisions`
- SQL text fragment `read_model.refresh` inside a refresh-status helper name/string

No non-Workbench physical table reference remains in `PostgresReadModelRepository` compatibility methods after the owner split.

## Guard Coverage

`tests/test_read_model_manifest.py` guards the physical SQL owner split for:

- Invoice usage/collection/payment family.
- Pending invoice/invoice lifecycle family.
- Bank detail/balance family.
- Search/workbench relation family.
- Summary/residual family.

`tests/test_read_model_architecture_guards.py` classifies all direct `read_model_status = "fresh"` assignments after owner movement, including the turnover ledger fresh literal now owned by `PostgresSummaryReadModelRepository`.

## Verification

Commands run:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m pytest tests/test_cost_statistics_sql_runtime.py tests/test_tax_offset_sql_runtime.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_turnover_ledger_read_model_refresh.py tests/test_turnover_ledger_read_facade.py -q
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
bash scripts/verify.sh docs
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
git diff --check
```

Results:

- Manifest/registry: 41 tests passed.
- Summary/residual runtime/facade tests: 57 tests passed.
- Architecture/platform boundary guards: 174 tests passed.
- Docs verification passed.
- App `--check` returned `status: ready`.
- Diff whitespace check passed.

## Remaining Gate

PSCIP-L4 remains unclaimed. The next boundary must collect production or equivalent runtime evidence for freshness and performance, or explicitly stop for server/DB access.

Minimum evidence still required:

- Readiness/status evidence for all App Status read models.
- Queue/dirty-scope convergence evidence from PostgreSQL durable queue facts.
- API or browser smoke proving page payloads are fresh or correctly refreshing/stale, never stale-as-fresh.
- Performance evidence for hot pages and high-row queries, especially Workbench active generation, search, bank detail, no-OA bank batch, turnover ledger, cost statistics, and tax offset.
