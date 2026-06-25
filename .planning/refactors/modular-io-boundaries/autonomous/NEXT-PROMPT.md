# Next Prompt

Continue after `server-py:no-oa-bank-batch-refresh-producer-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:no-oa-bank-batch-refresh-producer-extraction`.
- Row400 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-refresh-producer-extraction-2026-06-25.md`.
- `NoOaBankBatchReadModelRefreshProducer` owns no-OA scope normalization and gateway enqueue.
- `server.py` no longer defines `_enqueue_no_oa_bank_batch_read_model_refreshes(...)`.
- `server.py` no longer directly calls `enqueue_many("no_oa_bank_batch", ...)`.
- No-OA module/global closure is not claimed because remaining `Application` no-OA surfaces still need a post-producer local closure audit and real production evidence remains deferred.

## Previous Prompt Completion

`server-py:no-oa-bank-batch-refresh-producer-extraction` is complete as a local implementation slice:

- added `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh_producer.py`;
- moved accepted-scope filtering, invalid-scope fallback and durable queue enqueue ownership out of `Application`;
- wired tag selection, `NoOaBankBatchApplicationService` and `NoOaBankBatchDerivedLifecycleExecutor` through the producer;
- removed `Application._enqueue_no_oa_bank_batch_read_model_refreshes(...)`;
- added producer/service/static Guard tests;
- avoided production validation and avoided module/global closure claims.

## Next Boundary

`server-py:no-oa-bank-batch-post-refresh-producer-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-refresh-producer-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-route-owner-local-closure-audit-2026-06-25.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh_producer.py`
   - relevant no-OA read model refresh tests and platform Guards
3. Audit remaining no-OA `Application` surfaces:
   - identify all methods/fields containing `no_oa_bank_batch` or no-OA relation ownership;
   - classify each as composition-root, platform adapter, provider port, compat-only support, or implementation gap;
   - verify no route callbacks and no direct no-OA refresh enqueue helper remain;
   - verify old paths cannot write canonical facts, dirty scopes, outbox, readiness, cache or App Status outside explicit boundaries.
4. Write an analysis file and update queue/state/journal/next prompt.
5. If the audit finds a concrete remaining implementation gap, select the next narrow local boundary. If it finds no local gap, record local support as accounted but production evidence deferred.

## Stop Gates

- Do not run production validation or mutation.
- Do not change no-OA business behavior, API response shape, read model schema, dirty/outbox semantics, frontend behavior or production data during the audit.
- Do not claim no-OA module/global closure from local code audit alone.
- If the audit becomes broader than no-OA `server.py` support, stop with the smallest next boundary instead of expanding scope.
