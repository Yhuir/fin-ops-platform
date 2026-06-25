# Next Prompt

Continue the user-authorized `main-read-model-closure` run.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260625-230543`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest completed wave: `main-read-model-closure:wave-3-remaining-read-model-owner-split:bank-read-models`.
- Reconciliation file: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-25.md`.
- Wave 1 aligned non-Workbench manifest `repository_owner` values to existing narrow read model repository ports and added a manifest guard.
- Wave 2 split physical SQL ownership for the invoice-family read models:
  - `input_invoice_usage`, `output_invoice_collection`, and `oa_pending_payment` into `PostgresInvoiceUsageCollectionReadModelRepository`.
  - `pending_invoice` and `invoice_lifecycle` into `PostgresPendingInvoiceLifecycleReadModelRepository`.
- Wave 2 analysis file: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-2-physical-sql-owner-split-2026-06-25.md`.
- Wave 3 first subwave split physical SQL ownership for `bank_detail` and `bank_account_balance` into `PostgresBankReadModelRepository`.
- Wave 3 analysis file: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-3-remaining-read-model-owner-split-2026-06-25.md`.
- No production/server/DB access was used. No secret, production DB mutation, queue mutation, readiness mutation or worker replay occurred.
- No PSCIP-L4 global closure is claimed.

## Required First Steps On Resume

1. Confirm `git status --short --branch`; stop if unrelated dirty files would be committed.
2. Confirm `main` is fast-forward synced with `origin/main`.
3. Read:
   - `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-25.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - `backend/src/fin_ops_platform/services/postgres_state_store.py`
   - relevant `*_read_model_repository.py` ports for the selected family
   - relevant module tests for the selected family
4. Use CodeGraph before editing:
   - `codegraph_status`
   - `codegraph_context` for the selected physical SQL family
   - `codegraph_impact` for any shared repository method before changing it

## Next Boundary

`main-read-model-closure:wave-3-remaining-read-model-owner-split:search-workbench-relation`

Recommended next family: search + workbench relation.

Scope:
- `search`
- `workbench_relation`

Deferred after this family:
- `cost_statistics`
- `tax_offset`
- `no_oa_bank_batch`
- `turnover_ledger`

Goal:
- Move from “narrow port wrapping broad `PostgresReadModelRepository` methods” toward clearer physical SQL ownership without changing API behavior.
- Prefer a coherent extraction pattern that keeps public port APIs stable.
- Do not split every method one-by-one if a family-level owner can be extracted safely with tests.
- Preserve the already-completed invoice-family owner split:
  - `PostgresInvoiceUsageCollectionReadModelRepository`
  - `PostgresPendingInvoiceLifecycleReadModelRepository`
  - `PostgresBankReadModelRepository`

Acceptance:
- No API response shape change unless explicitly tested.
- No stale-as-fresh path introduced.
- No new direct dirty/outbox SQL outside allowed owners.
- No broad `all` fake fresh.
- No Redis/RabbitMQ freshness truth.
- Do not implement Go, Go Fiber or Go Worker.
- Existing repository port tests remain green.
- Add or update at least one guard proving the selected family no longer treats shared `PostgresReadModelRepository` as its physical owner once extracted.
- Update `analysis/read-model-main-wave-3-remaining-read-model-owner-split-2026-06-25.md` with search/workbench-relation PSCIP movement.
- Update this `NEXT-PROMPT.md` at the end of the wave.

Suggested verification:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py tests/test_invoice_lifecycle_read_model_refresh.py tests/test_invoice_lifecycle_read_facade.py tests/test_invoice_lifecycle_page_integration.py tests/test_invoice_usage_collection_sql_runtime.py tests/test_oa_pending_payment_api.py -q
bash scripts/verify.sh docs
git diff --check
```

Do not claim PSCIP-L4 without production or equivalent runtime evidence.
