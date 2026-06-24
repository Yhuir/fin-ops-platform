# Production Read Model Full User Scope API Metadata Smoke After Turnover Fixes - 2026-06-25

**Boundary:** `production:read-model-full-user-scope-api-metadata-smoke-after-turnover-fixes`
**Status:** `production-controlled`
**Module closure:** `not-module-closed`
**Production mutation:** GET-only API smoke; GET fresh gates may enqueue read-model refresh if stale is found.
**Active release expected:** `dev-turnover-source-version-persistence-20260625`

## Goal

Retry the full non-admin user-scope API metadata smoke after pending invoice, no-OA and turnover grouped/source-version fixes. Prove the default user-scope read-model-heavy API probes pass without hidden aggregate refresh enqueue, or classify any remaining delta.

## Safety Scope

Allowed:

- read-only production prechecks and postchecks;
- one full non-admin user-scope `http_slo_probe.DEFAULT_API_PROBES` run through the existing target OA applicant credential seam;
- no response bodies, payload samples or payload rows in output;
- aggregate dirty/outbox/readiness/dead-letter comparison before/after.

Forbidden:

- printing/storing secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers;
- browser, admin or write-flow probes;
- direct SQL mutation, manual refresh/requeue/replay/repair, readiness mutation or deploy.

## Precheck Plan

Collect:

- active release and release commit;
- `/health/ready`;
- dirty scope status counts;
- App Status readiness status counts;
- read-model outbox status counts;
- read-model dead-letter counts;
- recent read-model outbox/dirty max timestamps by scope type for attribution if counts move.

## Smoke Plan

Run a remote Python process that:

1. loads production env without printing values;
2. resolves one configured target OA applicant credential in memory;
3. logs in and builds auth headers in memory;
4. verifies session is non-admin user scope;
5. runs all probes in `http_slo_probe.DEFAULT_API_PROBES` except admin probes;
6. uses `iterations=1`, `warmup=1`, `include_samples=False`, `timeout_seconds=20`;
7. prints sanitized report only.

Expected:

- all non-admin probes pass;
- probe-level read-model metadata is fresh/no enqueue where applicable;
- aggregate dirty/outbox totals do not increase.

## Postcheck Plan

Repeat precheck and compare:

- if dirty/outbox totals move, classify event type/scope/latest timestamp before any next step;
- stop before browser/admin/write probes unless aggregate no-enqueue is proven.

## Stop Criteria

Stop if any probe fails, any unexpected aggregate dirty/outbox delta appears, `/health/ready` regresses, or read-model dead letters appear.

## Production Evidence

Executed by T0 through root SSH. No secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows, samples or business identifiers were printed.

### Precheck

- Active release: `dev-turnover-source-version-persistence-20260625`.
- Active release commit: `8f525563e10972168014356ff410c4fc8456f377`.
- `/health/ready`: `ready`.
- Dirty scopes: `done=187061`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=202956`.
- Read-model dead letters: none.
- Recent turnover dirty aggregate: `done=4`, latest `2026-06-25 07:21:52.785154+08`.
- Recent turnover outbox aggregate: `done=4`, latest `2026-06-25 07:21:52.790827+08`.
- Recent no-OA dirty aggregate: `done=2`, latest `2026-06-25 06:33:15.75908+08`.
- Recent no-OA outbox aggregate: `done=2`, latest `2026-06-25 06:33:15.765409+08`.

### Full Non-admin User-scope API Smoke

Ran all non-admin probes in `http_slo_probe.DEFAULT_API_PROBES` through the target OA applicant credential seam with `include_samples=false`.

- Configured target credential count: `2`.
- Session: `allowed=true`, `can_access_app=true`, `can_mutate_data=true`, `can_admin_access=false`, `access_tier=full_access`.
- Probe count: `37`.
- Status: `pass`.
- Failed probes: `0`.
- Non-fresh probes: `0`.
- Probe-level refresh-enqueued probes: `0`.
- Response bodies, payload rows and samples were not printed.

### Postcheck

- `/health/ready`: `ready`.
- Dirty scopes: `done=187061`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=202956`.
- Read-model dead letters: none.
- Recent turnover dirty/outbox and no-OA dirty/outbox aggregates were unchanged from precheck.

## Result

The full non-admin user-scope API metadata smoke is production-controlled. All 37 probes passed, all reported read-model metadata was fresh/no-enqueue where applicable, and aggregate dirty/outbox totals did not increase. This closes the previous API aggregate no-enqueue gap from Row285 after the pending invoice, no-OA and turnover fixes.

Browser, admin and write-flow production evidence remain out of scope for this boundary and still open for global closure.
