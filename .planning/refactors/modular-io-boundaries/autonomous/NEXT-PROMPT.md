# Next Prompt

Continue the autonomous modular IO refactor after the `go-hot-path:workbench-compute-performance-baseline-contract` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `go-hot-path:workbench-compute-performance-baseline-contract`
- Last status: `planning-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- Workbench compute Python reference IO, minimum performance evidence, shadow-forbidden writes and rollback gates are documented in `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-baseline-contract.md`.
- Go implementation remains blocked until local executable guards/harness planning, candidate-specific performance evidence, shadow-run comparison and rollback proof are complete.

## Next Boundary

`go-hot-path:workbench-compute-python-reference-contract-guards`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-performance-baseline-and-admission-reconciliation.md`
   - `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-baseline-contract.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/reconciliation-workbench/implementation-notes.md`
   - `docs/operations/runtime-worker-governance.md`
   - `backend/src/fin_ops_platform/services/workbench_matching_dirty_scope_worker.py`
   - `backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py`
   - `backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py`
   - `backend/src/fin_ops_platform/services/workbench_matching_rules.py`
   - `backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`
   - `backend/src/fin_ops_platform/services/workbench_amount_check_service.py`
   - `tests/test_workbench_matching_dirty_scope_worker.py`
   - `tests/test_workbench_matching_orchestrator.py`
   - `tests/test_workbench_reconciliation_engine.py`
   - `tests/test_workbench_matching_rules.py`
   - `tests/test_workbench_free_matching_engine.py`
   - `tests/test_workbench_amount_check_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Add or tighten local tests/guards that freeze the Workbench compute reference IO and shadow-forbidden-write contract.
- Prefer existing Workbench tests and `test_platform_runtime_boundary_guards.py` before adding new abstractions.
- Guard that `workbench:matching-grouping-check` reference state writes remain owned by Python worker/orchestrator/repositories/command services, not by shadow compute.
- Guard or document the canonical shadow diff artifact shape: input scope, source-version signature, canonicalized candidate/decision rows, summary counts, forbidden-write proof and comparison status.
- Keep `go-hot-path:workbench-compute-admission` blocked unless all local guard prerequisites and evidence requirements are satisfied.
- Do not implement Go, Go Fiber or Go Worker in this slice.
- Do not change Python runtime behavior unless a minimal test-only seam is unavoidable and justified.
- Do not weaken Workbench active generation, relation command, dirty queue, freshness, operation barrier, audit or API compatibility semantics.

Expected verification:

- Targeted existing Workbench matching/grouping/check tests selected from the evidence above.
- Any added/changed guard tests.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified Workbench compute reference-contract guard slice, update state-machine accounting, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
