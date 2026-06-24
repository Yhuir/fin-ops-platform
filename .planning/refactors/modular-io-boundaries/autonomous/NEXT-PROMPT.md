# Next Prompt

Continue after the `production:no-oa-bank-batch-fk-fix-deploy-and-convergence-runbook` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `production:no-oa-bank-batch-fk-fix-deploy-and-convergence-runbook`
- Last status: `production-controlled`
- Queue semantics remain corrected: slice status is not module closure.
- Controller-only files are defined in `12-PARALLEL-ORCHESTRATION.md`.
- No product module has `Module Closure = closed`; production evidence and Go admission still need commit-backed reconciliation before any global closure claim.
- Deployed production release: `dev-no-oa-fk-20260625014906`.
- Active production release commit: `cc43e262eeb13c1a459d0f96e991666d0db2f280`.
- Production convergence evidence file: `analysis/production-no-oa-bank-batch-fk-fix-deploy-and-convergence-runbook-2026-06-25.md`.
- No-OA exact event `3bc506fd-5662-4902-a9b9-19b0d8fbe4a6` was requeued once after deploy and processed `done`.
- `no_oa_bank_batch:all` dirty scope is `done` at source version `35430`.
- `read_model.app_status_readiness` for `no_oa_bank_batch:all` is `fresh`.
- `/health/ready` returned `status=ready`, `queue_backlog={}`, `failed_jobs=0`, `stale_dirty_scope_count=0`, and no active dirty scope summaries.
- Historical obsolete `dead_lettered` rows remain in `job.outbox_events`; they are not current `/health/ready` blockers. Do not clean them without a separate bounded maintenance boundary.

## Next Boundary

`planning:post-no-oa-production-convergence-next-boundary-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Read:
   - `analysis/commit-backed-state-reconciliation-2026-06-25.md`
   - `analysis/production-no-oa-bank-batch-fk-fix-deploy-and-convergence-runbook-2026-06-25.md`
   - `MODULE-QUEUE.md`
   - `STATE.md`
   - `JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Reconcile latest evidence from rows 231-234 into the current progress baseline.
5. Select the next highest-risk safe boundary. Do not claim global closure unless commit-backed reconciliation proves all module closure requirements, production/App Status/worker/browser/high-row evidence and Go admission rules are satisfied.

## Guidance

- Do not repeat the PostgreSQL restart, app/worker restart, no-OA deploy or exact event requeue unless new evidence shows regression.
- Do not execute broad `resolve-covered-dead-letters --execute` from the no-OA boundary; the dry-run included Workbench and other obsolete events, so any cleanup must be separately scoped.
- If the next boundary is production-facing, write a controlled runbook first.
- If the next boundary is code/docs/tests, use normal local verification and avoid production mutation.

## Stop Condition

Proceed only through the T0 controller workflow. Do not run several master controllers against `dev` without the controller/worker permissions and write lease from `12-PARALLEL-ORCHESTRATION.md`.
