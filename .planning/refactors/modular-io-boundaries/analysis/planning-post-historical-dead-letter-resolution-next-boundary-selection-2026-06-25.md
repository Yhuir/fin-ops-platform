# Planning Post Historical Dead Letter Resolution Next Boundary Selection 2026-06-25

**Boundary:** `planning:post-historical-dead-letter-resolution-next-boundary-selection`
**Final status:** `planning-closed`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `c4e6da91a87ee8c8bdbf0c68d9f8482393e199c4`

## Inputs Reviewed

- `analysis/production-historical-dead-letter-covered-resolution-apply-runbook-2026-06-25.md`
- `analysis/production-historical-dead-letter-covered-resolution-read-only-maintenance-plan-2026-06-25.md`
- `analysis/production-workbench-matching-constructor-fix-deploy-and-convergence-runbook-2026-06-25.md`
- `analysis/commit-backed-state-reconciliation-2026-06-25.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/STATE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`
- `12-PARALLEL-ORCHESTRATION.md`

The analysis/handoff inventory currently contains 258 markdown files under the modular IO analysis and handoff folders. For this selection slice, T0 opened the files related to the selected production evidence path, current pending row, commit-backed baseline and controller orchestration rules.

## Current Evidence

The production blockers found during the latest T0 evidence loop have been addressed or reclassified:

- PostgreSQL shared-memory failure was recovered by the earlier controlled restart boundary.
- App, dispatcher and worker processes were restarted in a bounded controlled boundary and `/health/ready` returned ready afterward.
- The no-OA FK delete-order blocker was fixed, deployed and the exact failed `no_oa_bank_batch:all` event converged.
- The workbench-matching constructor mismatch was fixed, deployed and the worker stayed stable after deploy.
- Historical read-model dead-letter residue was resolved through the covered-dead-letter maintenance command:
  - pre-apply dry-run: `candidate_count=24`, `eligible_count=24`, `resolved_count=0`;
  - apply: `candidate_count=24`, `eligible_count=24`, `resolved_count=24`;
  - post-check: `job.outbox_events done=203169`, no `dead_lettered` rows, dead-letter groups empty;
  - dirty scopes remained `done=187007`;
  - readiness rows remained `fresh=498`;
  - `/health/ready` remained ready;
  - follow-up dry-run had zero candidates.

No global or module closure is proven by the residue cleanup alone. It only removes one known production evidence obstacle.

## Queue Reconciliation

Current queue facts after row 241:

- Total queue rows: `242`.
- First pending row: `242`, this planning boundary.
- Status counts:
  - `implementation-closed=107`;
  - `analysis-closed=72`;
  - `production-evidence-deferred=23`;
  - `planning-closed=12`;
  - `contract-guard-closed=10`;
  - `regression-guard-closed=4`;
  - `blocked-by-prerequisite=4`;
  - `static-guard-closed=3`;
  - `production-controlled=3`;
  - `route-guard-closed=1`;
  - `inventory-guard-closed=1`;
  - `go-candidate-deferred=1`;
  - `pending=1`.
- Module closure counts:
  - `implementation-gap-open=193`;
  - `not-module-closed=31`;
  - `go-admission-not-started=10`;
  - `not-applicable=8`.

The old commit-backed reconciliation file was produced before the later production-control sequence and remains useful as a baseline, but it cannot by itself classify the current post-cleanup production state. A fresh production read-only baseline is needed before any module-level production closure audit or worker wave can be credible.

## Candidate Boundaries Considered

| Candidate | Decision | Reason |
| --- | --- | --- |
| `planning:final-global-closure-audit` | Rejected | Module closure remains unproven; no product module has `Module Closure = closed`; production evidence, browser/high-row and Go admission gaps remain. |
| `go-hot-path:*` admission or implementation | Rejected | Go admission remains blocked by missing candidate-specific performance, shadow diff and rollback evidence. |
| Worker wave for module docs/contracts | Deferred | A worker wave can help later, but current highest risk is production evidence truth after several controlled production operations. |
| Module-specific production closure audit | Deferred | Before closing a specific module, T0 needs a current post-dead-letter global production baseline proving no active queue/readiness/worker residue remains. |
| `production:post-dead-letter-resolution-global-readiness-worker-db-evidence-sweep` | Selected | This is read-only, T0-owned, low risk, and directly advances the remaining production-evidence closure gap. |

## Selected Next Boundary

`production:post-dead-letter-resolution-global-readiness-worker-db-evidence-sweep`

The boundary should collect non-secret read-only evidence from the currently deployed production release after dead-letter cleanup:

- `/health` and `/health/ready` release identity and readiness summary;
- systemd status and stability samples for API, dispatcher and required read-model workers;
- deployed-runtime PostgreSQL aggregates for `job.outbox_events`, `job.read_model_dirty_scopes`, `read_model.app_status_readiness`;
- worker heartbeat/status samples as exposed by `/health/ready`;
- optional bounded log grep for recent errors in required worker units;
- confirmation that no active dirty scopes, non-fresh readiness rows, queue backlog or dead-letter groups remain.

This is an evidence sweep only. It must not deploy, restart, requeue, repair, mutate DB, mutate readiness, mutate dirty scopes, replay workers or print secrets.

## Docs Impact

No long-term docs update is required in this planning slice. It selects the next production evidence boundary and does not change runtime behavior, API contracts, worker state definitions, read model scope policy, permissions or UI behavior.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business logic changed. |
| 2. Service-layer tests | Not applicable | No service/repository/worker code changed. |
| 3. API contract tests | Not applicable | No HTTP contract changed. |
| 4. Read model/cache/background job tests | Not applicable | Planning-only slice; the selected next boundary will collect production read model and worker evidence. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No cross-module runtime behavior changed. |
| 7. Existing feature regression tests | Not applicable | Planning/accounting only; no runtime surface changed. |

## Verification

This slice is docs/accounting only. Required verification:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Decision

Mark row 242 `planning-closed` and add row 243:

`production:post-dead-letter-resolution-global-readiness-worker-db-evidence-sweep`

No global/module closure is claimed.
