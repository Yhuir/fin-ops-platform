# Production Turnover Ledger User-Scope Hidden Refresh Enqueue Diagnosis - 2026-06-25

**Boundary:** `production:turnover-ledger-user-scope-hidden-refresh-enqueue-diagnosis`
**Status:** `production-diagnosis-closed`
**Module closure:** `not-module-closed`
**Production mutation:** one focused authenticated GET may enqueue only if the endpoint is stale or schedules refresh
**Worker threads created:** none
**Previous boundary:** `production:read-model-full-user-scope-api-metadata-smoke-after-no-oa-fix`

## Goal

Classify why Row285's full user-scope API metadata smoke created one `turnover_ledger.read_model.refresh` for `turnover_ledger:all` while `http_slo_probe` reported `refresh_enqueued_count=0` for `turnover_ledger_grouped`.

Code evidence before production probe:

- `Application._handle_api_turnover_ledger(...)` directly returns the payload from `self._turnover_ledger_read_facade.list_ledger(...)`.
- `TurnoverLedgerApiRoutes.list_ledger(view="grouped")` calls `TurnoverLedgerQueryService.list_ledger(...)` when the query service is present.
- `TurnoverLedgerQueryService.list_ledger(...)` uses `ReadModelQueryGateway.load(...)` with `scope_type="turnover_ledger"` and `scope_key="all"`.
- `ReadModelQueryGateway.load(...)` attaches `read_model_status`, `read_model_scope_key`, `refresh_enqueued`, `refresh_reason` and stale reasons when a view is missing or stale.
- `_normalize_grouped_payload(...)` preserves top-level payload fields via `{**dict(payload), "groups": normalized_groups}`.

This means a focused live response can distinguish:

- fresh response with `refresh_enqueued=false`;
- stale response with `refresh_enqueued=true`;
- missing metadata due to a different payload path;
- Row285 event caused by another probe or unrelated concurrent activity.

## Allowed Operations

- `ssh finops-prod-root` with bounded commands.
- `/health/ready` readiness summary and active release/git commit discovery.
- Sourcing existing production env files with `set +x`, without printing env values.
- Reading target OA applicant credential summaries and decrypting one target applicant credential only inside a remote Python process.
- OA login inside the same remote Python process to hold the bearer token in memory only.
- One authenticated GET to `/api/turnover-ledger?view=grouped&page=1&page_size=50`, reducing the response to top-level metadata allowlist before printing.
- Sanitized PostgreSQL aggregate summaries before and after for dirty scopes, readiness, outbox, read-model dead letters and recent turnover ledger read-model events.

## Forbidden Operations

- Printing or storing env files, DSNs, OA usernames, passwords, bearer tokens, cookies, private keys, response bodies, `samples`, payload rows, invoice numbers, project names, counterparties, account names, transaction IDs, relation IDs or other business identifiers.
- Passing tokens on the shell command line or writing tokens to files.
- Broad API probes, browser probes, admin probes, write probes, deploy, restart, repair tools, worker replay, manual queue consume, direct SQL mutation, direct readiness mutation, direct dirty-scope mutation or business writes.

## Stop Gates

- Stop before executing if `/health/ready` is unavailable or not ready.
- Stop before executing if active release is not `dev-no-oa-source-version-480d2d0e-20260625`.
- Stop before executing if precheck shows non-done dirty/outbox rows, non-fresh readiness rows or read-model dead letters.
- Stop before executing if the only available auth path would print, store or copy tokens/cookies/passwords/env secret values.
- Stop after one focused GET and postcheck; do not retry broadly.
- If the focused GET enqueues refresh, wait only for normal convergence and record sanitized postcheck evidence.

## Exact Commands

Production precheck:

```bash
ssh finops-prod-root 'bash -s' <<'REMOTE'
set -euo pipefail
python3 - <<'PY'
# Print active release/git metadata, health status, aggregate read-model statuses,
# and recent turnover_ledger read-model dirty/outbox aggregate only.
PY
REMOTE
```

Focused GET metadata probe:

```bash
ssh finops-prod-root 'bash -s' <<'REMOTE'
set +x
set -euo pipefail
python3 - <<'PY'
# Source production config without printing env values.
# Resolve/login one target OA applicant credential inside this process.
# GET only /api/turnover-ledger?view=grouped&page=1&page_size=50.
# Print only top-level metadata allowlist and scalar counts.
PY
REMOTE
```

