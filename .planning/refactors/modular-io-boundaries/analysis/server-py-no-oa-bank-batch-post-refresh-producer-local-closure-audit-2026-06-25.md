# server-py:no-oa-bank-batch-post-refresh-producer-local-closure-audit

## Status

- Boundary: `server-py:no-oa-bank-batch-post-refresh-producer-local-closure-audit`
- Result: `analysis-closed`
- Module closure: `implementation-gap-open`
- Production evidence: `production-evidence-deferred`
- Worker threads: none; this was a read-only controller audit.

## Goal

Audit remaining no-OA bank batch surfaces in `Application` after:

- `/api/no-oa-bank-batches*` route callback collapse;
- no-OA refresh producer extraction;
- no-OA source-version/stale-reason helper removal;
- no-OA read model repository, persistence, derived lifecycle and mutation persistence boundary slices.

This audit does not change runtime behavior.

## Evidence Checked

- `git status --short --branch`: clean before audit.
- Text inventory of `no_oa_bank_batch`, `NoOaBankBatch` and no-OA route/helper names in `server.py`.
- CodeGraph context for no-OA route owner, application service and refresh producer boundaries.
- Targeted search for removed route callbacks, removed refresh helper and direct no-OA enqueue bypass.

## Closed Surfaces

- Route dispatch: `server.py` delegates `/api/no-oa-bank-batches*` to `NoOaBankBatchApiRoutes.route(...)`.
- Route callbacks: no `_handle_api_no_oa_bank_batch*` callbacks remain in `server.py`.
- Refresh enqueue: `Application._enqueue_no_oa_bank_batch_read_model_refreshes(...)` is removed.
- Direct refresh bypass: `server.py` has no direct `enqueue_many("no_oa_bank_batch", ...)`.
- Refresh producer: `Application._no_oa_bank_batch_read_model_refresh_producer(...)` is dependency assembly only.
- Application service factory: `_no_oa_bank_batch_application_service(...)` is dependency assembly and injects explicit ports.
- Route factory: `_no_oa_bank_batch_routes(...)` is dependency assembly and HTTP adapter wiring.
- Mutation session: `_no_oa_bank_batch_mutation_session(...)` is HTTP/auth platform mapping.
- Derived lifecycle: `_no_oa_bank_batch_derived_lifecycle_executor(...)` is dependency assembly.
- Source versions: `_no_oa_bank_batch_workbench_source_versions(...)` is a provider wrapper over the Workbench source-version boundary.
- Tag selection refresh callback: uses the refresh producer.
- Workbench submit internal transfer callback: delegates to `NoOaBankBatchApplicationService.submit_internal_transfer_rows_from_workbench(...)`.

## Remaining Local Implementation Gap

`server.py` still owns no-OA relation payload decoration for Workbench rows:

- `_relation_with_no_oa_bank_batch_metadata(...)`
- `_apply_no_oa_bank_batch_pair_metadata(...)`
- `_apply_no_oa_bank_batch_available_actions(...)`

These helpers enrich relation payloads with no-OA batch metadata, tags, cost flags and `withdraw_no_oa_batch` action state. They are not just composition-root wiring, platform mapping or provider stubs. They are still app-owned response shaping behavior for no-OA relation display inside Workbench payload rows.

The smallest safe next boundary is to extract that behavior into a dedicated service/provider and inject it into the row decoration path. This should not change Workbench API shape, relation semantics, withdraw availability, tags or cost display fields.

## Non-Gaps / Retained Ports

- `_bank_transaction_category_codes_for_workbench_row_ids(...)` remains a Workbench provider port. It reads no-OA eligible bank rows and effective categories so Workbench confirm-link preconditions can resolve category codes. It does not write canonical facts, dirty scopes, outbox, readiness, cache or App Status.
- `_no_oa_bank_batch_workbench_source_versions(...)` remains a source-version provider wrapper. It does not compute no-OA stale reasons or enqueue refresh.
- `NO_OA_BANK_BATCH_RELATION_MODE` checks inside broader Workbench row decoration are dispatcher branches; the no-OA-specific payload shaping should move, but the generic Workbench decorator can still call an injected no-OA decorator.

## Selected Next Boundary

`server-py:no-oa-bank-batch-workbench-payload-decorator-extraction`

Expected implementation:

- Add a focused no-OA Workbench payload decorator service.
- Move relation metadata enrichment, tag injection, cost display fields and withdraw action injection out of `Application`.
- Keep `Application._apply_pair_relation_to_row(...)` as a generic Workbench row decorator that delegates no-OA-specific shaping.
- Add focused unit tests and a platform Guard preventing the no-OA helpers from returning to `Application`.

## Deferred Evidence And Risks

- No production command was run.
- No staging database and no local PostgreSQL URL are available.
- Real PostgreSQL/worker/App Status/browser/write-flow closure remains deferred.
- no-OA module/global closure is not claimed.

## Verification

This audit is analysis-only. Required verification after documentation updates:

```bash
bash scripts/verify.sh docs
git diff --check
```
