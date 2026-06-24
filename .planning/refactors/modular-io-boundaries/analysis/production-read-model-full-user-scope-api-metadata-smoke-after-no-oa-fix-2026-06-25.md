# Production Read-Model Full User-Scope API Metadata Smoke After No-OA Fix - 2026-06-25

**Boundary:** `production:read-model-full-user-scope-api-metadata-smoke-after-no-oa-fix`
**Status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Production mutation:** authenticated GET fresh gates may enqueue only if an endpoint unexpectedly reports stale
**Worker threads created:** none
**Previous boundary:** `production:no-oa-source-version-provider-fix-deploy-and-convergence`

## Goal

Run a full non-admin user-scope authenticated production API metadata smoke after pending invoice and no-OA focused blockers were fixed and deployed.

Target evidence:

- active release remains `dev-no-oa-source-version-480d2d0e-20260625`;
- `/health/ready` is ready;
- dirty scopes are all `done`;
- App Status readiness rows are all `fresh`;
- read-model outbox rows are all `done`;
- read-model dead letters are empty;
- target OA applicant session is full-access user scope and not admin;
- every non-admin `http_slo_probe.DEFAULT_API_PROBES` probe returns its expected HTTP status;
- read-model metadata is fresh where present;
- no probe enqueues refresh;
- p95 is below each probe target.

This boundary must not run browser probes, admin-only probes or write probes. It must not claim module/global closure.

## Allowed Operations

- `ssh finops-prod-root` with bounded commands.
- `/health/ready` readiness summary and active release/git commit discovery.
- Sourcing existing production env files with `set +x`, without printing env values.
- Reading target OA applicant credential summaries and decrypting one target applicant credential only inside a remote Python process.
- OA login inside the same remote Python process to hold the bearer token in memory only.
- API-only `http_slo_probe.collect_http_slo(...)` with all `DEFAULT_API_PROBES` where `auth_scope != "admin"`, `iterations=1`, `warmup=1`, `include_samples=False`.
- Sanitized PostgreSQL aggregate summaries for dirty scopes, readiness, outbox and dead letters.
- If any probe fails, sanitized failing-probe metadata only: probe name, path, expected/status counts, read model statuses, refresh enqueue count, p95, error codes and report summary.

## Forbidden Operations

- Printing or storing env files, DSNs, OA usernames, passwords, bearer tokens, cookies, private keys, response bodies, `samples`, payload rows, invoice numbers, project names, counterparties, account names, transaction IDs, batch IDs or other business identifiers.
- Passing tokens on the shell command line or writing tokens to files.
- Browser probes, admin-only probes, write probes, repair tools, worker replay, manual queue consume, direct SQL mutation, direct readiness mutation, direct dirty-scope mutation or business writes.
- Deploy, restart, requeue or manual refresh in this boundary.

## Stop Gates

- Stop before executing if `/health/ready` is unavailable or not ready.
- Stop before executing if precheck shows non-done dirty/outbox rows, non-fresh readiness rows or read-model dead letters.
- Stop before executing if active release is not `dev-no-oa-source-version-480d2d0e-20260625`.
- Stop before executing if the only available auth path would print, store or copy tokens/cookies/passwords/env secret values.
- Stop after the smoke if any probe fails, reports stale/non-fresh metadata, enqueues refresh or exceeds target; collect only sanitized failure metadata and postcheck evidence.
- Do not continue into browser/admin/write or closure audit from this boundary.

## Exact Commands

Production precheck:

```bash
ssh finops-prod-root 'bash -s' <<'REMOTE'
set -euo pipefail
python3 - <<'PY'
# Print only active release/git metadata, health status and aggregate read-model status counts.
PY
REMOTE
```

Full user-scope API metadata smoke:

```bash
ssh finops-prod-root 'bash -s' <<'REMOTE'
set +x
set -euo pipefail
python3 - <<'PY'
# Source production config without printing env values.
# Resolve one configured target OA applicant credential inside this process.
# Login and run all non-admin DEFAULT_API_PROBES with include_samples=False.
# Print only sanitized scalar probe summaries.
PY
REMOTE
```

Production postcheck:

```bash
ssh finops-prod-root 'bash -s' <<'REMOTE'
set -euo pipefail
python3 - <<'PY'
# Print only active release/git metadata, health status, aggregate read-model status counts,
# recent read-model outbox/dirty aggregate counts and read-model dead-letter aggregate counts.
PY
REMOTE
```

## Rollback And Cleanup

