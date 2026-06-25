# Read Model Main Closure Wave 3 Remaining Owner Split

Date: 2026-06-25

Branch: `main`

Controller: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`

## Scope Completed In This Wave So Far

Wave 3 first subwave completed the bank read model physical SQL owner split:

- `bank_detail`
- `bank_account_balance`

Wave 3 second subwave completed the search/workbench relation physical SQL owner split:

- `search`
- `workbench_relation`

Wave 3 third subwave completed the summary/residual read model physical SQL owner split:

- `cost_statistics`
- `tax_offset`
- `no_oa_bank_batch`
- `turnover_ledger`

The public narrow ports remain unchanged:

- `BankDetailReadModelRepositoryPort`
- `BankAccountBalanceReadModelRepositoryPort`
- `SearchReadModelRepositoryPort`
- `WorkbenchRelationReadModelRepositoryPort`
- `CostStatisticsReadModelRepositoryPort`
- `TaxOffsetReadModelRepositoryPort`
- `NoOaBankBatchReadModelRepositoryPort`
- `TurnoverLedgerReadModelRepositoryPort`

`PostgresReadModelRepository` keeps compatibility methods for existing port contracts, but those methods delegate to family-specific owners. `PostgresBankReadModelRepository` contains bank detail scope summaries, account/transaction list reads, tagged row lookups, bank account balance reads, bank detail writes, bank account balance writes, and bank detail scope marking. `PostgresSearchWorkbenchRelationReadModelRepository` contains search index reads/writes and workbench relation distribution rows/groups/scopes reads, writes, freshness checks, source-version reads, and empty-scope marking. `PostgresSummaryReadModelRepository` contains cost statistics, tax offset, no-OA bank batch, and turnover ledger read/write SQL plus their local row/item snapshot helpers.

## PSCIP Movement

Before this wave, `bank_detail` and `bank_account_balance` were already partitioned/scoped/incremental at the manifest, policy, queue, and runtime behavior level, but physical SQL ownership still lived in the shared `PostgresReadModelRepository`.

After this subwave:

- `bank_detail` moves from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- `bank_account_balance` moves from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- `search` moves from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- `workbench_relation` moves from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- `cost_statistics` moves from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- `tax_offset` moves from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- `no_oa_bank_batch` moves from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- `turnover_ledger` moves from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- No broad `all` fake-fresh path was introduced.
- No Redis or RabbitMQ freshness source was introduced.
- No dirty scope/outbox ownership changed.
- No PSCIP-L4 closure is claimed because no production or equivalent runtime evidence was collected.

## Guard Added

`tests/test_read_model_manifest.py` now includes `test_bank_read_model_physical_sql_owner_is_split_from_shared_repository`.

The guard proves:

- Bank detail and bank account balance methods exist on `PostgresBankReadModelRepository`.
- `PostgresReadModelRepository` compatibility methods delegate through `_bank_read_model_repository`.
- The shared compatibility methods do not directly reference:
  - `read_model.bank_detail_rows`
  - `read_model.bank_detail_scopes`
  - `read_model.bank_account_balances`

`tests/test_read_model_architecture_guards.py` was updated so direct fresh-status classification follows `PostgresBankReadModelRepository.get_bank_detail_tagged_rows_by_transaction_ids`.

`tests/test_read_model_manifest.py` now also includes `test_search_workbench_relation_physical_sql_owner_is_split_from_shared_repository`.

That guard proves:

- Search and workbench relation methods exist on `PostgresSearchWorkbenchRelationReadModelRepository`.
- `PostgresReadModelRepository` compatibility methods delegate through `_search_workbench_relation_repository`.
- The shared compatibility methods do not directly reference:
  - `read_model.search_index_rows`
  - `read_model.workbench_relation_rows`
  - `read_model.workbench_relation_groups`
  - `read_model.workbench_relation_scopes`

`tests/test_read_model_architecture_guards.py` was further updated so direct fresh-status classification follows:

- `PostgresSearchWorkbenchRelationReadModelRepository.get_workbench_relation_rows_by_ids`
- `PostgresSearchWorkbenchRelationReadModelRepository.get_workbench_relation_groups_by_ids`
- `PostgresSummaryReadModelRepository.list_turnover_ledger_view`

`tests/test_read_model_manifest.py` now also includes `test_summary_read_model_physical_sql_owner_is_split_from_shared_repository`.

That guard proves:

- Summary/residual methods exist on `PostgresSummaryReadModelRepository`.
- `PostgresReadModelRepository` compatibility methods delegate through `_summary_read_model_repository`.
- The shared compatibility methods do not directly reference:
  - `read_model.cost_statistics_read_models`
  - `read_model.cost_statistics_rows`
  - `read_model.tax_offset_read_models`
  - `read_model.tax_offset_items`
  - `read_model.no_oa_bank_batch_rows`
  - `read_model.turnover_ledger_rows`

## Verification

Commands run:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m pytest tests/test_bank_details_sql_runtime.py tests/test_bank_account_balance_read_model.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py tests/test_workbench_relation_read_facade.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_cost_statistics_sql_runtime.py tests/test_tax_offset_sql_runtime.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_turnover_ledger_read_model_refresh.py tests/test_turnover_ledger_read_facade.py -q
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
```

Results:

- `tests.test_read_model_manifest tests.test_runtime_worker_registry`: passed.
- `tests/test_bank_details_sql_runtime.py tests/test_bank_account_balance_read_model.py`: 61 passed.
- `tests/test_search_pending_sql_runtime.py tests/test_workbench_relation_read_facade.py`: 74 passed.
- `tests/test_cost_statistics_sql_runtime.py tests/test_tax_offset_sql_runtime.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_turnover_ledger_read_model_refresh.py tests/test_turnover_ledger_read_facade.py`: 57 passed.
- `tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards`: passed.

## Remaining

No known non-Workbench physical SQL owner split candidates remain in this wave.

Workbench itself remains the active-generation exception and is not mechanically converted.

No server SSH, production DB, production queue, readiness flag, worker replay, or secret access was used in this wave.
