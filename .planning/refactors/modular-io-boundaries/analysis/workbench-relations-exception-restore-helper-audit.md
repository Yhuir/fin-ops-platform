# Workbench Relation Exception Restore Helper Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:exception-restore-helper-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Select a narrow exception rollback restore extraction next:

`workbench-relations:exception-rollback-restore-service-extraction`

The remaining app-owned exception restore helpers are not removable. They protect Workbench exception, personal advance and exception/override changes from leaving in-memory services half-mutated when persistence or relation command work fails.

## Evidence

Current app helpers:

- `_restore_workbench_exception_write_snapshots(...)`
- `_restore_workbench_exception_pair_snapshots(...)`
- `_restore_workbench_exception_override_snapshots(...)`
- inline restore block in `_persist_workbench_exception_and_override_change(...)`
- inline restore block in `_apply_workbench_exception_application(...)`

Callers and behavior:

- `WorkbenchWriteFacade._apply_exception_payload(...)` calls `_restore_exception_write_snapshots(...)` when exception service relation command or persistence fails. It needs exception cases, pair relations, candidate matches and overrides restored together.
- `WorkbenchWriteFacade.confirm_personal_advance_repayment(...)` calls `_restore_exception_pair_snapshots(...)` when relation command or exception-case save fails. It needs exception cases and pair relations restored together.
- `WorkbenchWriteFacade._persist_exception_and_override_change(...)` calls `_restore_exception_override_snapshots(...)` for exception/override persistence failure.
- `Application._persist_workbench_exception_and_override_change(...)` has equivalent inline exception/override restore for app-owned legacy mutation paths.
- `Application._apply_workbench_exception_application(...)` has equivalent inline exception/pair/candidate/override restore for app-level exception application paths.

## Boundary Selection

The next implementation should extract these cohesive rollback restore behaviors into an explicit service, suggested:

- file: `backend/src/fin_ops_platform/services/workbench_exception_rollback_restore_service.py`
- class: `WorkbenchExceptionRollbackRestoreService`

Suggested methods:

- `restore_write_snapshots(...)` for exception + pair + candidate + override rollback.
- `restore_pair_snapshots(...)` for exception + pair rollback.
- `restore_override_snapshots(...)` for exception + override rollback, preserving best-effort `state_store.save_workbench_exception_cases(...)` when applicable.

Suggested dependencies:

- `state_store`;
- `replace_exception_case_service`;
- `replace_pair_relation_service`;
- `replace_candidate_match_service`;
- `replace_override_service`;
- `configure_exception_application_service`.

The service should reuse the app's centralized pair relation replacement callback so cached pair-relation persist state remains consistent.

## Legacy Path Classification

- `_restore_workbench_exception_write_snapshots(...)`: implementation-pending; should become compat-only delegate after extraction.
- `_restore_workbench_exception_pair_snapshots(...)`: implementation-pending; should become compat-only delegate after extraction.
- `_restore_workbench_exception_override_snapshots(...)`: implementation-pending; should become compat-only delegate after extraction.
- `_persist_workbench_exception_and_override_change(...)` inline restore block: implementation-pending; should delegate to the same service method.
- `_apply_workbench_exception_application(...)` inline restore block: implementation-pending; should delegate to the same service method.
- `_restore_batch_accounting_pair_relation_snapshot(...)`: out of scope for the next slice.
- Blocked-by-human-gate: none.

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
| Business core unit tests | Not applicable. No relation or exception business rule changed in this audit. |
| Service-layer tests | Not applicable for this audit. The next implementation should add rollback restore service tests. |
| API contract tests | Not applicable. No HTTP behavior changed. |
| Read model/cache/background job tests | Not applicable. No runtime behavior changed in this audit. |
| Frontend component and interaction tests | Not applicable. |
| End-to-end business-flow integration tests | Not applicable. |
| Existing feature regression tests | Applicable through text impact review and existing Workbench write characterization rollback tests identified as follow-up verification. |

## Verification

Pending before commit:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the exception restore helper audit. It does not extract code, close `workbench_relation`, validate production evidence or unblock Go admission.
