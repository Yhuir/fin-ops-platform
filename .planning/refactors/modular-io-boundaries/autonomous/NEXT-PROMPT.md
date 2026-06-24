# Next Prompt

Continue after the `read-models:no-oa-bank-batch-event-fk-delete-order-fix` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:no-oa-bank-batch-event-fk-delete-order-fix`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- Parallel orchestration is controller-led.
- Controller-only files are defined in `12-PARALLEL-ORCHESTRATION.md`.
- No product module has `Module Closure = closed`; production evidence closure and Go admission remain incomplete.
- Commit-backed reconciliation report: `analysis/commit-backed-state-reconciliation-2026-06-25.md`.
- App/dispatcher/worker controlled restart evidence file: `analysis/production-app-worker-controlled-restart-readiness-runbook-2026-06-25.md`.
- No-OA production dead-letter read-only diagnosis file: `analysis/production-no-oa-bank-batch-dead-letter-read-only-diagnosis-2026-06-25.md`.
- No-OA FK delete-order local fix file: `analysis/read-model-no-oa-bank-batch-event-fk-delete-order-fix-2026-06-25.md`.
- Production read-only diagnosis proved:
  - `/health/ready` is reachable and returns `status=ready`;
  - `no_oa_bank_batch:all` dirty scope remains pending at source version `35430`;
  - `read_model.app_status_readiness` for `no_oa_bank_batch:all` is failed;
  - 14 all-scope `no_oa_bank_batch.read_model.refresh` events dead-lettered on `app.no_oa_bank_batch_events_no_oa_bank_batch_id_fkey`;
  - the failed referenced `superseded` batch still exists and has 6 event rows.
- Local implementation fix:
  - `PostgresWorkbenchRepository.save_no_oa_bank_batches(...)` now deletes events for removed batches before deleting removed no-OA batch rows;
  - empty snapshot replacement deletes events before batches;
  - repository boundary regressions and no-OA refresh tests pass.
- Production still runs release `main-bf4405fb-20260623194934`, so the local fix is not yet production evidence.

## Next Boundary

`production:no-oa-bank-batch-fk-fix-deploy-and-convergence-runbook`

## Options

Recommended autonomous continuation:

- Use `prompts/06-t0-meta-orchestrator-goal.md`.
- Start exactly one T0 `/goal` thread.
- T0 must write a controlled production deploy/convergence runbook before any production deploy, requeue, repair, readiness mutation or worker replay.
- The runbook must include exact release/deploy command, pre/post checks, stop gates, rollback/cleanup posture, no-secret posture, and exact no-OA convergence verification.
- Prefer the existing production deploy entrypoint `./scripts/deploy-oa.sh` if the runbook proves it is the current repository-supported release path.
- If queue convergence requires mutation after deploy, use the narrowest exact-scope operation and prove why it is safe before executing it.
- Do not perform broad DB mutation, broad queue replay, manual mark-done, arbitrary repair, unbounded worker consume/replay or secret output.
- Do not create worker threads for this production boundary; production deploy/convergence gate is controller-owned.

Single-thread fallback:

- Use `prompts/04-master-goal-controller.md`.
- Start with `production:no-oa-bank-batch-fk-fix-deploy-and-convergence-runbook`.

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Read `analysis/production-no-oa-bank-batch-dead-letter-read-only-diagnosis-2026-06-25.md`, `analysis/read-model-no-oa-bank-batch-event-fk-delete-order-fix-2026-06-25.md`, `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, this prompt, `12-PARALLEL-ORCHESTRATION.md`, `docs/operations/runtime-worker-governance.md`, `deploy/oa/README.md`, and `scripts/deploy-oa.sh`.
4. Use the completed commit-backed audit as the progress baseline; do not recalculate from memory or raw row counts alone.
5. Write the controlled production deploy/convergence runbook before SSH production mutation. Include the exact no-OA post-deploy proof: `/health/ready`, selected systemd units, `job.outbox_events`, `job.read_model_dirty_scopes`, `read_model.app_status_readiness`, and no new dead-letter/error logs.

## Stop Condition

Proceed only through the T0 controller workflow. Do not run several master controllers against `dev` without the controller/worker permissions and write lease from `12-PARALLEL-ORCHESTRATION.md`.
