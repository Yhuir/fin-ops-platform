# Production Turnover Ledger Grouped Metadata Fix Deploy And Resmoke - 2026-06-25

**Boundary:** `production:turnover-ledger-grouped-metadata-fix-deploy-and-resmoke`
**Status:** `production-controlled`
**Module closure:** `not-module-closed`
**Target branch:** `dev`
**Target commit before deploy:** current `origin/dev` after this runbook is committed; record exact `RELEASE.json` git commit after deploy.
**Planned release name:** `dev-turnover-grouped-metadata-20260625`
**Previous production release:** `dev-no-oa-source-version-480d2d0e-20260625`

## Goal

Deploy the turnover ledger grouped metadata preservation fix and run one focused authenticated user-scope metadata re-smoke for:

- `GET /api/turnover-ledger?view=grouped&page=1&page_size=50`

The probe must prove top-level read-model metadata is now observable, or explicitly classify any remaining enqueue/freshness behavior.

## Safety Scope

Allowed:

- read-only production prechecks and postchecks;
- one deploy through `./scripts/deploy-oa.sh --release-name dev-turnover-grouped-metadata-20260625`;
- one focused authenticated user-scope metadata probe through the existing target OA applicant credential seam;
- recording sanitized metadata and aggregate counts only.

Forbidden:

- printing or storing secrets, cookies, bearer tokens, passwords, env values, response bodies, payload rows, groups or business identifiers;
- broad API smoke, browser smoke, admin smoke or write-flow smoke;
- manual refresh, requeue, repair, replay, readiness mutation, direct DB mutation or broad worker restart;
- claiming module/global closure from this deploy/re-smoke.

## Precheck Plan

Before deploy, collect sanitized evidence:

- active systemd working directory and deployed `RELEASE.json` release/commit;
- `/health` and `/health/ready`;
- `job.read_model_dirty_scopes` status counts;
- App Status read-model readiness status counts;
- `job.outbox_events` read-model status counts;
- read-model dead-letter counts;
- recent turnover ledger outbox/dirty latest timestamps.

## Deploy Plan

Run:

```bash
./scripts/deploy-oa.sh --release-name dev-turnover-grouped-metadata-20260625
```

Expected:

- deploy exits `0`;
- active release `RELEASE.json` points at the committed `origin/dev` deployment commit that includes `a16ab9863ba2c2335457b2598a5a970489658bec`;
- services return ready after deploy.

## Focused Resmoke Plan

Run one focused in-process authenticated metadata probe using target OA applicant credentials without printing/storing credentials or payload rows.

Allowed output fields:

- HTTP status;
- elapsed/p95 metadata;
- top-level `read_model_status`;
- top-level `read_model_scope_key`;
- top-level `read_model_stale_reasons`;
- top-level `refresh_enqueued`;
- top-level `refresh_reason`;
- top-level `cache_status`;
- sanitized top-level key list excluding `groups` and `rows`;
- group count and pagination counters only.

Expected fresh result:

- HTTP `200`;
- `read_model_status=fresh`;
- `refresh_enqueued=false`;
- aggregate turnover dirty/outbox totals do not increase.

If the probe enqueues:

- response metadata must expose `refresh_enqueued=true` and available reason/stale metadata;
- postcheck must show the turnover event/dirty scope converged or classify the failure.

## Postcheck Plan

Repeat the precheck evidence and compare:

- health/readiness remain ready/fresh;
- read-model dead letters remain absent;
- any dirty/outbox delta is classified, especially `turnover_ledger:all`.

## Rollback / Stop Criteria

Stop and do not broaden the boundary if:

- deploy fails;
- `/health/ready` fails after deploy;
- read-model dead letters appear;
- turnover dirty/outbox events do not converge;
- focused grouped metadata remains absent;
- probe requires secrets or payload rows to diagnose.

Rollback path for a failed deploy is the existing release rollback procedure through the deployment script/systemd release symlink. Do not execute rollback unless a concrete deploy failure or readiness regression occurs and the reason is documented.

## Follow-up Decision

Only after this focused probe and aggregate postcheck are understood should T0 decide whether to retry the full non-admin user-scope API smoke. Browser/admin/write evidence remains out of scope for this boundary.

## Production Evidence

Executed by T0 through root SSH after this runbook was committed. No secrets, tokens, cookies, passwords, response bodies, payload rows, grouped rows or business identifiers were printed.

### Precheck

- Active release before deploy: `dev-no-oa-source-version-480d2d0e-20260625`.
- Active release commit before deploy: `d117b4519284db00c0fa88bdf7faaa938a5b1f69`.
- `/health/ready`: `ready`.
- Dirty scopes: `done=187059`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=202954`.
- Read-model dead letters: none.
- Turnover outbox recent aggregate: `done=562`, latest `2026-06-25 06:52:50.733073+08`.
- Turnover dirty recent aggregate: `done=460`, latest `2026-06-25 06:52:50.729942+08`.

### Deploy

Command:

```bash
./scripts/deploy-oa.sh --release-name dev-turnover-grouped-metadata-20260625
```

Result:

- Deploy exited `0`.
- Frontend build completed with the existing minified CSS warnings.
- Active release after deploy: `dev-turnover-grouped-metadata-20260625`.
- Active `RELEASE.json`: `git_branch=dev`, `git_commit=2dbacf9f6054baabe7084fc87b87511a49bbdb95`.
- App service, RabbitMQ dispatcher and all listed worker units were active during deploy-control status checks.

### Focused Metadata Probe

Focused authenticated user-scope probe:

- Request: `GET /api/turnover-ledger?view=grouped&page=1&page_size=50`.
- Configured target credential count: `2`.
- Session: `allowed=true`, `can_access_app=true`, `can_mutate_data=true`, `can_admin_access=false`, `access_tier=full_access`.
- HTTP status: `200`.
- Elapsed: `110.729ms`.
- `read_model_status=refreshing`.
- `read_model_scope_key=all`.
- `read_model_stale_reasons=["turnover_relation_snapshot_version_mismatch"]`.
- `refresh_enqueued=true`.
- `refresh_reason=source_version_mismatch`.
- `cache_status=null`.
- Top-level keys excluding `rows`/`groups`: `family_summaries`, `filters`, `pagination`, `read_model_scope_key`, `read_model_stale_reasons`, `read_model_status`, `refresh_enqueued`, `refresh_reason`, `source_versions`, `summary`.
- Group count: `20`.
- Pagination scalars: page `1`, page size `50`, total `20`.

### Postcheck

- Active release after deploy: `dev-turnover-grouped-metadata-20260625`.
- Active `RELEASE.json`: `git_branch=dev`, `git_commit=2dbacf9f6054baabe7084fc87b87511a49bbdb95`.
- `/health/ready`: `ready`.
- Dirty scopes: `done=187060`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=202955`.
- Read-model dead letters: none.
- Turnover outbox recent aggregate: `done=563`, latest `2026-06-25 07:07:13.851087+08`.
- Turnover dirty recent aggregate: `done=461`, latest `2026-06-25 07:07:13.844547+08`.

## Result

The deployed grouped metadata fix works: the focused grouped turnover response now exposes top-level read-model metadata and no longer hides the GET-triggered enqueue. The boundary remains not-module-closed because the response also proved a separate production freshness issue, `turnover_relation_snapshot_version_mismatch`, which caused one visible `turnover_ledger:all` refresh. That refresh converged to `done`, health stayed ready, readiness stayed fresh and no read-model dead letters appeared.

Next safe boundary: a read-only diagnosis of the turnover relation snapshot source-version mismatch before retrying full user-scope API smoke.
