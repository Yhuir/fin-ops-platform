# Next Prompt

Continue after `production:pending-invoice-source-version-contract-deploy-and-convergence-runbook`.

## Current State

- Branch: `dev`.
- Row276 fixed pending invoice source-version contract alignment locally.
- Row277 deployed release `dev-pending-invoice-source-17d13466-20260625` at git commit `3329d8954a7219a1c21641392aaa3f5448ec20f5`.
- Row277 production evidence:
  - `/health/ready` was ready before and after deploy.
  - One bounded `pending_invoice=expense:all` smoke event reached `event_status=done` and `dirty_status=done`.
  - The smoke tool returned timeout only because the explicit override scope had no App Status readiness row; this is a smoke-tool evidence gap, not a worker failure.
  - A no-enqueue sanitized metadata probe proved pending invoice rows/filter-options for `expense:all` are `fresh`.
  - Pending invoice source-version stale reasons are empty.
  - Actual source-version keys include `invoice_lifecycle_policy_schema_version`, `bank_detail_source_versions` and `workbench_relation_source_versions`.
  - Selected pending invoice dirty scopes/outbox are `done`; pending invoice readiness is `fresh`.
- Pending invoice production convergence is closed for Row277.
- Module/global closure remains open.
- no-OA `bank_transaction_category_snapshot_version_mismatch` remains the next open production source-version issue from Row275.

## Next Boundary

`production:no-oa-bank-batch-category-source-version-mismatch-diagnosis`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Acquire the direct-dev write lease before editing:
   - `mkdir /tmp/fin-ops-dev-write.lock`
4. Read:
   - `analysis/production-pending-invoice-source-version-contract-deploy-and-convergence-runbook-2026-06-25.md`
   - `analysis/production-pending-invoice-no-oa-source-version-contract-deep-diagnosis-2026-06-25.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
   - `docs/operations/runtime-worker-governance.md`
5. Write a read-only diagnosis/runbook file under `analysis/` before any production command.

## Diagnosis Scope

- Use root SSH controlled production evidence, but keep the first boundary read-only.
- Reconstruct expected no-OA source versions without broad `Application` startup when possible.
- Inspect only metadata needed for `bank_transaction_category_snapshot_version_mismatch`:
  - expected category snapshot/source version;
  - actual no-OA row source-version hashes/key sets for bounded month/bucket samples;
  - current dirty/outbox/readiness/dead-letter status for no-OA and bank transaction category related scopes;
  - whether a normal gateway-backed no-OA refresh would update the stale row source versions;
  - whether a local code-contract mismatch exists before any production rebuild is trusted.
- Do not print payload rows, business identifiers, counterparties, account names, tokens, cookies, DSNs or env secret values.
- Do not mutate production in this boundary.

## Stop Gates

- Any command would print secrets, tokens, cookies, DSNs, passwords, private keys or business payload rows.
- Exact source-version contract cannot be derived from code/docs/tests without guessing.
- Diagnosis would require broad DB mutation, no-OA rebuild, requeue, repair, manual mark-done, readiness mutation or worker replay.
- The mismatch cannot be scoped to a bounded no-OA/category source-version contract.
- Do not broaden back into pending invoice; Row277 already closed pending invoice production convergence for this slice.
- Do not claim module/global closure from no-OA diagnosis alone.
