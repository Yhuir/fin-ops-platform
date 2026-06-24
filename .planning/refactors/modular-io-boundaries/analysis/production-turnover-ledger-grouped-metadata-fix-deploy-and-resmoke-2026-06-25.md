# Production Turnover Ledger Grouped Metadata Fix Deploy And Resmoke - 2026-06-25

**Boundary:** `production:turnover-ledger-grouped-metadata-fix-deploy-and-resmoke`
**Status:** `runbook-prepared`
**Module closure:** `not-module-closed`
**Target branch:** `dev`
**Target commit before deploy:** `57aacc004d3d8fcdf9d0c00a463d3e15d35965d9`
**Planned release name:** `dev-turnover-grouped-metadata-57aacc00-20260625`
**Previous production release:** `dev-no-oa-source-version-480d2d0e-20260625`

## Goal

Deploy the turnover ledger grouped metadata preservation fix and run one focused authenticated user-scope metadata re-smoke for:

- `GET /api/turnover-ledger?view=grouped&page=1&page_size=50`

The probe must prove top-level read-model metadata is now observable, or explicitly classify any remaining enqueue/freshness behavior.

## Safety Scope

Allowed:

- read-only production prechecks and postchecks;
- one deploy through `./scripts/deploy-oa.sh --release-name dev-turnover-grouped-metadata-57aacc00-20260625`;
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
./scripts/deploy-oa.sh --release-name dev-turnover-grouped-metadata-57aacc00-20260625
```

Expected:

- deploy exits `0`;
- active release `RELEASE.json` points at commit `57aacc004d3d8fcdf9d0c00a463d3e15d35965d9`;
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
