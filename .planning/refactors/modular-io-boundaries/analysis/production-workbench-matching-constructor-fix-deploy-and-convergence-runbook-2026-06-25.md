# Production Workbench Matching Constructor Fix Deploy And Convergence Runbook 2026-06-25

**Boundary:** `production:workbench-matching-constructor-fix-deploy-and-convergence-runbook`
**Final status:** `production-controlled`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `b4539f343f6774a3f6659dcc1a03f73fdff44740`
**Target release:** `dev-workbench-matching-port-20260625020818`

## Target

Deploy the local `WorkbenchMatchingWorkerFactory` constructor fix and prove the production `fin-ops-worker@workbench-matching.service` no longer restart-loops on:

```text
TypeError: WorkbenchMatchingOrchestrator.__init__() got an unexpected keyword argument 'pair_relation_service'
```

## Preconditions

- Local branch is `dev`.
- Local `HEAD` equals `origin/dev`.
- Last local commit is `b4539f34 fix(runtime): wire workbench matching relation port`.
- Worktree is clean before deploy.
- Row237 local verification passed:
  - `py_compile` for `runtime_worker_handlers.py`;
  - targeted runtime boundary guard;
  - `tests.test_workbench_matching_orchestrator`;
  - docs verify;
  - diff checks.

## Allowed Operations

- Run the repository deploy script from clean `dev`.
- Use root SSH for non-secret post-deploy status, health, readiness, DB aggregate and bounded log checks.
- Read systemd status for API, dispatcher and `fin-ops-worker@workbench-matching.service`.
- Query production runtime aggregate facts through existing deployed configuration without printing secrets.

## Forbidden Operations

- Printing env files, DSNs, passwords, tokens, cookies, private keys or secret env values.
- Direct DB mutation.
- Queue requeue/resolve/repair.
- Worker replay or broad queue consume.
- Readiness mutation.
- Historical dead-letter cleanup.

## Deploy Command

From `/Users/yu/Desktop/fin-ops-platform`:

```bash
./scripts/deploy-oa.sh --release-name dev-workbench-matching-port-20260625020818
```

## Post-Deploy Evidence Commands

1. Active release identity:

```bash
ssh finops-prod-root 'systemctl show fin-ops.service -p ActiveState -p SubState -p Result -p NRestarts -p ExecMainStatus -p WorkingDirectory --value'
```

2. Workbench matching worker stability:

```bash
ssh finops-prod-root 'systemctl show fin-ops-worker@workbench-matching.service -p ActiveState -p SubState -p Result -p NRestarts -p ExecMainStatus -p MainPID --value'
sleep 15
ssh finops-prod-root 'systemctl show fin-ops-worker@workbench-matching.service -p ActiveState -p SubState -p Result -p NRestarts -p ExecMainStatus -p MainPID --value'
```

3. Health endpoints:

```bash
curl -fsS --max-time 5 https://www.yn-sourcing.com/fin-ops-api/health
curl -fsS --max-time 8 https://www.yn-sourcing.com/fin-ops-api/health/ready
```

4. Read-only runtime aggregates:

Use a deployed-runtime Python/psql wrapper that reads existing runtime configuration without printing DSNs. Collect only:

- `job.outbox_events` status counts;
- `job.read_model_dirty_scopes` status counts;
- `read_model.app_status_readiness` status counts;
- non-done dirty scope samples if any;
- worker problem samples from `/health/ready` if any.

5. Workbench matching logs:

```bash
ssh finops-prod-root 'journalctl -u fin-ops-worker@workbench-matching.service --since "10 minutes ago" --no-pager | grep -E "WorkbenchMatchingOrchestrator|pair_relation_service|TypeError|Traceback" || true'
```

## Expected Evidence

- Active release is `dev-workbench-matching-port-20260625020818`.
- Active release git commit is the clean `dev` HEAD used for deploy; code fix commit `b4539f343f6774a3f6659dcc1a03f73fdff44740` is included in its ancestry.
- `fin-ops-worker@workbench-matching.service` is `active/running`.
- `NRestarts` for `fin-ops-worker@workbench-matching.service` is stable across the 15s recheck.
- `/health` and `/health/ready` return ready.
- No active non-done dirty scopes.
- App Status readiness remains fresh for current rows.
- No new constructor `TypeError` or `pair_relation_service` traceback appears after deploy.

## Rollback

If deploy fails before activation, stop and preserve deploy output.

If activation succeeds but readiness or the worker regresses with a new blocker, roll back to the previous known active release:

