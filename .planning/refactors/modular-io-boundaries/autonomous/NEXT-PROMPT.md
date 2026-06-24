# Next Prompt

Continue the autonomous modular IO refactor after the `go-hot-path:workbench-compute-production-evidence-gate` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `go-hot-path:workbench-compute-production-evidence-gate`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- Workbench compute Python reference IO, shadow-forbidden writes and rollback gates are documented and locally guarded.
- Read-only Workbench compute evidence collector tooling exists locally at `backend/src/fin_ops_platform/tools/workbench_compute_evidence.py`.
- Local collector execution without PostgreSQL config returned structured `configuration_missing`.
- Production SSH read-only discovery reached `finops-prod-root`, confirmed the active runtime release and active worker status, but the deployed release does not contain the collector.
- A deployed-runtime read-only PostgreSQL sampling attempt failed to connect, so real Workbench compute p95/p99, row-count, candidate/decision, heartbeat, query timing and enqueue-to-fresh evidence remains unavailable.
- Go implementation remains blocked until real candidate-specific performance evidence, shadow-run comparison and admission review pass.

## Next Boundary

`planning:post-workbench-compute-evidence-gate-next-boundary-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/ROADMAP.md`
   - `.planning/refactors/README.md`
   - `.planning/refactors/modular-io-boundaries/README.md`
   - `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`
   - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-production-evidence-gate.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `docs/modules/README.md`

## Boundary Scope

Target:

- Reconcile the roadmap and queue after the Workbench compute production evidence gate was deferred.
- Select the next safe non-blocked boundary from the existing modular IO roadmap.
- Do not select `go-hot-path:workbench-compute-admission`, `go-hot-path:workbench-read-model-builder-admission`, `go-hot-path:import-parser-admission`, or `go-hot-path:cost-summary-rollup-admission` while their prerequisites remain missing.
- If the next useful boundary is not already represented in `MODULE-QUEUE.md`, insert one narrow planning or implementation slice with a concrete boundary name, status `pending`, and clear module-closure semantics.
- Prefer remaining modular IO/read model/worker boundary hardening over Go implementation while Go admission gates are blocked.
- If no safe boundary can be selected from the current roadmap without user input, record a hard stop with evidence. Do not invent broad global refactors.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.
- Do not change canonical Python runtime behavior in this planning slice.

Expected output:

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/` recording:
  - previous state,
  - selected next boundary,
  - why blocked Go rows were skipped,
  - roadmap/queue consistency,
  - affected docs/tests,
  - seven-category test applicability,
  - state-machine impact.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified next-boundary selection slice: the queue has exactly one next `pending` executable boundary, Go admission remains blocked unless prerequisites are proven, state-machine accounting is current, docs verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
