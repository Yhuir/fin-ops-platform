# Production Turnover Ledger Source Version Persistence Fix Deploy And Convergence - 2026-06-25

**Boundary:** `production:turnover-ledger-source-version-persistence-fix-deploy-and-convergence`
**Status:** `runbook-prepared`
**Module closure:** `not-module-closed`
**Target branch:** `dev`
**Target commit before deploy:** current `origin/dev` after this runbook is committed; record exact `RELEASE.json` git commit after deploy.
**Planned release name:** `dev-turnover-source-version-persistence-20260625`
**Previous production release:** `dev-turnover-grouped-metadata-20260625`

## Goal

Deploy the turnover source-version capture fix and prove the production grouped turnover read path no longer reports `turnover_relation_snapshot_version_mismatch` after refresh convergence.

## Safety Scope

Allowed:

- read-only production prechecks and postchecks;
- one deploy through `./scripts/deploy-oa.sh --release-name dev-turnover-source-version-persistence-20260625`;
- one focused authenticated user-scope grouped turnover metadata probe;
- read-only persisted source-version comparison before/after deploy.

Forbidden:

- printing or storing secrets, cookies, bearer tokens, passwords, env values, response bodies, payload rows, grouped rows or business identifiers;
- broad API smoke, browser smoke, admin smoke or write-flow smoke;
- manual repair, direct SQL mutation, readiness mutation, broad refresh/replay, requeue or worker restart outside the deploy script;
- claiming module/global closure from this deploy/convergence.

## Precheck Plan

Collect sanitized evidence:

- active release and release git commit;
- `/health/ready`;
- dirty/readiness/outbox/dead-letter aggregate counts;
- current turnover persisted source-version comparison, including only keys, mismatch reasons and hash prefixes.

## Deploy Plan

Run:

```bash
./scripts/deploy-oa.sh --release-name dev-turnover-source-version-persistence-20260625
```

Expected:

- deploy exits `0`;
- active release `RELEASE.json` points at the committed `origin/dev` deployment commit that includes `e5ee227551fe7e2c4ee45d51be3ada1c568fbb2d`;
- `/health/ready` returns `ready`.

## Focused Probe Plan

Run one focused authenticated user-scope metadata probe for:

- `GET /api/turnover-ledger?view=grouped&page=1&page_size=50`

Allowed output:

- credential count;
- session permission booleans;
- HTTP status and elapsed milliseconds;
- top-level read-model metadata fields;
- top-level key list excluding `rows` and `groups`;
- group count and pagination scalars.

Expected clean result:

- HTTP `200`;
- `read_model_status=fresh`;
- `refresh_enqueued=false`;
- no `turnover_relation_snapshot_version_mismatch`.

If the probe still enqueues:

- metadata must expose the enqueue and stale reasons;
- postcheck must classify whether the refresh converged and whether persisted source versions now match after convergence.

## Postcheck Plan

Repeat:

- `/health/ready`;
- dirty/readiness/outbox/dead-letter aggregates;
- turnover persisted source-version comparison.

## Stop Criteria

Stop without broadening if deploy fails, readiness regresses, read-model dead letters appear, turnover refresh does not converge, or focused grouped metadata still reports a source-version mismatch after convergence.
