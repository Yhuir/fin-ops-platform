# Next Prompt

Continue the autonomous modular IO refactor after the `go-hot-path:workbench-compute-python-reference-contract-guards` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `go-hot-path:workbench-compute-python-reference-contract-guards`
- Last status: `static-guard-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- Workbench compute Python reference IO, shadow-forbidden writes and rollback gates are documented and now locally guarded.
- Go implementation remains blocked until candidate-specific performance evidence, shadow-run comparison and admission review pass.

## Next Boundary

`go-hot-path:workbench-compute-performance-evidence-collector-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-performance-baseline-and-admission-reconciliation.md`
   - `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-baseline-contract.md`
   - `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-python-reference-contract-guards.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/reconciliation-workbench/implementation-notes.md`
   - `docs/operations/runtime-worker-governance.md`
   - Existing SLO/performance tools under `backend/src/fin_ops_platform/tools/`
   - Runtime queue / Workbench dirty scope repository code and tests if collector tooling is added.

## Boundary Scope

Target:

- Define or add a read-only evidence collection contract/tooling path for Workbench compute performance.
- Required evidence fields:
  - worker p95/p99 duration by scope and by batch;
  - claimed/processed/failed/stale-completed scope counts;
  - OA/bank/invoice/active-relation/held-row counts per scope;
  - candidate/decision paired/open/conflict/expired/suppressed/auto-completed counts;
  - dirty-scope lag and `workbench-matching` heartbeat;
  - query timing evidence for row provider, active relation read and decision/candidate persistence where available;
  - Workbench active generation enqueue-to-fresh p95/p99 after matching invalidation;
  - explicit `configuration_missing` / `production_evidence_required` output when local `PGSQL_URL` or deployed runtime evidence is unavailable.
- Reuse existing SLO tooling conventions and fail-closed semantics before adding a new tool.
- If a tool is added, it must be read-only by default, must not require staging, and must have unit tests using fake connections/data.
- Do not perform production writes.
- Do not implement Go, Go Fiber or Go Worker in this slice.
- Do not change canonical Python runtime behavior.
- Keep `go-hot-path:workbench-compute-admission` blocked unless performance evidence and shadow prerequisites are satisfied.

Expected verification:

- Targeted tests for any added/changed evidence collector contract/tooling.
- Existing SLO tool tests if reused or extended.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified Workbench compute performance evidence collector contract/tooling slice, update state-machine accounting, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
