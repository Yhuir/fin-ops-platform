# Planning Post Workbench Matching Production Convergence Next Boundary Selection 2026-06-25

**Boundary:** `planning:post-workbench-matching-production-convergence-next-boundary-selection`
**Final status:** `planning-closed`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `35c2f6cfa784098caf55d7fc27e38e58f93cd01e`

## Inputs Reviewed

- `analysis/production-post-convergence-readiness-worker-db-aggregate-evidence-sweep-2026-06-25.md`
- `analysis/runtime-workers-workbench-matching-orchestrator-constructor-fix-2026-06-25.md`
- `analysis/production-workbench-matching-constructor-fix-deploy-and-convergence-runbook-2026-06-25.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/STATE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`

## Latest Evidence

- no-OA FK blocker is fixed and converged:
  - exact event `3bc506fd-5662-4902-a9b9-19b0d8fbe4a6` is `done`;
  - `no_oa_bank_batch:all` dirty scope is `done`;
  - no-OA readiness is `fresh`.
- Workbench matching constructor blocker is fixed and deployed:
  - release `dev-workbench-matching-port-20260625020818`;
  - release commit `b256db3a8fc370ce93e7b51bf62b1cd33176475d`;
  - `fin-ops-worker@workbench-matching.service` stable with `NRestarts=0`;
  - no post-deploy constructor `TypeError`.
- Current production aggregate:
  - `/health` and `/health/ready` are ready;
  - `job.read_model_dirty_scopes` only has `done=187007`;
  - `read_model.app_status_readiness` only has `fresh=498`;
  - `job.outbox_events` has `done=203145` and historical `dead_lettered=24`;
  - no active dirty scope samples and no non-fresh readiness samples.

## Selection Rationale

The two current production blockers discovered by the T0 sweep are resolved:

1. The no-OA FK refresh blocker was fixed, deployed, and the exact failed event converged.
2. The workbench-matching worker restart loop was fixed, deployed, and the systemd unit is stable.

The remaining visible runtime residue is the unchanged set of historical `dead_lettered` rows. They are not current `/health/ready` blockers (`failed_jobs=0`, active dirty scopes empty, readiness all fresh), so they must not be cleaned opportunistically inside a planning or unrelated production boundary.

The next safe boundary is a read-only maintenance classification:

`production:historical-dead-letter-covered-resolution-read-only-maintenance-plan`

This boundary should classify the 24 dead-letter rows, run only dry-run/inspect style commands, prove whether each row is covered by later done/fresh readiness/no active dirty scope evidence, and produce a bounded apply-or-defer decision. It must not execute `resolve-covered-dead-letters --execute` or mutate DB/queue/readiness.

## Docs Impact

No long-term module docs change is required in this planning slice. It only selects the next T0 boundary and does not change runtime behavior, API contracts, worker state definitions, read model scope policy, permissions or UI behavior.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business logic changed. |
| 2. Service-layer tests | Not applicable | No service/repository/worker code changed in this planning slice. |
| 3. API contract tests | Not applicable | No HTTP contract changed. |
| 4. Read model/cache/background job tests | Not applicable | No read model or worker behavior changed; production evidence was reviewed only. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No cross-module runtime behavior changed. |
| 7. Existing feature regression tests | Not applicable | Planning/accounting only; no runtime surface changed. |

## Verification

- `git status --short --branch`
- `git rev-parse HEAD origin/dev`
- Reviewed latest production evidence files and queue rows.

## Decision

Mark row239 `planning-closed` and add row240:

`production:historical-dead-letter-covered-resolution-read-only-maintenance-plan`

No global/module closure is claimed.