No rollback or cleanup is expected because this boundary performs only authenticated GET probes and read-only aggregate checks. If a GET fresh gate unexpectedly enqueues refresh, cleanup is limited to waiting for the existing worker pipeline to converge and recording postcheck evidence. No manual queue/readiness/dirty-scope cleanup is allowed.

## Why This Is Bounded

- The probe set is the repository's existing API metadata inventory, filtered to non-admin GET probes.
- It uses one in-process target OA applicant login and never prints or stores the token.
- `include_samples=False` prevents per-request response samples from being printed.
- The output is reduced to scalar probe summaries and aggregate status counts.
- There are no direct production writes, deploys, restarts, repairs, requeues or worker replays.

## Production Evidence

Executed by T0 through root SSH after writing this runbook.

Precheck:

- Active WorkingDirectory: `/opt/fin-ops/releases/dev-no-oa-source-version-480d2d0e-20260625/src`.
- `RELEASE.json`: `release_name=dev-no-oa-source-version-480d2d0e-20260625`, `git_branch=dev`, `git_commit=d117b4519284db00c0fa88bdf7faaa938a5b1f69`.
- `/health/ready`: `ready`.
- Dirty scopes: `done=187057`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=203223`.
- Read-model dead letters: none.

Full user-scope API metadata smoke:

- Configured target credential count: `2`.
- Session: `allowed=true`, `can_access_app=true`, `can_mutate_data=true`, `can_admin_access=false`, `access_tier=full_access`.
- Probe set: all `http_slo_probe.DEFAULT_API_PROBES` with `auth_scope != "admin"`.
- Probe count: `37`.
- Report status: `pass`.
- Failed probe count: `0`.
- Max p95: `757.465ms`.
- `refresh_enqueued_count` reported by `http_slo_probe`: `0` for all probes.
- No probe reported non-fresh read model status.
- Previously failing focused probes now pass:
  - `pending_invoices_rows`: HTTP `200`, `fresh`, p95 `757.465ms`, no reported refresh enqueue.
  - `pending_invoices_filter_options`: HTTP `200`, `fresh`, p95 `120.595ms`, no reported refresh enqueue.
  - `no_oa_bank_batches`: HTTP `200`, `fresh`, p95 `216.596ms`, no reported refresh enqueue.
- Other representative read-model probes passed with fresh metadata where present: Workbench summary/groups, Bank Details accounts/transactions, input invoice usage rows/filter-options, OA pending payments rows/filter-options, output invoice collections rows/filter-options, tax offset summary/rows, cost statistics explorer/summary, batch accounting, and search.

Postcheck:

- Active WorkingDirectory: `/opt/fin-ops/releases/dev-no-oa-source-version-480d2d0e-20260625/src`.
- `RELEASE.json`: `release_name=dev-no-oa-source-version-480d2d0e-20260625`, `git_branch=dev`, `git_commit=d117b4519284db00c0fa88bdf7faaa938a5b1f69`.
- `/health/ready`: `ready`.
- Dirty scopes: `done=187058`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=203224`.
- Read-model dead letters: none.
- Recent read-model outbox in last 20 minutes:
  - `turnover_ledger.read_model.refresh`, `scope_type=turnover_ledger`, `scope_key=all`, `status=done`, latest `2026-06-25 06:48:10.775011+08`.
  - `no_oa_bank_batch.read_model.refresh`, `scope_type=no_oa_bank_batch`, `scope_key=all`, `status=done`, count `2`, latest `2026-06-25 06:33:15.765409+08`.
- Recent dirty scopes in last 20 minutes:
  - `turnover_ledger:all`, `status=done`, latest `2026-06-25 06:48:10.769301+08`.
  - `no_oa_bank_batch:all`, `status=done`, count `2`, latest `2026-06-25 06:33:15.75908+08`.

No response bodies, `samples`, payload rows, credentials, tokens, cookies, env values, direct DB/queue/readiness mutation, repair, requeue, restart, deploy or worker replay occurred in this boundary.

## Result

The full non-admin user-scope API metadata smoke passed at the HTTP/read-model metadata level: 37/37 probes passed, all reported read-model metadata was fresh, and `http_slo_probe` reported zero refresh enqueues.

However, aggregate postcheck showed one new `turnover_ledger.read_model.refresh` outbox/dirty scope created during the smoke and already completed. Because the boundary target required no refresh enqueue, the boundary remains `production-evidence-deferred` rather than `production-controlled`.

The next safe boundary is a read-only/sanitized diagnosis of why the `turnover_ledger_grouped` user-scope GET can enqueue `turnover_ledger:all` while the response metadata does not expose `refresh_enqueued=true`.
