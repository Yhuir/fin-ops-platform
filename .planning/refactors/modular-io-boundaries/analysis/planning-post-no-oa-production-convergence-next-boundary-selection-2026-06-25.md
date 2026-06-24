# Planning Post No-OA Production Convergence Next Boundary Selection 2026-06-25

**Boundary:** `planning:post-no-oa-production-convergence-next-boundary-selection`
**Final status:** `planning-closed`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `a9982d4db1a51ef30ca1fd1d1a6051fc2ff6d704`

## Evidence Reviewed

- `production-app-worker-controlled-restart-readiness-runbook-2026-06-25.md`
- `production-no-oa-bank-batch-dead-letter-read-only-diagnosis-2026-06-25.md`
- `read-model-no-oa-bank-batch-event-fk-delete-order-fix-2026-06-25.md`
- `production-no-oa-bank-batch-fk-fix-deploy-and-convergence-runbook-2026-06-25.md`
- Current `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md` and `NEXT-PROMPT.md`

## Current Facts

- PostgreSQL shared-memory failure was recovered by the controlled PostgreSQL restart.
- API, dispatcher and worker stale process loops were recovered by the controlled app/worker restart.
- The no-OA FK delete-order bug was fixed locally, deployed and converged in production.
- `/health/ready` after no-OA convergence reported:
  - `status=ready`
  - `queue_backlog={}`
  - `failed_jobs=0`
  - `stale_dirty_scope_count=0`
  - no active dirty scope summaries
  - required worker missing/stale/mismatch counts all `0`
- Historical obsolete `dead_lettered` rows remain in `job.outbox_events`, but they are not current `/health/ready` blockers.

## Selection

Next boundary:

```text
production:post-convergence-readiness-worker-db-aggregate-evidence-sweep
```

## Rationale

The last several T0 boundaries changed production runtime state materially: PostgreSQL restart, app/worker restart, deployment and exact event requeue. Before selecting more code work or claiming any additional module closure, T0 needs a read-only post-convergence production baseline across:

- release identity;
- systemd API/dispatcher/required worker status;
- `/health` and `/health/ready`;
- PostgreSQL queue/dirty/readiness aggregates;
- no-OA exact scope;
- historical dead-letter classification.

This is safer than immediately cleaning obsolete dead letters because the dry-run candidate set includes Workbench and other scopes beyond the no-OA boundary. Any cleanup must be separately scoped after the aggregate sweep proves whether those rows matter.

## Stop Gates For Next Boundary

- Read-only only: no DB writes, requeue, resolve, repair, deploy, restart or readiness mutation.
- No secret/env/DSN output.
- If aggregate evidence shows new active blockers, select the narrowest diagnosis boundary rather than broad cleanup.
- If aggregate evidence is clean, use it to update production evidence accounting but do not claim global closure without commit-backed module closure reconciliation.
