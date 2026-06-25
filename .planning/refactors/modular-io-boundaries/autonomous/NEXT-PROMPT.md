# Next Prompt

Continue after `server-py:no-oa-bank-batch-workbench-display-policy-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:no-oa-bank-batch-workbench-display-policy-extraction`.
- Row404 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-workbench-display-policy-extraction-2026-06-25.md`.
- `NoOaBankBatchWorkbenchDisplayPolicy` owns no-OA Workbench row tag derivation and relation display payload labels.
- No-OA module/global closure is not claimed and production evidence remains deferred.

## Previous Prompt Completion

`server-py:no-oa-bank-batch-workbench-display-policy-extraction` is complete as a local implementation slice:

- added `backend/src/fin_ops_platform/services/no_oa_bank_batch_workbench_display_policy.py`;
- kept generic Workbench display helpers as dispatchers/delegators;
- moved no-OA managed-label filtering, display tag source merging, batch type label lookup, batch label fallback and relation display payload shape out of `Application`;
- added display policy unit tests, static Guard and targeted Workbench/no-OA regressions;
- avoided production validation and avoided module/global closure claims.

## Next Boundary

`server-py:no-oa-bank-batch-post-display-policy-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-workbench-display-policy-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-post-decorator-local-closure-audit-2026-06-25.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining no-OA `Application` surfaces after display policy extraction:
   - route callbacks;
   - refresh enqueue;
   - application service factory;
   - route factory;
   - mutation session;
   - source-version provider;
   - Workbench/internal-transfer provider;
   - payload decorator;
   - display policy;
   - derived lifecycle registry/factory;
   - residual `NO_OA_BANK_BATCH_RELATION_MODE` branches.
4. Classify each remaining surface as composition-root, platform adapter, provider port, compat-only support, or implementation gap.
5. If no further local gap remains, record local `server.py` support as accounted but production evidence deferred. If a concrete local gap remains, select the next narrow boundary.
6. Update analysis/state/queue/journal/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not change runtime code during this audit unless a separate implementation boundary is explicitly selected.
- Do not claim no-OA module/global closure from local code audit alone.
- If remaining scope expands beyond no-OA `server.py` support, stop with the smallest next boundary instead of broadening the slice.
