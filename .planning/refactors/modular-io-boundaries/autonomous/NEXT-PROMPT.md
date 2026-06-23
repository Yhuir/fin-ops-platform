# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:etc-repair-link-migration-persist-callback-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:etc-repair-link-migration-persist-callback-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open` until final closure/defer accounting is completed.
- ETC repair/link/migration callbacks are classified as explicit post-command persist boundaries.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:final-local-implementation-closure-and-production-evidence-defer`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-etc-repair-link-migration-persist-callback-closure-audit.md`
   - all latest workbench relation closure/accounting analysis files;
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
4. Inspect remaining direct relation references in app, services, tools and tests.
5. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Determine whether all local `workbench_relation` implementation gaps are closed or explicitly classified.
- If local gaps remain, insert the next narrow implementation/audit boundary before Go.
- If only unavailable real PostgreSQL/worker/App Status/high-row/browser evidence remains, mark the module slice as `production-evidence-deferred`, not `closed`.
- Confirm Go admission remains blocked unless all documented Go prerequisites are actually satisfied.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not mark `workbench_relation` globally closed.
- Do not hide local implementation gaps as production evidence defer.

## Expected Output

- Narrow final closure/defer accounting slice.
- Updated queue/state/journal/next prompt.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:final-local-implementation-closure-and-production-evidence-defer` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
