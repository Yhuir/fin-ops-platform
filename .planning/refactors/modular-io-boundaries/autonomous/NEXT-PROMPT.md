# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:workbench-write-facade-required-port-constructor` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:workbench-write-facade-required-port-constructor`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- WorkbenchWriteFacade now requires explicit relation read/snapshot and special metadata mutation ports.
- WorkbenchWriteFacade no longer stores or accepts broad `pair_relation_service`.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:post-workbench-write-facade-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-required-port-constructor.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-post-port-local-implementation-closure-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
5. Use CodeGraph/text search for remaining `workbench_relation` local gaps, especially ETC relation dependencies and any remaining direct pair service dependencies outside explicit ports.
6. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Re-audit broader `workbench_relation` local gaps after WorkbenchWriteFacade no longer accepts broad pair service.
- Decide the next smallest safe boundary before any production-evidence defer or Go admission.
- Consider ETC focused classification, command service native metadata commands, remaining turnover compat reads, or other documented gaps based on current evidence.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed unless all full closure requirements are met.
- Do not change relation behavior, dirty scope semantics, read model refresh semantics or API response shape in this audit slice.

## Expected Output

- Analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:post-workbench-write-facade-local-implementation-closure-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
