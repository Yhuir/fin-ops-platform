# Next Prompt

Continue after `server-py:no-oa-bank-batch-route-owner-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:no-oa-bank-batch-route-owner-local-closure-audit`.
- Row399 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-route-owner-local-closure-audit-2026-06-25.md`.
- No `_handle_api_no_oa_bank_batch*` callbacks remain in `server.py`.
- No-OA module/global closure is not claimed because `_enqueue_no_oa_bank_batch_read_model_refreshes(...)` still owns scope normalization and direct gateway enqueue logic in `Application`.

## Previous Prompt Completion

`server-py:no-oa-bank-batch-route-owner-local-closure-audit` is complete as analysis-only:

- proved no no-OA route callbacks remain in `server.py`;
- classified remaining no-OA `Application` surfaces;
- selected no-OA refresh producer extraction as the next local implementation boundary;
- avoided runtime code changes and avoided production validation.

## Next Boundary

`server-py:no-oa-bank-batch-refresh-producer-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-route-owner-local-closure-audit-2026-06-25.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_derived_lifecycle_executor.py`
   - relevant no-OA read model refresh tests and platform Guards
3. Implement only no-OA refresh producer extraction:
   - introduce a no-OA-specific refresh producer/service in `services/`;
   - move scope normalization and `ReadModelRefreshGateway.enqueue_many("no_oa_bank_batch", ...)` out of `Application`;
   - preserve accepted scopes (`all` and `YYYY-MM`), reason forwarding and false return when gateway cannot enqueue;
   - wire `NoOaBankBatchApplicationService` and derived lifecycle through the producer;
   - remove `_enqueue_no_oa_bank_batch_read_model_refreshes(...)` from `Application`;
   - add service/static Guard tests.
4. Update analysis/state/queue/journal/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not change no-OA business behavior, API response shape, read model schema, dirty/outbox semantics, frontend behavior or production data.
- Do not move unrelated Workbench payload decoration helpers in this slice.
- Do not claim no-OA module/global closure.
