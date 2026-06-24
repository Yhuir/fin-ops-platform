# Production No-OA Bank Batch FK Fix Deploy And Convergence Runbook 2026-06-25

**Boundary:** `production:no-oa-bank-batch-fk-fix-deploy-and-convergence-runbook`
**Final status:** `production-controlled`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `0266ae0d4dbd27a955ee5e1067006d1c0ba1de37`

## Target Boundary

Deploy the no-OA FK delete-order fix and prove production convergence for the exact `no_oa_bank_batch:all` blocker identified in:

- `production-no-oa-bank-batch-dead-letter-read-only-diagnosis-2026-06-25.md`
- `read-model-no-oa-bank-batch-event-fk-delete-order-fix-2026-06-25.md`

## Controlled Operation Scope

Allowed operations, in order:

1. Run the repository-supported release deploy from a clean `dev` worktree:

```bash
./scripts/deploy-oa.sh --release-name dev-no-oa-fk-20260625014906
```

2. Collect non-secret post-deploy evidence:

- active release identity from `/health` and `/health/ready`;
- selected systemd unit status for API, dispatcher and `fin-ops-worker@no-oa-bank-batch.service`;
- read-only PostgreSQL evidence for `job.outbox_events`, `job.read_model_dirty_scopes`, `read_model.app_status_readiness`.

3. If and only if the exact pre-existing event is still `dead_lettered` and the exact dirty scope is still pending after deploy, requeue the latest exact no-OA event using the active release runtime env without printing secrets:

```bash
ssh finops-prod-root 'set -euo pipefail; release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"; cd "$release_src"; set -a; source /etc/fin-ops/fin-ops.common.env; source /etc/fin-ops/fin-ops.secrets.env; set +a; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops requeue --event-id 3bc506fd-5662-4902-a9b9-19b0d8fbe4a6 --reason no_oa_fk_delete_order_fix_deployed'
```

4. Wait for worker convergence and verify exact scope:

- latest `no_oa_bank_batch.read_model.refresh` for `no_oa_bank_batch:all` is `done`, or a later same-scope event is `done`;
- `job.read_model_dirty_scopes` for `no_oa_bank_batch:all` has no active `pending/processing/failed` row;
- `read_model.app_status_readiness` for `no_oa_bank_batch:all` is `fresh`;
- `/health/ready` returns `status=ready`;
- no new no-OA FK violation appears in selected worker logs.

## Forbidden

- Do not print env files, DSNs, passwords, tokens, cookies, private keys or secret env values.
- Do not manually `update`, `insert` or `delete` production DB rows.
- Do not mark dirty scopes done by hand.
- Do not delete dead-letter rows.
- Do not run broad queue replay, broad worker consume/replay, arbitrary repair tools or `--apply` repair commands.
- Do not deploy from a dirty worktree or with `--allow-dirty`.
- Do not force push or deploy `main`.

## Stop Gates

Stop before deploy if:

- local branch is not clean `dev`, local `HEAD` is not aligned with `origin/dev`, or the no-OA FK delete-order fix commit is not present;
- `origin/dev` does not match local `HEAD`;
- `bash scripts/verify.sh docs`, targeted tests or `git diff --check` fail;
- deploy would require secrets in local output.

Stop after deploy and classify `needs-human-production-gate` if:

- `./scripts/deploy-oa.sh` fails in check-release/activate/readiness/status/worker ensure;
- `/health` or `/health/ready` cannot prove the active release identity;
- API, dispatcher or no-OA worker does not return `active/running`;
- the exact requeue command would require exposing secrets or running arbitrary SQL;
- requeue fails and no later same-scope done event covers the blocker.

## Rollback / Cleanup Posture

The release deploy helper keeps previous releases. If activation fails, the deploy helper stops at its failing step and reports the step. Do not perform ad hoc rollback in this boundary unless the helper documents and executes it. Preserve non-secret evidence and stop.

The exact event requeue is recoverable because it only returns one existing dead-lettered event to the queue for the same read-model scope after deploying the code fix. If it dead-letters again, stop with evidence; do not retry repeatedly or manually mutate readiness.

## Pre-Deploy Verification

Already passed before writing this runbook:

```bash
PYTHONPATH=backend/src pytest tests/test_postgres_repositories_boundaries.py -q
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_read_model_refresh -v
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/workbench.py
bash scripts/verify.sh docs
git diff --check
git diff --cached --check
```

## Evidence Results

Executed at approximately `2026-06-25T01:50-01:55+08:00`.

### Deploy

Command:

```bash
./scripts/deploy-oa.sh --release-name dev-no-oa-fk-20260625014906
```

Result:

- Exit code `0`.
- Frontend build completed. Vite emitted existing CSS minify warnings for generated selectors such as `:is()` / `:not(:is())`, but did not fail the build.
- Release upload/check/activate completed.
- PostgreSQL migrations were checked and skipped/applied according to schema history; no migration failure.
- Deploy helper reported:
  - backend readiness check passed;
  - deploy-control status passed;
  - runtime worker ensure passed;
  - frontend hash check passed;
  - public session route check passed;
  - cleanup old releases deleted `workbench-source-linked-promotion-clean-05a9a878-20260623125034`.

