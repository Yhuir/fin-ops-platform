# Production No-OA Bank Batches API Stale Reasons Sanitized Probe - 2026-06-25

**Boundary:** `production:no-oa-bank-batches-api-stale-reasons-sanitized-probe`
**Status:** `implementation-closed`
**Module closure:** `not-module-closed`
**Production mutation:** GET fresh gate may enqueue because the endpoint is currently stale
**Worker threads created:** none
**Previous boundary:** `production:no-oa-bank-batches-focused-api-freshness-recheck`

## Goal

Collect only the sanitized API freshness metadata needed to explain why authenticated user-scope `GET /api/no-oa-bank-batches?month=2026-06&bucket=unsubmitted&page=1&page_size=200` still reports `read_model_status=stale`.

This boundary must print only:

- HTTP status;
- elapsed time;
- `read_model_status`;
- `read_model_stale_reasons`;
- `refresh_enqueued`;
- `refresh_reason`;
- selected pagination scalar counts if present;
- session access metadata;
- pre/post health and read-model aggregate status.

It must not print `summary`, `batches`, row payloads, batch IDs, transaction IDs, account names, counterparties, credentials, tokens, cookies, passwords, env values or full response bodies.

## Allowed Operations

- `ssh finops-prod-root` with bounded commands.
- `/health/ready` readiness summary and active release discovery.
- Sourcing existing production env files with `set +x`, without printing env values.
- Reading target OA applicant credential summaries and decrypting one target applicant credential only inside a remote Python process.
- OA login inside the same remote Python process to hold the bearer token in memory only.
- One authenticated GET to the no-OA list endpoint, immediately reducing the response to a metadata allowlist before printing.
- Sanitized PostgreSQL aggregate summaries for dirty scopes, readiness, outbox and dead letters.

## Forbidden Operations

- Printing or storing env files, DSNs, OA usernames, passwords, bearer tokens, cookies, private keys, response bodies, payload rows, invoice numbers, project names, counterparties, account names, transaction IDs, batch IDs or other business identifiers.
- Passing tokens on the shell command line or writing tokens to files.
- Browser/admin/write probes.
- Full user-scope probe set.
- Deploy, restart, repair, replay workers, manual requeue, manual refresh, direct SQL mutation, direct readiness mutation, direct dirty-scope mutation or business writes.

## Stop Gates

- Stop before executing if `/health/ready` is unavailable or not ready.
- Stop before executing if the only available auth path would print, store or copy tokens/cookies/passwords/env secret values.
- Stop after one sanitized API response; do not retry blindly.
- If the GET fresh gate enqueues refresh, postcheck must prove dirty/outbox/readiness converged.
- Do not claim module/global closure from this stale-reasons probe.

## Step 1 - Read-Only Production Precheck

Collect active release, `/health/ready`, dirty scope status counts, readiness status counts, read-model outbox status counts and read-model dead-letter aggregate.

Expected evidence: health ready, dirty scopes done, readiness fresh, outbox done, no read-model dead letters.

## Step 2 - Sanitized Stale-Reasons API Probe

Use the Row280/Row282 in-process target OA applicant credential seam. Perform one authenticated GET to:

`/api/no-oa-bank-batches?month=2026-06&bucket=unsubmitted&page=1&page_size=200`

The remote Python process must parse the JSON response and construct a new allowlisted dict before printing. It must discard the original response body and never print row/list fields.

Expected evidence: exact stale reason names are visible without business payload fields.

## Step 3 - Production Postcheck

Repeat Step 1 after the API probe, including a recent no-OA dirty/outbox aggregate.

## Production Evidence

Executed by T0 through `ssh finops-prod-root` after writing this runbook.

Precheck:

- Active release: `dev-pending-invoice-source-17d13466-20260625`.
- `/health/ready`: `ready`.
- Dirty scopes: `done=187056`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=202951`.
- Read-model dead letters: none.

Sanitized API stale-reasons probe:

- Configured target credential count: `2`.
- Session: `allowed=true`, `can_access_app=true`, `can_mutate_data=true`, `can_admin_access=false`, `access_tier=full_access`.
- Request: `GET /api/no-oa-bank-batches?month=2026-06&bucket=unsubmitted&page=1&page_size=200`.
- HTTP status: `200`.
- Elapsed: `221.667ms`.
- `read_model_status`: `stale`.
- `read_model_stale_reasons`: `workbench_read_model_schema_version_mismatch`.
- `refresh_enqueued`: `true`.
- `refresh_reason`: `api_no_oa_source_versions_stale`.
- Response payload was stripped before printing; `summary`, `batches`, row payloads and identifiers were not printed.

Postcheck:

- Initial postcheck saw the expected GET-triggered no-OA refresh still `processing/pending`.
- Follow-up postcheck after a short wait proved convergence:
  - `/health/ready`: `ready`.
  - Dirty scopes: `done=187057`.
  - App Status readiness: `fresh=498`.
  - Read-model outbox: `done=202952`.
  - Recent no-OA outbox in last hour: `done=3`, latest `2026-06-25 06:33:15.765409+08`.
  - Recent no-OA dirty in last hour: `all/done=3`, latest `2026-06-25 06:33:15.75908+08`.
  - Read-model dead letters: none.

No payload row, batch id, transaction id, account name, counterparty, secret, env value, DB mutation, queue mutation, readiness mutation, deploy, restart, manual refresh, manual requeue, repair command or worker replay occurred in the production probe.

## Root Cause

The production API process reports `workbench_read_model_schema_version_mismatch` because the no-OA API service was wired to `Application._workbench_matching_source_versions()`, which emits legacy `WORKBENCH_READ_MODEL_SCHEMA_VERSION`, while the no-OA read-model refresh worker writes rows using the SQL projection source-version contract (`WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION`) through `runtime_worker_handlers._workbench_matching_source_versions(...)`.

Row281 did not reproduce the mismatch because its fresh deployed-code reconstruction used the SQL projection constant. Row283 proved the live API route still used the legacy server helper.

## Local Fix

Implemented a narrow no-OA API source-version provider:

- Added `Application._no_oa_bank_batch_workbench_source_versions()`, which preserves the existing Workbench matching source-version fields but overrides `workbench_read_model_schema_version` to `WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION`.
- Wired `_no_oa_bank_batch_application_service()` to that no-OA-specific provider instead of the legacy `_workbench_matching_source_versions()`.
- Added a regression test proving `app._no_oa_bank_batch_application_service().no_oa_bank_batch_source_versions()["workbench_read_model_schema_version"] == WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION`.

## Verification

- `PYTHONPATH=backend/src pytest -q tests/test_no_oa_bank_batch_read_model_refresh.py::NoOaBankBatchReadModelRefreshTests::test_no_oa_api_source_versions_use_sql_workbench_schema_version`
- `PYTHONPATH=backend/src pytest -q tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_workbench_integration.py`
- `PYTHONPATH=backend/src pytest -q tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_source_version_helpers_stay_out_of_application`

## Next Safe Action

Deploy the no-OA API source-version provider fix through a bounded production deploy/convergence runbook, then rerun the focused no-OA API freshness probe. Do not run broad user-scope/browser/admin/write probes until this focused no-OA blocker is closed.