Production postcheck:

```bash
ssh finops-prod-root 'bash -s' <<'REMOTE'
set -euo pipefail
python3 - <<'PY'
# Print active release/git metadata, health status, aggregate read-model statuses,
# and recent turnover_ledger read-model dirty/outbox aggregate only.
PY
REMOTE
```

## Rollback And Cleanup

No rollback or cleanup is expected because this boundary performs one authenticated GET and read-only aggregate checks. If a GET fresh gate enqueues refresh, cleanup is limited to waiting for the existing worker pipeline to converge and recording postcheck evidence. No manual queue/readiness/dirty-scope cleanup is allowed.

## Production Evidence

Executed by T0 through root SSH after writing this runbook.

Precheck:

- Active WorkingDirectory: `/opt/fin-ops/releases/dev-no-oa-source-version-480d2d0e-20260625/src`.
- `RELEASE.json`: `release_name=dev-no-oa-source-version-480d2d0e-20260625`, `git_branch=dev`, `git_commit=d117b4519284db00c0fa88bdf7faaa938a5b1f69`.
- `/health/ready`: `ready`.
- Dirty scopes: `done=187058`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=203224`.
- Read-model dead letters: none.
- Recent turnover outbox in last 30 minutes: `done=1`, latest `2026-06-25 06:48:10.775011+08`.
- Recent turnover dirty in last 30 minutes: `done=1`, latest `2026-06-25 06:48:10.769301+08`.

Focused GET metadata probe:

- Configured target credential count: `2`.
- Session: `allowed=true`, `can_access_app=true`, `can_mutate_data=true`, `can_admin_access=false`, `access_tier=full_access`.
- Request: `GET /api/turnover-ledger?view=grouped&page=1&page_size=50`.
- HTTP status: `200`.
- Elapsed: `140.719ms`.
- Top-level metadata fields were absent:
  - `read_model_status=null`;
  - `read_model_scope_key=null`;
  - `read_model_stale_reasons=null`;
  - `refresh_enqueued=null`;
  - `refresh_reason=null`;
  - `cache_status=null`.
- Top-level response keys after stripping `groups`: `family_summaries`, `filters`, `pagination`, `summary`.
- Scalar pagination only: page `1`, page size `50`, total `20`.
- Group count: `20`.
- Payload rows/groups and identifiers were not printed.

Postcheck:

- Active WorkingDirectory: `/opt/fin-ops/releases/dev-no-oa-source-version-480d2d0e-20260625/src`.
- `/health/ready`: `ready`.
- Dirty scopes: `done=187059`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=203225`.
- Read-model dead letters: none.
- Recent turnover outbox in last 30 minutes: `done=2`, latest `2026-06-25 06:52:50.733073+08`.
- Recent turnover dirty in last 30 minutes: `done=2`, latest `2026-06-25 06:52:50.729942+08`.

Code evidence:

- `Application._handle_api_turnover_ledger(...)` directly returns the payload from `self._turnover_ledger_read_facade.list_ledger(...)`.
- `TurnoverLedgerApiRoutes._normalize_grouped_payload(...)` preserves top-level keys when they exist via `{**dict(payload), "groups": normalized_groups}`.
- `TurnoverLedgerQueryService.list_ledger(...)` would return `ReadModelQueryGateway.load(...)` metadata if its SQL repository/read-model gateway path produced a read-model payload or if PostgreSQL runtime were required.
- `TurnoverLedgerService.list_grouped_ledger(...)` is legacy/live grouped generation and does not add read-model metadata.

## Result

Row285 attribution is confirmed. A focused authenticated user-scope grouped GET created one additional `turnover_ledger.read_model.refresh` for `turnover_ledger:all`; the event and dirty scope converged to `done`, and health/readiness/dead letters stayed clean.

The live grouped response used a legacy grouped payload path with no top-level read-model metadata, so `http_slo_probe` could not observe `refresh_enqueued=true` even though the aggregate queue proved a refresh was created.

This is not a production closure blocker for runtime health because the refresh converged, but it is a modular IO boundary gap: a read-model API GET can still return legacy grouped data without freshness metadata while causing a read-model refresh side effect. The next safe boundary is a local implementation/regression slice to make `view=grouped` use the SQL/read-model freshness contract or otherwise fail/refresh explicitly with metadata instead of silent legacy fallback.
