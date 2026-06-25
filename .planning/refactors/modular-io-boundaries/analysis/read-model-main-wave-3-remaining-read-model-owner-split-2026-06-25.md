# Read Model Main Closure Wave 3 Remaining Owner Split

Date: 2026-06-25

Branch: `main`

Controller: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`

## Scope Completed In This Wave So Far

Wave 3 first subwave completed the bank read model physical SQL owner split:

- `bank_detail`
- `bank_account_balance`

The public narrow ports remain unchanged:

- `BankDetailReadModelRepositoryPort`
- `BankAccountBalanceReadModelRepositoryPort`

`PostgresReadModelRepository` keeps compatibility methods for existing port contracts, but those methods delegate to `PostgresBankReadModelRepository`. The new owner contains bank detail scope summaries, account/transaction list reads, tagged row lookups, bank account balance reads, bank detail writes, bank account balance writes, and bank detail scope marking.

## PSCIP Movement

Before this wave, `bank_detail` and `bank_account_balance` were already partitioned/scoped/incremental at the manifest, policy, queue, and runtime behavior level, but physical SQL ownership still lived in the shared `PostgresReadModelRepository`.

After this subwave:

- `bank_detail` moves from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- `bank_account_balance` moves from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
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

## Verification

Commands run:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m pytest tests/test_bank_details_sql_runtime.py tests/test_bank_account_balance_read_model.py -q
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
```

Results:

- `tests.test_read_model_manifest tests.test_runtime_worker_registry`: passed.
- `tests/test_bank_details_sql_runtime.py tests/test_bank_account_balance_read_model.py`: 61 passed.
- `tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards`: passed.

## Remaining

Remaining non-Workbench physical SQL owner split candidates:

- `search`
- `workbench_relation`
- `cost_statistics`
- `tax_offset`
- `no_oa_bank_batch`
- `turnover_ledger`

Workbench itself remains the active-generation exception and is not mechanically converted.

No server SSH, production DB, production queue, readiness flag, worker replay, or secret access was used in this wave.
