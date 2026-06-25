# Next Prompt

Continue after `server-py:etc-reconciliation-task-payload-facade-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-task-payload-facade-audit`.
- Row333 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-payload-facade-audit-2026-06-25.md`.
- `server.py` no longer defines `_handle_api_etc_reconciliation*` callbacks, but it still owns task payload/read-shaping helper implementations.
- ETC reconciliation route-owner local closure is not proven until those helpers move behind an explicit payload facade.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-task-payload-facade-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-payload-facade-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` payload helpers:
     - `_etc_reconciliation_task_payload(...)`
     - `_etc_reconciliation_unavailable_task_payload(...)`
     - `_etc_reconciliation_import_blockers(...)`
     - `_etc_reconciliation_imported_invoice_summary(...)`
     - `_etc_reconciliation_task_can_confirm(...)`
     - `_etc_source_file_payloads(...)`
     - `_etc_parse_issue_payloads(...)`
     - `_etc_task_card_has_linked_etc_evidence(...)`
     - `_etc_task_card_has_linked_supplement(...)`
     - `_etc_task_card_supplement_delta_requires_note(...)`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - relevant payload tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect payload helper callers/callees.
4. Extract the payload helper group into an explicit facade without changing response shape:
   - add a facade under `backend/src/fin_ops_platform/services/`;
   - inject explicit import-batch lookup and serializer dependencies;
   - wire `Application._etc_reconciliation_routes(...)` to pass facade methods into `EtcReconciliationTaskApiRoutes`;
   - remove payload helper implementations from `Application` except for a narrow facade factory if needed.
5. Add direct facade tests and extend static Guard to prevent helper implementation regression into `server.py`.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change task payload response shape.
- Do not change import blockers, imported invoice summary or `canConfirm` semantics.
- Do not pass the whole `Application` into the facade.
- Do not move HTTP response construction into the facade.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
