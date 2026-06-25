# Next Prompt

Continue after `server-py:no-oa-bank-batch-workbench-payload-decorator-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:no-oa-bank-batch-workbench-payload-decorator-extraction`.
- Row402 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-workbench-payload-decorator-extraction-2026-06-25.md`.
- `NoOaBankBatchWorkbenchPayloadDecorator` owns no-OA relation metadata enrichment, tag/display tag/cost field decoration and `withdraw_no_oa_batch` action injection.
- `server.py` no longer defines `_relation_with_no_oa_bank_batch_metadata(...)`, `_apply_no_oa_bank_batch_pair_metadata(...)` or `_apply_no_oa_bank_batch_available_actions(...)`.
- No-OA module/global closure is not claimed and production evidence remains deferred.

## Previous Prompt Completion

`server-py:no-oa-bank-batch-workbench-payload-decorator-extraction` is complete as a local implementation slice:

- added `backend/src/fin_ops_platform/services/no_oa_bank_batch_workbench_payload_decorator.py`;
- kept `Application._apply_pair_relation_to_row(...)` as a generic Workbench row decorator dispatcher;
- delegated no-OA-specific relation payload shaping to the decorator;
- preserved tags, display tags, `special_metadata`, cost fields and withdraw action behavior;
- added decorator unit tests, static Guard and targeted Workbench/no-OA regressions;
- avoided production validation and avoided module/global closure claims.

## Next Boundary

`server-py:no-oa-bank-batch-post-decorator-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-workbench-payload-decorator-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-post-refresh-producer-local-closure-audit-2026-06-25.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_workbench_payload_decorator.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining no-OA `Application` surfaces:
   - route callbacks;
   - refresh enqueue;
   - application service factory;
   - route factory;
   - mutation session;
   - source-version provider;
   - Workbench/internal-transfer provider;
   - relation payload decoration;
   - derived lifecycle registry/factory.
4. Classify each remaining surface as composition-root, platform adapter, provider port, compat-only support, or implementation gap.
5. If no further local gap remains, record local `server.py` support as accounted but production evidence deferred. If a concrete local gap remains, select the next narrow boundary.
6. Update analysis/state/queue/journal/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not change runtime code during this audit unless a separate implementation boundary is explicitly selected.
- Do not claim no-OA module/global closure from local code audit alone.
- If remaining scope expands beyond no-OA `server.py` support, stop with the smallest next boundary instead of broadening the slice.
