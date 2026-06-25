# Next Prompt

Continue after `server-py:no-oa-bank-batch-post-decorator-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:no-oa-bank-batch-post-decorator-local-closure-audit`.
- Row403 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-post-decorator-local-closure-audit-2026-06-25.md`.
- no-OA route, refresh, payload decorator, factory, session and source-version surfaces are accounted for locally.
- Remaining local implementation gap: no-OA Workbench tag/display policy still lives inside generic `Application` helpers.
- No-OA module/global closure is not claimed and production evidence remains deferred.

## Previous Prompt Completion

`server-py:no-oa-bank-batch-post-decorator-local-closure-audit` is complete as analysis-only:

- confirmed removed no-OA route/refresh/payload helpers remain absent;
- classified route/refresh/decorator/factory/session/source-version surfaces as accounted local ports;
- identified `_derive_workbench_row_tags(...)` and `_pair_relation_display_payload(...)` as still owning no-OA-specific Workbench display behavior;
- avoided runtime code changes and avoided production validation.

## Next Boundary

`server-py:no-oa-bank-batch-workbench-display-policy-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-post-decorator-local-closure-audit-2026-06-25.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_platform_runtime_boundary_guards.py`
   - Workbench candidate grouping / no-OA integration tests covering display tags and relation display payload
3. Implement only the no-OA Workbench display policy extraction:
   - introduce a focused no-OA Workbench display policy service;
   - move no-OA row tag derivation out of `_derive_workbench_row_tags(...)`;
   - move no-OA relation display payload out of `_pair_relation_display_payload(...)`;
   - keep generic Workbench helpers as dispatchers/delegators;
   - preserve managed-label filtering, relation/group/special metadata tag inputs, batch type label lookup, batch label fallback and relation display payload shape.
4. Add focused unit tests and static Guard coverage.
5. Update analysis/state/queue/journal/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not change Workbench API response shape, no-OA business behavior, read model schema, dirty/outbox semantics, frontend behavior or production data.
- Do not refactor unrelated Workbench relation modes in this slice.
- Do not claim no-OA module/global closure.
