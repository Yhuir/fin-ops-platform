# Next Prompt

Continue after `production:read-model-focused-user-scope-api-metadata-resmoke-runbook`.

## Current State

- Branch: `dev`.
- Row280 reused the Row273 in-process target OA applicant credential seam without printing or storing credentials/tokens.
- Focused user-scope API metadata re-smoke results:
  - `pending_invoices_rows`: pass, HTTP `200`, `read_model_status=fresh`, `refresh_enqueued_count=0`, p95 `660.208ms`.
  - `pending_invoices_filter_options`: pass, HTTP `200`, `read_model_status=fresh`, `refresh_enqueued_count=0`, p95 `129.211ms`.
  - `no_oa_bank_batches`: fail, HTTP `200`, `read_model_status=stale`, `refresh_enqueued_count=1`, p95 `143.406ms`.
- Row280 obeyed the stop gate and did not run full non-admin user-scope probes because the focused set failed.
- Row280 postcheck:
  - `/health/ready`: ready.
  - dirty scopes: all `done`.
  - readiness: all `fresh`.
  - read-model outbox: all `done`.
  - read-model dead letters: none.
  - recent no-OA dirty/outbox from the GET-triggered refresh: `done`.
- Row278 previously proved the bounded no-OA row category snapshot matched the deployed expected category snapshot and `source_version_mismatch_reasons` was empty against the safely reconstructed base contract.
- Module/global closure remains open.

## Next Boundary

`production:no-oa-bank-batches-api-stale-read-only-diagnosis`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Acquire the direct-dev write lease before editing:
   - `mkdir /tmp/fin-ops-dev-write.lock`
4. Read:
   - `analysis/production-read-model-focused-user-scope-api-metadata-resmoke-runbook-2026-06-25.md`
   - `analysis/production-no-oa-bank-batch-category-source-version-mismatch-diagnosis-2026-06-25.md`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
5. Write a read-only diagnosis runbook/evidence file under `analysis/` before any production command.

## Diagnosis Scope

Diagnose why user-scope `GET /api/no-oa-bank-batches?month=2026-06&bucket=unsubmitted&page=1&page_size=200` still reports `read_model_status=stale` after:

- Row278 showed category source-version parity for the bounded row set;
- Row280's GET-triggered no-OA refresh converged to done;
- App Status readiness remains fresh and dirty/outbox/dead-letter aggregates are clean.

The diagnosis should be read-only first and should avoid production API calls. It should compare deployed API expected source versions against bounded row source versions, including optional downstream keys if the deployed request path can include them, and inspect the freshness/status/dirty/outbox/readiness metadata needed to classify the stale reason.

## Stop Gates

- Do not call production API endpoints in the diagnosis boundary.
- Do not print payload rows, batch ids, transaction ids, account names, counterparties, tokens, cookies, passwords, DSNs, env secret values or private keys.
- Do not enqueue/requeue/refresh/repair/rebuild/replay/deploy/restart/manually mark readiness/directly mutate DB rows.
- Stop if exact expected source-version construction would require broad `Application` startup or guessing unknown contracts.
- Do not claim module/global closure from this diagnosis alone.
