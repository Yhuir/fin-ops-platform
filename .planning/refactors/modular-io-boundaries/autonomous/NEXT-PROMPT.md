# Next Prompt

Continue the autonomous modular IO refactor after the `go-hot-path:workbench-compute-performance-evidence-collector-contract` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `go-hot-path:workbench-compute-performance-evidence-collector-contract`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- Workbench compute Python reference IO, shadow-forbidden writes and rollback gates are documented and locally guarded.
- Read-only Workbench compute evidence collector tooling now exists at `backend/src/fin_ops_platform/tools/workbench_compute_evidence.py`.
- Go implementation remains blocked until real candidate-specific performance evidence, shadow-run comparison and admission review pass.

## Next Boundary

`go-hot-path:workbench-compute-production-evidence-gate`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-baseline-contract.md`
   - `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-python-reference-contract-guards.md`
   - `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-evidence-collector-contract.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/reconciliation-workbench/implementation-notes.md`
   - `docs/operations/runtime-worker-governance.md`
   - `backend/src/fin_ops_platform/tools/workbench_compute_evidence.py`
   - `tests/test_workbench_compute_evidence.py`

## Boundary Scope

Target:

- Run or explicitly defer the read-only Workbench compute evidence collection path in an approved deployed/runtime context.
- First run the collector locally without assuming `PGSQL_URL`; if configuration is missing, record the structured `configuration_missing` result as expected local evidence.
- If SSH production access is used, perform only read-only checks. Do not write secrets into files, docs, prompts, shell scripts or git history.
- Prefer an existing approved runtime wrapper/env on the server. Do not print database URLs or secret values.
- If no safe approved way exists to run the collector with production database connectivity, write an analysis file that records `production-evidence-deferred` and explains the missing runtime evidence.
- Required real evidence, if safely collectible:
  - Workbench matching worker p95/p99 duration by scope and by batch.
  - Claimed/processed/failed/stale-completed scope counts.
  - OA/bank/invoice/active-relation/held-row counts per scope.
  - Candidate/decision paired/open/conflict/expired/suppressed/auto-completed counts.
  - Dirty-scope lag and `workbench-matching` heartbeat.
  - Query timing evidence for row provider, active relation read and decision/candidate persistence where available.
  - Workbench active generation enqueue-to-fresh p95/p99 after matching invalidation.
- Do not perform production writes.
- Do not deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.
- Do not implement Go, Go Fiber or Go Worker.
- Do not change canonical Python runtime behavior.
- Keep `go-hot-path:workbench-compute-admission` blocked unless real evidence and shadow prerequisites are satisfied.

Expected verification:

- Local collector configuration-missing behavior if no local `PGSQL_URL` exists.
- If production evidence is safely collected, archive only sanitized JSON/report fields without secrets.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified Workbench compute production evidence gate slice: either sanitized read-only runtime evidence exists, or the evidence is explicitly marked `production-evidence-deferred` with reasons. Update state-machine accounting, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
