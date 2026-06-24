# Next Prompt

Continue the autonomous modular IO refactor after the `go-hot-path:performance-baseline-and-admission-reconciliation` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `go-hot-path:performance-baseline-and-admission-reconciliation`
- Last status: `planning-closed`
- Queue semantics remain corrected: slice status is not module closure.
- All prior non-Go read model implementation-pending queue items are locally accounted for or explicitly `production-evidence-deferred`.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- Go implementation remains blocked until candidate-specific performance evidence, stable Python reference IO, shadow-run plan, rollback gates and freshness/operation-barrier compatibility are documented.

## Next Boundary

`go-hot-path:workbench-compute-performance-baseline-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-performance-baseline-and-admission-reconciliation.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/reconciliation-workbench/implementation-notes.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/tests.md`
   - `docs/operations/runtime-worker-governance.md`
   - Workbench matching/grouping/check code and tests found through CodeGraph.
   - Existing SLO/performance tools under `backend/src/fin_ops_platform/tools/` and their tests.

## Boundary Scope

Target:

- Define the exact Python reference boundary for `workbench:matching-grouping-check`.
- Identify candidate input objects, output objects, state, events, read model dependencies, permissions/audit assumptions and forbidden writes.
- Identify the minimum performance baseline evidence needed before `go-hot-path:workbench-compute-admission` can start.
- Define which evidence can be collected without local `PGSQL_URL`/staging and which must stay production-evidence-deferred.
- Define shadow-run comparison requirements: same input, Go output non-authoritative, no ack, no readiness/cache/active-generation writes.
- Define rollback gates: Python remains reference, Go can be disabled per worker/service, and Python facade API/auth/audit remains unchanged.
- Decide whether `go-hot-path:workbench-compute-admission` can become the next pending boundary or must remain blocked.
- Do not implement Go, Go Fiber or Go Worker in this slice.
- Do not change Python runtime behavior.

Expected verification:

- Targeted existing tests for SLO tool semantics and Workbench matching/grouping/check contract if selected as evidence.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified Workbench compute performance-baseline/IO-contract planning slice, update state-machine accounting, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
