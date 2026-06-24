# Next Prompt

Continue after `production:no-oa-bank-batches-focused-api-freshness-recheck`.

## Current State

- Branch: `dev`.
- Row282 reused the Row280 in-process target OA applicant credential seam without printing/storing credentials or tokens.
- Row282 ran only the focused `no_oa_bank_batches` API metadata probe.
- Row282 precheck:
  - Active release: `dev-pending-invoice-source-17d13466-20260625`.
  - `/health/ready`: ready.
  - dirty scopes: `done=187055`.
  - readiness: `fresh=498`.
  - read-model outbox: `done=202950`.
  - read-model dead letters: none.
- Row282 focused probe:
  - configured target credential count: `2`.
  - session: `allowed=true`, `can_access_app=true`, `can_mutate_data=true`, `can_admin_access=false`, `access_tier=full_access`.
  - `no_oa_bank_batches`: HTTP `200`, p95 `165.274ms`, `read_model_status=stale`, `refresh_enqueued_count=1`.
  - focused report status: `fail`.
  - full user-scope, browser, admin and write probes were not run.
- Row282 postcheck:
  - `/health/ready`: ready.
  - dirty scopes: `done=187056`.
  - readiness: `fresh=498`.
  - read-model outbox: `done=202951`.
  - recent no-OA outbox last hour: `done=2`, latest `2026-06-25 06:29:53.777793+08`.
  - recent no-OA dirty last hour: `all/done=2`, latest `2026-06-25 06:29:53.771578+08`.
  - read-model dead letters: none.
- Row281 still matters: a fresh deployed-code process proved current persisted no-OA rows match both exact base expected and optional downstream expected source-version contracts. Therefore repeating refresh is not justified until the API process's actual stale reasons are known.
- Module/global closure remains open.

## Next Boundary

`production:no-oa-bank-batches-api-stale-reasons-sanitized-probe`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev`.
3. Acquire the direct-dev write lease before editing:
   - `mkdir /tmp/fin-ops-dev-write.lock`
4. Read:
   - `analysis/production-no-oa-bank-batches-focused-api-freshness-recheck-2026-06-25.md`
   - `analysis/production-no-oa-bank-batches-api-stale-read-only-diagnosis-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
5. Write a bounded runbook/evidence file under `analysis/` before any production API command.

## Probe Scope

Collect only sanitized API freshness metadata from the authenticated user-scope no-OA list response:

- `http_status`
- `read_model_status`
- `read_model_stale_reasons`
- `refresh_enqueued`
- elapsed timing
- session access metadata
- postcheck dirty/outbox/readiness/dead-letter aggregates

The command must discard and never print:

- `summary`
- `batches`
- pagination row payloads
- batch IDs
- transaction IDs
- account names
- counterparties
- credentials/tokens/cookies/passwords/env values
- full response bodies

## Stop Gates

- Stop if `/health/ready` is unavailable or not ready.
- Stop if no safe target OA applicant auth path is available without printing/storing secrets.
- Stop after sanitized stale reasons are collected; do not retry blindly.
- If the GET fresh gate enqueues refresh, run postcheck and ensure convergence.
- Do not run full user-scope/browser/admin/write probes.
- Do not manually refresh/rebuild/repair/requeue/replay/deploy/restart or mutate DB/readiness/queue state.
- Do not claim module/global closure from this stale-reasons probe alone.
