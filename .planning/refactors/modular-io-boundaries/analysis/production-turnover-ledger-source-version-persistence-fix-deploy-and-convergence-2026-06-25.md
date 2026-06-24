# Production Turnover Ledger Source Version Persistence Fix Deploy And Convergence - 2026-06-25

**Boundary:** `production:turnover-ledger-source-version-persistence-fix-deploy-and-convergence`
**Status:** `production-controlled`
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

## Production Evidence

Executed by T0 through root SSH and the standard deploy script. No secrets, tokens, cookies, passwords, env values, response bodies, payload rows, grouped rows or business identifiers were printed.

### Precheck

- Active release before deploy: `dev-turnover-grouped-metadata-20260625`.
- Active release commit before deploy: `2dbacf9f6054baabe7084fc87b87511a49bbdb95`.
- `/health/ready`: `ready`.
- Dirty scopes: `done=187060`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=202955`.
- Read-model dead letters: none.
- Turnover dirty aggregate: `done=461`, latest `2026-06-25 07:07:13.844547+08`.
- Turnover outbox aggregate: `done=563`, latest `2026-06-25 07:07:13.851087+08`.
- Baseline mismatch reasons: `turnover_relation_snapshot_version_mismatch`.
- Baseline expected hash prefix: `7c63fec7ba82c80c`.
- Baseline persisted top-level and first-row hash prefix: `198f5fd5f7ccbb8a`.

### Deploy

Command:

```bash
./scripts/deploy-oa.sh --release-name dev-turnover-source-version-persistence-20260625
```

Result:

- Deploy exited `0`.
- Frontend build completed with the existing minified CSS warnings.
- Active release after deploy: `dev-turnover-source-version-persistence-20260625`.
- Active `RELEASE.json`: `git_branch=dev`, `git_commit=8f525563e10972168014356ff410c4fc8456f377`.
- App service, RabbitMQ dispatcher and all listed worker units were active during deploy-control status checks.

### Initial Focused Probe

Immediately after deploy, the persisted read model still carried pre-deploy source versions, so the first focused grouped GET correctly exposed a visible refresh:

- Request: `GET /api/turnover-ledger?view=grouped&page=1&page_size=50`.
- Configured target credential count: `2`.
- Session: `allowed=true`, `can_access_app=true`, `can_mutate_data=true`, `can_admin_access=false`, `access_tier=full_access`.
- HTTP status: `200`.
- Elapsed: `85.277ms`.
- `read_model_status=refreshing`.
- `read_model_scope_key=all`.
- `read_model_stale_reasons=["turnover_relation_snapshot_version_mismatch"]`.
- `refresh_enqueued=true`.
- `refresh_reason=source_version_mismatch`.
- Group count: `20`.
- Pagination scalars: page `1`, page size `50`, total `20`.

### Convergence Postcheck

After the visible refresh converged:

- Active release: `dev-turnover-source-version-persistence-20260625`.
- Active release commit: `8f525563e10972168014356ff410c4fc8456f377`.
- `/health/ready`: `ready`.
- Dirty scopes: `done=187061`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=202956`.
- Read-model dead letters: none.
- Turnover dirty aggregate: `done=462`, latest `2026-06-25 07:21:52.785154+08`.
- Turnover outbox aggregate: `done=564`, latest `2026-06-25 07:21:52.790827+08`.
- Persisted mismatch reasons: none.
- Persisted first-row mismatch reasons: none.
- Expected hash prefix: `7c63fec7ba82c80c`.
- Persisted top-level hash prefix: `7c63fec7ba82c80c`.
- Persisted first-row hash prefix: `7c63fec7ba82c80c`.
- Expected equals persisted top-level: `true`.
- Expected equals persisted first row: `true`.
- Repository `read_model_status_field=fresh`.

### Post-convergence Focused Recheck

The same focused grouped turnover GET after convergence:

- HTTP status: `200`.
- Elapsed: `67.957ms`.
- `read_model_status=fresh`.
- `read_model_scope_key=all`.
- `read_model_stale_reasons=null`.
- `refresh_enqueued=false`.
- `refresh_reason=null`.
- Group count: `20`.
- Pagination scalars: page `1`, page size `50`, total `20`.

Final aggregate postcheck after this recheck showed no additional turnover dirty/outbox delta:

- `/health/ready`: `ready`.
- Dirty scopes: `done=187061`.
- App Status readiness: `fresh=498`.
- Read-model outbox: `done=202956`.
- Read-model dead letters: none.
- Turnover dirty aggregate remained `done=462`, latest `2026-06-25 07:21:52.785154+08`.
- Turnover outbox aggregate remained `done=564`, latest `2026-06-25 07:21:52.790827+08`.

## Result

The production source-version persistence fix is controlled and converged. The first post-deploy GET surfaced the expected refresh against old persisted rows; the new worker then rewrote top-level and row-level `turnover_relation_snapshot_version` to match API expected source versions. A post-convergence focused grouped GET returned `fresh` with `refresh_enqueued=false`, and aggregate dirty/outbox counts did not increase afterward.

Next safe boundary: retry the full non-admin user-scope API metadata smoke to confirm the previous hidden/aggregate enqueue issue is gone across all default user-scope probes.
