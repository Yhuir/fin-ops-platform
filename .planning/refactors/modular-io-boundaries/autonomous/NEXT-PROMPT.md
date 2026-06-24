# Next Prompt

Continue after the `production:app-worker-controlled-restart-readiness-runbook` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `production:app-worker-controlled-restart-readiness-runbook`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- Parallel orchestration is controller-led.
- Worker prompts may auto-progress inside assigned workstreams, but they do not own global state or global closure.
- Controller-only files are defined in `12-PARALLEL-ORCHESTRATION.md`.
- No product module has `Module Closure = closed`; production evidence closure and Go admission remain incomplete.
- Commit-backed reconciliation report: `analysis/commit-backed-state-reconciliation-2026-06-25.md`.
- Boundary selection report: `analysis/planning-post-parallel-handoff-next-boundary-selection-2026-06-25.md`.
- Production readiness evidence file: `analysis/production-readiness-worker-status-controlled-read-only-2026-06-25.md`.
- PostgreSQL shared-memory evidence file: `analysis/production-postgres-shared-memory-read-only-diagnosis-2026-06-25.md`.
- PostgreSQL controlled restart evidence file: `analysis/production-postgres-controlled-restart-runbook-2026-06-25.md`.
- App/dispatcher/worker controlled restart evidence file: `analysis/production-app-worker-controlled-restart-readiness-runbook-2026-06-25.md`.
- PostgreSQL shared-memory recovery was proven by `/dev/shm/PostgreSQL.*` objects and active PostgreSQL post-checks.
- T0 restarted `fin-ops.service`, `fin-ops-rabbitmq-dispatcher.service` and 20 explicit `fin-ops-worker@*.service` units once.
- All selected runtime units returned `active/running` with `NRestarts=0`.
- `/health/ready` recovered from timeout and returned `status=ready` in `2.816792s` immediately after restart and `0.600410s` on stability recheck.
- Sampled post-restart logs showed no new `PoolTimeout`, missing shared-memory, `FATAL`, `Main process exited` or `Failed with result` lines after `2026-06-25T01:36:03+08:00`.
- Remaining production blocker: one stale `no_oa_bank_batch:all` dirty scope and one dead-lettered `no_oa_bank_batch.read_model.refresh` event with an FK violation:
  - `queue_backlog={'dead_lettered': 1}`
  - `dirty_scopes={'done': 187006, 'pending': 1}`
  - `failed_jobs=1`
  - `stale_dirty_scope_count=1`

## Next Boundary

`production:no-oa-bank-batch-dead-letter-read-only-diagnosis`

## Options

Recommended autonomous continuation:

- Use `prompts/06-t0-meta-orchestrator-goal.md`.
- Start exactly one T0 `/goal` thread.
- T0 will execute `production:no-oa-bank-batch-dead-letter-read-only-diagnosis`.
- T0 must collect non-secret read-only production evidence only.
- Do not requeue, mark done, delete rows, repair FK data, run worker replay, mutate readiness, deploy, restart services again or print secrets in this boundary.
- Do not create worker threads for this boundary; production evidence and controlled production gates are controller-owned.
- If the read-only diagnosis proves a safe exact-scope cleanup/requeue is required, create a later controlled production runbook boundary before any mutation.

Single-thread fallback:

- Use `prompts/04-master-goal-controller.md`.
- Start with `production:no-oa-bank-batch-dead-letter-read-only-diagnosis`.

Manual parallel fallback:

- Read `12-PARALLEL-ORCHESTRATION.md`.
- Manual T1-T9 startup is deprecated for unattended runs. Prefer T0-created worker threads from `06-t0-meta-orchestrator-goal.md`.
- Do not start workers for this production diagnosis unless T0 first converts it into a non-production code/docs/test boundary.

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read `analysis/commit-backed-state-reconciliation-2026-06-25.md`, `analysis/production-app-worker-controlled-restart-readiness-runbook-2026-06-25.md`, `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, this prompt, and `12-PARALLEL-ORCHESTRATION.md`.
5. Use the completed commit-backed audit as the progress baseline; do not recalculate from memory or raw row counts alone.
6. For the selected boundary, write or update a read-only diagnosis evidence file before using SSH for production evidence. Include exact commands, no-secret posture, stop gates, observed blocker shape and proposed next boundary.

## Stop Condition

Proceed only through either the single-thread controller or the controller-led parallel workflow. Do not run several master controllers against `dev` without the controller/worker permissions and write lease from `12-PARALLEL-ORCHESTRATION.md`.
