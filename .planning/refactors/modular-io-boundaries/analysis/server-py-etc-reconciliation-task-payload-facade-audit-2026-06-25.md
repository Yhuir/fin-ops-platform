# server-py:etc-reconciliation-task-payload-facade-audit

Date: 2026-06-25
Status: analysis-closed

## Goal

Audit the ETC reconciliation task payload helper group still owned by `Application` after route callback collapse, and select the next smallest local implementation boundary.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
- `tests/test_etc_backend.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-route-owner-local-closure-audit-2026-06-25.md`
- CodeGraph context/explore for `EtcReconciliationTaskApiRoutes` and the payload helper group.

## Findings

`server.py` no longer owns `_handle_api_etc_reconciliation*` callbacks, but it still owns ETC reconciliation route response composition:

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

This is not just generic JSON serialization. The helper group owns route-facing ETC reconciliation semantics:

- imported invoice summary lookup through `_etc_import_batch_by_id(...)`;
- ready-for-import unavailable task blockers and user-facing blocker messages;
- `canConfirm` state derived from task status, credit-card item resolutions, linked ETC evidence, linked supplement evidence, delta note requirements and exclusion/manual-confirmation reasons;
- source-file `hasBlockingIssue` flags derived from parse results;
- parse issue shaping with source-file context.

`EtcReconciliationTaskApiRoutes` currently receives two callables, `task_payload` and `unavailable_task_payload`, and uses them for list/create/detail/delete/imported-invoice delete/source delete/item patch/confirm/reopen/refresh/upload/text responses. Tests already cover important response-shape contracts: created payload source/parse arrays, unavailable import blockers, parse issue source context, stale `canConfirm`, upload source payload fields and imported invoice summary.

## Decision

Do not mark ETC reconciliation route-owner local closure.

Select the next implementation boundary:

`server-py:etc-reconciliation-task-payload-facade-extraction`

The next slice should extract a dedicated payload facade from `Application`, likely under `services/`, with explicit dependencies:

- an import batch lookup dependency for imported invoice summary;
- a serializer dependency, or an equivalent local serializer function, for dataclass/decimal/datetime/enum payload values.

The facade should own:

- task payload;
- unavailable task payload;
- import blockers;
- imported invoice summary;
- confirmability calculation;
- source-file payloads;
- parse issue payloads;
- linked evidence helper calculations.

`server.py` should only assemble the facade and inject `facade.task_payload` / `facade.unavailable_task_payload` into `EtcReconciliationTaskApiRoutes`.

## Stop Gates For Implementation

- Do not change task payload response shape.
- Do not change imported invoice summary semantics.
- Do not change import blocker codes/messages.
- Do not change `canConfirm` semantics.
- Do not move HTTP response construction into the facade.
- Do not pass the whole `Application` into the facade.
- Do not run production browser/admin/write validation for this local boundary.

## Required Tests For Next Slice

- Add direct facade/service tests for payload shape, import blockers, imported invoice summary and at least one negative `canConfirm` case.
- Preserve existing API regressions in `tests/test_etc_backend.py`.
- Extend static boundary guard so payload helper implementations cannot return to `server.py`, while allowing thin facade factory/wiring.

## Verification

Analysis-only slice. No runtime code changed.

Local verification for this slice should be docs/diff checks after state updates.

## Next Boundary

`server-py:etc-reconciliation-task-payload-facade-extraction`
