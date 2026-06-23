# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:final-local-implementation-closure-and-production-evidence-defer` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:final-local-implementation-closure-and-production-evidence-defer`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` local implementation support surfaces are accounted for, but the module is not globally closed.
- Real PostgreSQL relation/history, worker dirty/outbox/readiness, App Status, high-row performance and browser smoke evidence remain deferred.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:next-pilot-selection-after-workbench-relation`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read:
   - `.planning/ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-final-local-implementation-closure-and-production-evidence-defer.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-bank-detail.md`
   - `docs/modules/read-models/README.md`
   - relevant candidate module docs under `docs/modules/`
5. Reconcile whether the next work should be a read model implementation pilot, shared boundary hardening slice, or planning correction slice.
6. Produce an analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Select the next non-Go modular IO/read model pilot after `bank_detail` and `workbench_relation`.
- Use current roadmap, manifest, module docs, implementation-gap evidence and cross-page freshness risk.
- Prefer a narrow boundary that reduces read model inconsistency risk.
- If the next candidate is too broad, split it into the first implementation/audit slice.
- Keep Go hot-path candidates blocked unless every documented Go admission gate is actually satisfied.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed.
- Do not skip pending modular IO/read model implementation work to reach Go admission.
- Do not rely on staging DB or local `PGSQL_URL`.

## Expected Output

- One verified `read-models:next-pilot-selection-after-workbench-relation` analysis/planning slice.
- Updated queue/state/journal/next prompt.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified next-pilot selection slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
