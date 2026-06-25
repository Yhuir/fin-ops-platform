# Next Prompt

Continue after `server-py:no-oa-bank-batch-post-refresh-producer-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:no-oa-bank-batch-post-refresh-producer-local-closure-audit`.
- Row401 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-post-refresh-producer-local-closure-audit-2026-06-25.md`.
- no-OA route dispatch, refresh producer, application service factory, mutation session, source-version provider and derived lifecycle assembly are accounted for locally.
- Remaining local implementation gap: no-OA Workbench relation payload decoration still lives in `Application`.
- No-OA module/global closure is not claimed and production evidence remains deferred.

## Previous Prompt Completion

`server-py:no-oa-bank-batch-post-refresh-producer-local-closure-audit` is complete as analysis-only:

- confirmed no `_handle_api_no_oa_bank_batch*` callbacks remain in `server.py`;
- confirmed no `_enqueue_no_oa_bank_batch_read_model_refreshes(...)` helper or direct `enqueue_many("no_oa_bank_batch", ...)` bypass remains in `server.py`;
- classified route/factory/session/source-version/derived-lifecycle surfaces as accounted local ports;
- identified no-OA Workbench payload decoration as a remaining app-owned implementation gap;
- avoided runtime code changes and avoided production validation.

## Next Boundary

`server-py:no-oa-bank-batch-workbench-payload-decorator-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-post-refresh-producer-local-closure-audit-2026-06-25.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
   - Workbench payload/relation tests that cover no-OA tags/actions if present
3. Implement only the no-OA Workbench payload decorator extraction:
   - introduce a focused service/provider for no-OA Workbench relation payload decoration;
   - move `_relation_with_no_oa_bank_batch_metadata(...)`, `_apply_no_oa_bank_batch_pair_metadata(...)` and `_apply_no_oa_bank_batch_available_actions(...)` behavior out of `Application`;
   - keep `Application._apply_pair_relation_to_row(...)` as generic Workbench row decoration and delegate no-OA-specific behavior;
   - preserve tags, display_tags, `special_metadata`, `cost_excluded`, summary/detail fields and `withdraw_no_oa_batch` action semantics;
   - add focused unit tests and static Guard coverage.
4. Update analysis/state/queue/journal/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not change no-OA business behavior, API response shape, Workbench row response shape, read model schema, dirty/outbox semantics, frontend behavior or production data.
- Do not refactor unrelated Workbench relation modes in this slice.
- Do not claim no-OA module/global closure.