```bash
ssh finops-prod-root 'systemctl show fin-ops.service -p WorkingDirectory --value'
```

Then use the repository/deploy runbook rollback path for the previous release. Do not perform manual DB or queue mutation as rollback.

## Stop Gates

- Deploy command exits non-zero.
- Active release identity does not match the requested release.
- `/health/ready` is not ready after deploy.
- `fin-ops-worker@workbench-matching.service` remains `activating/auto-restart` or `NRestarts` keeps rising after deploy.
- Logs show a new non-constructor error requiring diagnosis.
- Any post-check would require printing secrets or mutating DB/queue/readiness.

## Execution Results

Executed from clean `dev` at `b256db3a8fc370ce93e7b51bf62b1cd33176475d`.

### Deploy

- Command: `./scripts/deploy-oa.sh --release-name dev-workbench-matching-port-20260625020818`.
- Exit code: `0`.
- Frontend build completed. Vite emitted the same existing CSS minify warnings around generated `:is()` / `:not(:is())` selectors; build still completed.
- Deploy helper completed release activation, backend readiness, status, runtime worker ensure, frontend hash check, public session route check and old release cleanup.

### Active Release

- Release: `dev-workbench-matching-port-20260625020818`.
- Git commit: `b256db3a8fc370ce93e7b51bf62b1cd33176475d`.
- Working directory: `/opt/fin-ops/releases/dev-workbench-matching-port-20260625020818/src`.
- `/health`: HTTP 200, `status=ready`, release metadata consistent, production runtime guard consistent.
- `/health/ready`: HTTP 200, `status=ready`.

### Worker Stability

Initial post-deploy systemd check:

- `fin-ops.service`: `active/running`, `NRestarts=0`, working directory new release.
- `fin-ops-rabbitmq-dispatcher.service`: `active/running`, `NRestarts=0`, working directory new release.
- `fin-ops-worker@workbench-matching.service`: `active/running`, `MainPID=3380166`, `NRestarts=0`, `ExecMainStatus=0`, working directory new release.

15 second stability recheck:

- `fin-ops-worker@workbench-matching.service`: still `active/running`.
- `MainPID` remained `3380166`.
- `NRestarts` remained `0`.
- `ExecMainStatus` remained `0`.

### Runtime Aggregates

Read-only deployed-runtime PostgreSQL aggregate:

- `job.outbox_events`: `done=203145`, `dead_lettered=24`.
- `job.read_model_dirty_scopes`: `done=187007`.
- `read_model.app_status_readiness`: `fresh=498`.
- Active dirty scope samples: `[]`.
- Non-fresh readiness samples: `[]`.
- Historical dead-letter classification remained unchanged:
  - `no_oa_bank_batch.read_model.refresh all`: 13 rows;
  - `pending_invoice.read_model.refresh expense:all:2026-05`: 1 row;
  - Workbench read-model refresh rows for `2025-04`, `2025-09`, `2025-11`, `2025-12`, `2026-01`, `2026-02`, `2026-03`, `2026-04`, `2026-05`, `2026-06`: 10 rows.

`/health/ready` runtime summary:

- `queue_backlog={}`.
- `dirty_scopes={"done": 187007}`.
- `failed_jobs=0`.
- `stale_dirty_scope_count=0`.
- required worker missing/stale/mismatch counts all `0`.
- RabbitMQ queue depth, unacked and DLQ counts all `0`.
- `worker_status_counts={"available": 21}`.
- Remaining worker problem samples are old non-required stale/mismatch worker rows, not current required worker blockers.

### Log Evidence

`journalctl -u fin-ops-worker@workbench-matching.service --since "2026-06-25 02:10:20"` with grep for `WorkbenchMatchingOrchestrator|pair_relation_service|TypeError|Traceback` returned no lines.

The broader 10-minute log grep still shows the pre-deploy constructor loop from `02:01` through `02:09`; no matching constructor traceback appears after the new release activation at about `02:10`.

## Conclusion

`production:workbench-matching-constructor-fix-deploy-and-convergence-runbook` is `production-controlled`: the code fix is deployed, the `workbench-matching` systemd worker is stable with `NRestarts=0`, health/readiness are ready, runtime aggregates have no active dirty or non-fresh rows, and the constructor `TypeError` no longer appears after deploy.

No DB writes, requeue, resolve, repair, worker replay, readiness mutation, historical dead-letter cleanup or secret output occurred in this boundary.

Next boundary: `planning:post-workbench-matching-production-convergence-next-boundary-selection`.
