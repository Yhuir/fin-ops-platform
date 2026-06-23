# Workbench Relation Command Repository Snapshot Adapter Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:command-repository-snapshot-adapter-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

The app-level command repository callback and snapshot merge/apply helpers can be extracted as one narrow implementation boundary.

Next boundary:

`workbench-relations:command-repository-snapshot-adapter-extraction`

## Evidence

CodeGraph showed a compact call chain:

- `_workbench_relation_command_repository(...)` is called only by `_workbench_relation_command_service(...)`.
- `_save_workbench_relation_command_snapshot(...)` is called only by `_workbench_relation_command_repository(...)`.
- `_apply_workbench_relation_command_snapshot(...)` is called only by `_save_workbench_relation_command_snapshot(...)`.
- `_relation_history_touches_cases(...)` is called only by `_apply_workbench_relation_command_snapshot(...)`.

The current app-owned block:

- builds `CallbackWorkbenchRelationRepository`;
- loads the current in-memory `WorkbenchPairRelationService` snapshot;
- optionally calls a transaction repository's `save_workbench_pair_relations(...)`;
- applies changed-case snapshot deltas back to runtime mirror state;
- rebuilds `WorkbenchPairRelationService` from the merged snapshot;
- refreshes Workbench exception application service wiring after replacing relation mirror internals.

## Why One Adapter Slice Is Safe

The helper group is cohesive and has a single caller chain. Splitting only `_relation_history_touches_cases(...)` or only snapshot apply would leave the app-level repository boundary fragmented and would not reduce the meaningful IO surface.

The implementation should move this group into a service module, while keeping `server.py` as dependency assembly:

- suggested file: `backend/src/fin_ops_platform/services/workbench_relation_command_repository_adapter.py`;
- suggested class: `WorkbenchRelationCommandRepositoryAdapter`;
- injected dependencies:
  - current `WorkbenchPairRelationService`;
  - optional repository override;
  - post-apply callback for `_configure_workbench_exception_application_service`;
- exposed method compatible with `WorkbenchRelationCommandService` repository expectations:
  - `load_workbench_pair_relations()`;
  - `save_workbench_pair_relations(snapshot, changed_case_ids=...)`.

`CallbackWorkbenchRelationRepository` may remain for tests and worker/runtime adapters; this slice should not force a global replacement.

## Remaining Gaps After Next Slice

- App-level pair relation persist/schedule/background helpers remain.
- `WorkbenchWriteFacade` still receives relation snapshot/persist callbacks.
- Broader relation write lifecycle migration remains open.
- Production PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.

## Legacy Path Classification

- Current app-level command repository helper group: implementation-pending.
- Existing `CallbackWorkbenchRelationRepository`: retained; not classified as legacy because tests/runtime handlers still use it as a callback adapter.
- App-level pair relation persist/schedule/background helpers: implementation-pending, not touched by the next adapter slice.
- Blocked-by-human-gate: none for the next local implementation boundary.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/workbench-relations/state-machine.md`

No state definition changes are needed. This audit closes as `analysis-closed`; `workbench_relation` remains `implementation-gap-open`.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. No business rules changed. |
| Service-layer tests | Not applicable for this audit. The next implementation should add adapter unit tests. |
| API contract tests | Not applicable. No HTTP behavior changed. |
| Read model/cache/background job tests | Not applicable. No runtime behavior changed. |
| Frontend component and interaction tests | Not applicable. |
| End-to-end business-flow integration tests | Not applicable. |
| Existing feature regression tests | Applicable through docs/diff verification and CodeGraph evidence review. |

## Verification

Pending before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`

## Completion Claim

This slice closes only the command repository snapshot adapter audit. It does not extract code, close `workbench_relation`, validate production evidence or unblock Go admission.
