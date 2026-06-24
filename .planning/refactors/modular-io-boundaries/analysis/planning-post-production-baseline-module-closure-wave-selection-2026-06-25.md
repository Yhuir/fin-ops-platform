# Planning Post Production Baseline Module Closure Wave Selection 2026-06-25

**Boundary:** `planning:post-production-baseline-module-closure-wave-selection`
**Final status:** `planning-closed`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `1d6e8ff87b721145ed6c4151d6819f225f8bc774`

## Inputs Reviewed

- `analysis/production-post-dead-letter-resolution-global-readiness-worker-db-evidence-sweep-2026-06-25.md`
- `analysis/planning-post-historical-dead-letter-resolution-next-boundary-selection-2026-06-25.md`
- `analysis/commit-backed-state-reconciliation-2026-06-25.md`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/STATE.md`
- `autonomous/JOURNAL.md`
- `autonomous/NEXT-PROMPT.md`
- `12-PARALLEL-ORCHESTRATION.md`

## Current Evidence

Row243 gives a clean global production baseline:

- `/health` and `/health/ready` are ready and release-consistent.
- Required worker missing/stale/mismatch counts are all `0`.
- API, dispatcher and 20 worker units are active/running with `NRestarts=0` across a stability recheck.
- Queue backlog is empty.
- `job.outbox_events` has only `done=203169`.
- No read-model dead-letter groups remain.
- `job.read_model_dirty_scopes` has only `done=187007`.
- `read_model.app_status_readiness` has only `fresh=498`.
- Covered dead-letter dry-run has zero candidates.
- Recent worker error grep returned no matches.

This removes the latest global production-health blocker, but it does not prove individual module closure. It does not by itself prove module-specific production row coverage, high-row behavior, browser behavior, API response contracts, source-version correctness or Go admission.

## Deferred Rows Reconciled

The queue still has many `production-evidence-deferred` rows. The active candidates for a module-specific evidence wave include:

- `bank-details:auto-tag-category-boundary`
- `batch-accounting:module-closure-audit-and-production-evidence-defer`
- `read-models:bank-detail-service-factory-collaborator-closure-audit`
- `workbench-relations:final-local-implementation-closure-and-production-evidence-defer`
- `read-models:pending-invoice-local-implementation-closure-audit`
- `read-models:oa-pending-payment-local-implementation-closure-audit`
- `read-models:input-invoice-usage-local-implementation-closure-audit`
- `read-models:output-invoice-collection-local-implementation-closure-audit`
- `read-models:invoice-lifecycle-local-implementation-closure-audit`
- `read-models:tax-offset-post-full-state-local-implementation-closure-audit`
- `read-models:cost-statistics-post-full-state-local-implementation-closure-audit`
- `read-models:turnover-ledger-local-implementation-closure-audit`
- `read-models:no-oa-bank-batch-post-full-state-local-implementation-closure-audit`
- `read-models:search-post-all-scope-worker-fanout-local-implementation-closure-audit`
- `read-models:bank-account-balance-local-implementation-closure-audit`
- `go-hot-path:workbench-compute-production-evidence-gate`

Older production incident rows for readiness timeouts, PostgreSQL shared memory, no-OA dead letters and workbench-matching restart loops are now superseded by later controlled fixes and the clean row243 baseline. They should remain historical evidence rows, not be retroactively treated as full module closure.

## Candidate Waves Considered

| Candidate | Decision | Reason |
| --- | --- | --- |
| Final global closure audit | Rejected | Module closure remains unproven; many rows are still `not-module-closed` or `implementation-gap-open`. |
| Go admission or implementation | Rejected | Go remains blocked by missing candidate-specific performance, shadow diff and rollback evidence. |
| Browser/high-row smoke wave | Deferred | Useful later, but the first gap is production DB/readiness/scope/source-version matrix evidence across read models. |
| Worker-thread module docs audits | Deferred | Independent worker audits can follow, but production DB evidence is T0-controlled and should establish the facts first. |
| T0-only read-model production evidence matrix | Selected | It is read-only, uses the clean production baseline, and directly addresses the largest cluster of `production-evidence-deferred` read-model rows. |

## Selected Next Boundary

`production:read-model-production-evidence-matrix-read-only-sweep`

The boundary should collect non-secret read-only production evidence for the registered read models:

- readiness counts by read model, scope type and status;
- dirty-scope counts by read model/scope and status;
- outbox read-model event counts by event type/status and recent activity windows;
- read-model row-count/high-row signals where table ownership is known and queries are safe;
- source-version/status samples where already exposed through existing readiness/read-model tables or deployed-runtime helpers;
- worker unit/heartbeat coverage mapped to the read-model keys;
- explicit gaps that remain for browser/API/high-row closure.

The boundary must not mutate production. It should not claim closure for a module unless the evidence directly proves that module's closure criteria. The expected output is an evidence matrix and a next selection: either a focused module closure audit, a browser/API smoke boundary, or a worker-audit wave for independent modules.

## Parallelism Decision

Do not spawn workers yet. The next boundary is T0-only because it uses production root SSH and deployed-runtime PostgreSQL evidence. After the matrix exists, T0 can safely create independent worker prompts for module-specific non-production audits or browser/API smoke planning if the file ownership scopes do not overlap.

## Docs Impact

No long-term docs update is required in this planning slice. It selects the next evidence boundary and does not change runtime behavior, API contracts, worker state definitions, read model scope policy, permissions or UI behavior.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business logic changed. |
| 2. Service-layer tests | Not applicable | No service/repository/worker code changed. |
| 3. API contract tests | Not applicable | No HTTP contract changed. |
| 4. Read model/cache/background job tests | Not applicable | Planning-only slice; the selected next boundary will collect production read model matrix evidence. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No cross-module business flow changed. |
| 7. Existing feature regression tests | Not applicable | Planning/accounting only; no runtime surface changed. |

## Verification

This slice is docs/accounting only. Required verification:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Decision

Mark row244 `planning-closed` and add row245:

`production:read-model-production-evidence-matrix-read-only-sweep`

No global/module closure is claimed.