Active release evidence:

```text
release_name=dev-no-oa-fk-20260625014906
git_commit=cc43e262eeb13c1a459d0f96e991666d0db2f280
working_directory=/opt/fin-ops/releases/dev-no-oa-fk-20260625014906/src
release_consistent=True
production_runtime_guard_consistent=True
```

Selected unit evidence:

```text
fin-ops.service active/running MainPID=3361103 NRestarts=0
fin-ops-rabbitmq-dispatcher.service active/running MainPID=3361285 NRestarts=0
fin-ops-worker@no-oa-bank-batch.service active/running MainPID=3364218 NRestarts=0
```

### Pre-Requeue Post-Deploy State

After deploy, `/health/ready` returned `status=ready` but still reported the old exact blocker:

```text
queue_backlog={'dead_lettered': 1}
dirty_scopes={'done': 187006, 'pending': 1}
failed_jobs=1
stale_dirty_scope_count=1
```

Read-only PostgreSQL proof showed the exact event remained dead-lettered and the exact dirty scope remained pending:

```text
event_id=3bc506fd-5662-4902-a9b9-19b0d8fbe4a6
status=dead_lettered
attempts=5
source_version=35430

dirty_scope no_oa_bank_batch:all status=pending source_version=35430
readiness no_oa_bank_batch:all status=failed source_versions={"source_version": 35430}
```

### Exact Requeue

Command:

```bash
ssh finops-prod-root 'set -euo pipefail; release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"; cd "$release_src"; set -a; source /etc/fin-ops/fin-ops.common.env; source /etc/fin-ops/fin-ops.secrets.env; set +a; PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops requeue --event-id 3bc506fd-5662-4902-a9b9-19b0d8fbe4a6 --reason no_oa_fk_delete_order_fix_deployed'
```

Result:

```json
{"event_id": "3bc506fd-5662-4902-a9b9-19b0d8fbe4a6", "requeued": true}
```

No env values or secret values were printed; only command output JSON was recorded.

### Convergence Proof

The exact requeued event converged:

```text
event_id=3bc506fd-5662-4902-a9b9-19b0d8fbe4a6
status=done
attempts=1
source_version=35430
processed_at=2026-06-25 01:52:57.111992+08
dead_lettered_at=null
last_error=null
```

Dirty scope and readiness:

```text
job.read_model_dirty_scopes active status count: 0 rows
no_oa_bank_batch:all dirty scope status=done source_version=35430 updated_at=2026-06-25 01:52:57.100896+08
read_model.app_status_readiness no_oa_bank_batch:all status=fresh source_versions={"source_version": 35430} updated_at=2026-06-25 01:52:57.10766+08
```

`/health/ready` after convergence:

```text
HTTP=200 TIME=0.532098
status=ready
queue_backlog={}
dirty_scopes={'done': 187007}
failed_jobs=0
stale_dirty_scope_count=0
missing_required_worker_count=0
stale_required_worker_count=0
mismatched_required_worker_count=0
worker_status_counts={'available': 21}
pending_outbox_events_by_scope_summary={"count": 0, "samples": []}
dirty_scopes_by_scope_summary={"count": 0, "samples": []}
stale_dirty_scopes_summary={"count": 0, "samples": []}
```

No-OA worker log grep since deploy found no new `dead`, `foreign key`, `no_oa_bank_batch_events_no_oa`, `PoolTimeout`, `FATAL`, `Failed with result` or `Main process exited` lines in the sampled output.

### Covered Dead-Letter Dry-Run

After convergence, `runtime_queue_ops resolve-covered-dead-letters --limit 20 --dry-run` showed 20 eligible obsolete dead letters, including older `no_oa_bank_batch:all` events now covered by fresh readiness and a later done event. The candidate set also included Workbench dead letters, so T0 did not execute this broad cleanup inside the no-OA boundary.

Read-only aggregate still shows historical dead-lettered rows:

```text
job.outbox_events status in active/problem set:
dead_lettered=24
```

They are not current blockers in `/health/ready`; cleanup is a separate bounded maintenance boundary if needed.

## Result Classification

`production-controlled`.

Reason:

- The no-OA FK delete-order fix was deployed to production release `dev-no-oa-fk-20260625014906`.
- The exact dead-lettered event was requeued once after deployment and processed successfully.
- `no_oa_bank_batch:all` dirty scope is done, readiness is fresh and `/health/ready` has no active queue/dirty/failed/stale blockers.
- No broad DB mutation, broad replay, manual mark-done, repair `--apply`, secret output or arbitrary SQL mutation was performed.

## Remaining Risk

- Historical obsolete `dead_lettered` rows remain in `job.outbox_events`, but they are not current `/health/ready` blockers after convergence.
- This row proves the no-OA production blocker is converged; it does not prove every product module has global closure evidence.

## Next Safe Boundary

```text
planning:post-no-oa-production-convergence-next-boundary-selection
```
