# Next Prompt

Continue the user-authorized `main-read-model-closure` run.

## Current State

- Branch: `main`.
- Backup branch: `codex/backup-main-before-read-model-closure-20260625-230543`.
- Controller prompt: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`.
- Latest completed wave: `main-read-model-closure:wave-3-remaining-read-model-owner-split:summary-read-models`.
- Reconciliation file: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-25.md`.
- Wave 1 aligned non-Workbench manifest `repository_owner` values to existing narrow read model repository ports and added a manifest guard.
- Wave 2 split physical SQL ownership for:
  - `input_invoice_usage`, `output_invoice_collection`, and `oa_pending_payment` into `PostgresInvoiceUsageCollectionReadModelRepository`.
  - `pending_invoice` and `invoice_lifecycle` into `PostgresPendingInvoiceLifecycleReadModelRepository`.
- Wave 3 split physical SQL ownership for:
  - `bank_detail` and `bank_account_balance` into `PostgresBankReadModelRepository`.
  - `search` and `workbench_relation` into `PostgresSearchWorkbenchRelationReadModelRepository`.
  - `cost_statistics`, `tax_offset`, `no_oa_bank_batch`, and `turnover_ledger` into `PostgresSummaryReadModelRepository`.
- Wave 3 analysis file: `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-3-remaining-read-model-owner-split-2026-06-25.md`.
- Workbench remains the documented active-generation exception and must not be mechanically converted.
- No production/server/DB access was used. No secret, production DB mutation, queue mutation, readiness mutation or worker replay occurred.
- No PSCIP-L4 global closure is claimed.

## Required First Steps On Resume

1. Confirm `git status --short --branch`; stop if unrelated dirty files would be committed.
2. Confirm `main` is fast-forward synced with `origin/main`.
3. Read:
   - `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-closure-reconciliation-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-main-wave-3-remaining-read-model-owner-split-2026-06-25.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - `tests/test_read_model_manifest.py`
   - `tests/test_read_model_architecture_guards.py`
4. Use CodeGraph before editing:
   - `codegraph_status`
   - `codegraph_context` for the selected closure/evidence boundary

## Next Boundary

`main-read-model-closure:local-owner-split-closure-audit-and-production-evidence-gate`

Goal:
- Audit whether all non-Workbench read models now have explicit partition, scope, incremental projection, manifest, policy, worker, queue, repository-port, and physical SQL owner contracts.
- Produce an updated local closure matrix with exact PSCIP level per read model.
- Identify any remaining old-code contamination paths that still bypass read model freshness/status/enqueue boundaries.
- Decide whether the next step is local code cleanup, targeted production/equivalent evidence collection, or a hard stop waiting for server access.

Acceptance:
- Do not claim PSCIP-L4 unless production or equivalent runtime evidence proves freshness and performance.
- No production mutation, queue mutation, readiness mutation, or worker replay without an explicit runbook and approval.
- If no further local code changes are required, write an analysis record explaining that local PSCIP-L3 owner split is complete and L4 is blocked only on production/equivalent evidence.
- If local contamination remains, fix it with tests before moving to production evidence.
- Update this `NEXT-PROMPT.md` at the end of the boundary.

Suggested verification:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py tests/test_workbench_relation_read_facade.py tests/test_cost_statistics_sql_runtime.py tests/test_tax_offset_sql_runtime.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_turnover_ledger_read_model_refresh.py tests/test_turnover_ledger_read_facade.py -q
bash scripts/verify.sh docs
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
git diff --check
```

Do not claim global closure without production/equivalent freshness and performance evidence.
