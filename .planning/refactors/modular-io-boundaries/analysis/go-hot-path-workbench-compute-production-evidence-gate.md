# Go Hot Path Workbench Compute Production Evidence Gate

**Date:** 2026-06-24
**Boundary:** `go-hot-path:workbench-compute-production-evidence-gate`
**Slice status:** `production-evidence-deferred`
**Module closure:** `go-admission-not-started`

## Goal

Run or explicitly defer the read-only Workbench compute production/runtime evidence path before any `workbench:matching-grouping-check` Go admission review.

This slice does not implement Go, Go Fiber or Go Worker, and does not change canonical Python runtime behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-baseline-contract.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-python-reference-contract-guards.md`
- `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-evidence-collector-contract.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/reconciliation-workbench/implementation-notes.md`
- `docs/operations/runtime-worker-governance.md`
- `backend/src/fin_ops_platform/tools/workbench_compute_evidence.py`
- `tests/test_workbench_compute_evidence.py`

## Execution Evidence

Preflight:

- Local branch was `dev`.
- `origin/dev` was already up to date.
- `origin/main` merged into `dev` with `Already up to date`.
- No worktree changes existed before the slice.

Local collector run:

```bash
env -u FIN_OPS_POSTGRES_DATABASE_URL -u DATABASE_URL \
  PYTHONPATH=backend/src \
  python3 -m fin_ops_platform.tools.workbench_compute_evidence --json
```

Result:

- Exit code: `2`
- `status`: `configuration_missing`
- `blocking_condition`: `database_url_required`
- `production_evidence_required`: `true`
- Required env names: `FIN_OPS_POSTGRES_DATABASE_URL`, `DATABASE_URL`

This is expected local evidence only. It is not an admission pass.

Production read-only SSH discovery:

- `ssh finops-prod-root` succeeded as root on host `VM-0-6-opencloudos`.
- `/usr/local/sbin/finops-deploy-control status` was available and returned active app/worker status.
- `workbench-matching`, `workbench-relation`, `workbench` and other runtime workers were reported active by the deploy-control status output.
- `/opt/fin-ops/current` was absent.
- The active release working directory was `/opt/fin-ops/releases/main-bf4405fb-20260623194934/src`.
- The deployed release did not contain `backend/src/fin_ops_platform/tools/workbench_compute_evidence.py`.
- The deployed release did contain `fin_ops_platform.tools.runtime_worker_manifest`, and the required instance list included `workbench-matching`.

Production read-only SQL sampling attempt:

- A read-only Python sampling script used the deployed venv, deployed `PostgresConnection`, deployed source path and existing runtime env files.
- The script guarded SQL against mutating verbs and contained only SELECT aggregation queries.
- No secret values, DSNs, tokens, cookies, private keys or payload bodies were printed or written to repository files.
- The attempt could not establish a database connection. The observed error was:

```text
connection to server at "127.0.0.1", port 5432 failed: FATAL: could not open shared memory segment
```

- The command was interrupted after repeated connection failures. No production writes, deploys, service restarts, requeues, readiness mutations, dirty-scope acknowledgements or repair apply actions were performed.

## Decision

The production/runtime Workbench compute evidence gate is `production-evidence-deferred`.

Reasons:

1. The local environment has no PostgreSQL URL, so the collector can only return structured `configuration_missing`.
2. The current production release does not include the newly added `workbench_compute_evidence` collector.
3. Running the collector on production would require deployment or copying code, both outside this slice.
4. A no-write deployed-runtime SQL sampling attempt failed to connect to PostgreSQL, so required p95/p99, row-count, candidate/decision, heartbeat, query timing and enqueue-to-fresh evidence could not be safely collected in this run.

## Required Evidence Still Missing

- Workbench matching worker p95/p99 duration by scope and by batch.
- Claimed/processed/failed/stale-completed scope counts with live dirty-scope lag.
- OA/bank/invoice/active-relation/held-row counts per scope from active generation.
- Candidate/decision paired/open/conflict/expired/suppressed/auto-completed counts.
- `workbench-matching` heartbeat lag from live PostgreSQL.
- Query timing evidence for row provider, active relation reads and decision/candidate persistence.
- Workbench active generation enqueue-to-fresh p95/p99 after matching invalidation.
- Shadow diff evidence on representative high-row months.
- Rollback gate proof for any future Go implementation.

## State Machine Impact

- `go-hot-path:workbench-compute-production-evidence-gate` transitions from `pending` to `production-evidence-deferred`.
- `go-hot-path:workbench-compute-admission` remains `blocked-by-prerequisite`.
- Go/Fiber/Go Worker implementation remains blocked.
- Insert `planning:post-workbench-compute-evidence-gate-next-boundary-selection` as the next pending planning slice. Its job is to select the next safe non-blocked boundary from the existing roadmap and queue, because all current Go admission rows remain blocked.
- Global state-machine definitions are unchanged; existing `production-evidence-deferred` and Go admission blocking semantics already cover this slice.
- Module state-machine definitions are unchanged; this slice does not change Workbench business state, API shape, UI behavior or canonical runtime ownership.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No matching, grouping, relation, amount, permission or status business rule changed. |
| 2. Service-layer tests | Not applicable | No service or repository runtime behavior changed. |
| 3. API contract tests | Not applicable | No HTTP/API contract changed. |
| 4. Read model/cache/background job tests | Applicable | Existing `workbench_compute_evidence` tests and platform guard tests remain the local evidence that the tool is read-only and admission stays blocked when production evidence is missing. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Deferred | Real production/staging-like Workbench performance and shadow evidence remains unavailable in this run. |
| 7. Existing feature regression tests | Applicable | Platform guard regression is updated to require the production evidence gate to be deferred and Go admission to remain blocked. |

## Verification

Targeted verification for this slice:

```bash
env -u FIN_OPS_POSTGRES_DATABASE_URL -u DATABASE_URL \
  PYTHONPATH=backend/src \
  python3 -m fin_ops_platform.tools.workbench_compute_evidence --json

PYTHONPATH=backend/src python3 -m unittest \
  tests.test_workbench_compute_evidence \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded \
  -v

bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- Production PostgreSQL connectivity for read-only evidence collection failed during this slice; this may be a transient server/runtime issue or an environment constraint.
- Because the current production release lacks the collector, a future deployed release or approved runtime wrapper is required before the exact collector can run against production.
- Go/Fiber/Go Worker implementation remains blocked until performance evidence, shadow comparison and rollback gates are satisfied.
