# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:no-oa-domain-repair-read-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:no-oa-domain-repair-read-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- No-OA application snapshot/version/persist/rollback pair service usage goes through `NoOaPairRelationSnapshotPort`.
- No-OA domain repair/read active relation reads go through `NoOaRelationRepairReadPort`.
- No-OA normal relation writes remain command-service gated.
- No-OA application active relation reads remain facade-backed.
- ETC and WorkbenchWriteFacade relation dependencies still need focused classification.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:post-no-oa-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-domain-repair-read-port-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/etc_service.py`
   - WorkbenchWriteFacade relation construction and relevant tests.
5. Use CodeGraph/text search for remaining `_workbench_pair_relation_service`, `pair_relation_service=`, `WorkbenchPairRelationService`, `replace_pair_relation_service`, `WorkbenchWriteFacade`, `EtcBusinessBatchApplicationService`, `EtcService`, and relation command/read facade boundaries.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Re-audit local `workbench_relation` implementation gaps after no-OA extraction.
- Decide whether the next narrow boundary should be ETC relation dependency audit/extraction, WorkbenchWriteFacade relation callback classification, production-evidence defer, or another smaller planning slice.
- Keep Go hot-path candidates blocked until relation dependencies and read model implementation prerequisites are closed or explicitly deferred.
- Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not change relation write semantics, API payloads, dirty scope semantics or read model refresh semantics in this audit slice.
- Do not declare `workbench_relation` module closed unless IO contract, legacy isolation, freshness proof, tests, docs and production evidence/defer requirements are all satisfied.

## Expected Output

- Analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:post-no-oa-local-implementation-closure-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
