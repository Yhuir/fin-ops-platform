# Production No-OA Bank Batches Focused API Freshness Recheck - 2026-06-25

**Boundary:** `production:no-oa-bank-batches-focused-api-freshness-recheck`
**Status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Production mutation:** GET fresh gate may enqueue only if the endpoint is unexpectedly non-fresh
**Worker threads created:** none
**Previous boundary:** `production:no-oa-bank-batches-api-stale-read-only-diagnosis`

## Goal

Run one focused authenticated user-scope production API metadata recheck for `no_oa_bank_batches` after Row281 proved the persisted no-OA rows now match the deployed source-version contract.

Target expectation:

- HTTP `200`.
- `read_model_status=fresh`.
- `refresh_enqueued_count=0`.
- p95 below the existing `http_slo_probe` 1s target.

This boundary must not run broad user-scope probes, browser probes, admin probes or write probes. It must not claim module/global closure.

## Allowed Operations

- `ssh finops-prod-root` with bounded commands.
- `/health/ready` readiness summary and active release discovery.
- Sourcing existing production env files with `set +x`, without printing env values.
- Reading target OA applicant credential summaries and decrypting one target applicant credential only inside a remote Python process.
- OA login inside the same remote Python process to hold the bearer token in memory only.
- API-only `http_slo_probe.collect_http_slo(...)` with the single `no_oa_bank_batches` probe and `include_samples=False`.
- Sanitized PostgreSQL aggregate summaries for dirty scopes, readiness, outbox and dead letters.

## Forbidden Operations

- Printing or storing env files, DSNs, OA usernames, passwords, bearer tokens, cookies, private keys, response bodies, payload rows, invoice numbers, project names, counterparties, account names or other business identifiers.
- Passing tokens on the shell command line or writing tokens to files.
- Browser/admin/write probes.
- Full user-scope probe set unless the focused no-OA probe passes cleanly and a separate boundary selects that work.
- Deploy, restart, repair, replay workers, manual requeue, direct SQL mutation, direct readiness mutation, direct dirty-scope mutation or business writes.

## Stop Gates

- Stop before executing if `/health/ready` is unavailable or not ready.
- Stop before executing if precheck shows active dirty/outbox/dead-letter blockers unrelated to the selected probe.
- Stop before executing if the only available auth path would print, store or copy tokens/cookies/passwords/env secret values.
- Stop after the focused probe if `no_oa_bank_batches` is not `fresh`, if it enqueues a refresh, or if it exceeds the target.
- Stop if postcheck shows health not ready or unresolved non-done read-model outbox/dirty/dead-letter rows.

## Step 1 - Read-Only Production Precheck

Collect:

- active release name and git commit if available;
- `/health/ready` summary;
- dirty scope status counts;
- App Status readiness status counts;
- read-model outbox status counts;
- read-model dead-letter aggregate.

Expected evidence:

- `/health/ready` reports `ready`;
- dirty scopes are all `done`;
- readiness rows are all `fresh`;
- read-model outbox rows are all `done`;
- dead-letter groups are empty.

Rollback/cleanup: none. This is read-only.

## Step 2 - Focused User-Scope No-OA API Metadata Probe

Use the Row280 in-process target OA applicant credential seam:

- list enabled configured target OA applicant credentials without printing usernames/passwords;
- resolve and login inside the same Python process;
- call `http_slo_probe.collect_http_slo(...)` with only the `no_oa_bank_batches` probe;
- print sanitized metadata only.

Expected evidence:

- target credential count is non-zero;
- session is allowed full-access user scope and `can_admin_access=false`;
- focused probe status is `pass`;
- `no_oa_bank_batches` returns HTTP `200`, `read_model_status=fresh`, `refresh_enqueued_count=0`, p95 under `1000ms`;
- output includes no response bodies or secrets.

Rollback/cleanup: none for API calls. If the GET fresh gate unexpectedly enqueues refreshes, postcheck must prove dirty/outbox/readiness converged and the boundary remains `production-evidence-deferred`.

## Step 3 - Production Postcheck

Repeat Step 1 after the API probe.

Expected evidence:

- `/health/ready` remains `ready`;
- dirty scopes are all `done`;
- readiness rows are all `fresh`;
- read-model outbox rows are all `done`;
- dead-letter groups are empty.

## Production Evidence

Executed by T0 through `ssh finops-prod-root` after writing this runbook.

Precheck:

- Active release: `dev-pending-invoice-source-17d13466-20260625`.
- `/health/ready`: `ready`.
- Dirty scopes: `done=187055`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=202950`.
- Read-model dead letters: none.

Focused API probe:

- Configured target credential count: `2`.
- Session: `allowed=true`, `can_access_app=true`, `can_mutate_data=true`, `can_admin_access=false`, `access_tier=full_access`.
- Probe set: `no_oa_bank_batches` only.
- HTTP status: `200`.
- p95: `165.274ms`.
- `read_model_statuses`: `stale=1`.
- `refresh_enqueued_count`: `1`.
- Focused report status: `fail`.
- Full user-scope, browser, admin and write probes were not run.

Postcheck after the failed focused probe:

- `/health/ready`: `ready`.
- Dirty scopes: `done=187056`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=202951`.
- Recent no-OA outbox rows in last hour: `done=2`, latest `2026-06-25 06:29:53.777793+08`.
- Recent no-OA dirty rows in last hour: `all/done=2`, latest `2026-06-25 06:29:53.771578+08`.
- Read-model dead letters: none.

No response body, payload row, batch id, transaction id, account name, counterparty, secret, env value, DB mutation, queue mutation, readiness mutation, deploy, restart, requeue, repair command or worker replay occurred in this boundary. The only side effect was the expected GET fresh gate enqueue when the endpoint reported stale; it converged to done/fresh.

## Result

The focused API recheck did not pass. It confirms the user-scope no-OA endpoint still reports `read_model_status=stale` and enqueues refresh even after Row281 proved current persisted rows match the exact deployed base source-version contract and optional downstream-key contract from a fresh deployed-code process.

The next boundary should collect the API response's sanitized `read_model_stale_reasons` only, without printing `summary`, `batches`, row payloads, IDs, account names or counterparties. Repeating refreshes is not justified until the actual API stale reason is known.
