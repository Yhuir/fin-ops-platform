# server-py:no-oa-bank-batch-post-display-policy-local-closure-audit

## Status

- Boundary: `server-py:no-oa-bank-batch-post-display-policy-local-closure-audit`
- Result: `production-evidence-deferred`
- Module closure: `not-module-closed`
- Production evidence: `production-evidence-deferred`
- Worker threads: none; this was a read-only controller audit.

## Goal

Audit remaining no-OA `Application` surfaces after route callback collapse, refresh producer extraction, payload decorator extraction and display policy extraction.

## Evidence Checked

- `git status --short --branch`: clean before audit.
- Text inventory of `no_oa_bank_batch`, `NoOaBankBatch`, `NO_OA_BANK_BATCH` and `/api/no-oa-bank-batches` in `server.py`.
- Targeted search for removed callbacks/helpers and direct refresh enqueue bypasses.
- Source review of residual relation-mode branches and provider methods.

## Removed Helpers Still Absent

- `_handle_api_no_oa_bank_batch*`
- `_enqueue_no_oa_bank_batch_read_model_refreshes(...)`
- `_relation_with_no_oa_bank_batch_metadata(...)`
- `_apply_no_oa_bank_batch_pair_metadata(...)`
- `_apply_no_oa_bank_batch_available_actions(...)`

`server.py` also has no direct `enqueue_many("no_oa_bank_batch", ...)`.

## Remaining Surfaces Classified

- Route dispatch for `/api/no-oa-bank-batches*`: app-level route switch delegating to `NoOaBankBatchApiRoutes.route(...)`.
- Route factory `_no_oa_bank_batch_routes(...)`: dependency assembly for route owner ports.
- Application service factory `_no_oa_bank_batch_application_service(...)`: dependency assembly for explicit service ports.
- Mutation session `_no_oa_bank_batch_mutation_session(...)`: HTTP/auth platform mapping.
- Refresh producer factory `_no_oa_bank_batch_read_model_refresh_producer(...)`: dependency assembly.
- Workbench payload decorator factory `_no_oa_bank_batch_workbench_payload_decorator(...)`: dependency assembly.
- Workbench display policy factory `_no_oa_bank_batch_workbench_display_policy(...)`: dependency assembly.
- Derived lifecycle factory `_no_oa_bank_batch_derived_lifecycle_executor(...)`: dependency assembly.
- Source-version provider `_no_oa_bank_batch_workbench_source_versions(...)`: provider wrapper over Workbench source-version facts.
- Workbench internal-transfer submit callback: delegates to `NoOaBankBatchApplicationService.submit_internal_transfer_rows_from_workbench(...)`.
- Workbench category-code provider `_bank_transaction_category_codes_for_workbench_row_ids(...)`: provider port for Workbench confirm-link preconditions; it does not write facts/readiness/dirty/outbox/cache.
- `NO_OA_BANK_BATCH_RELATION_MODE` branches in Workbench row/display helpers: relation-mode dispatch to the extracted no-OA payload decorator and display policy.
- `_bank_transaction_tag_label_current(...)` still imports `NO_OA_MANAGED_LABELS` as a shared label provider fallback. This is not a no-OA batch write/read-model boundary and does not own no-OA relation payload behavior after display policy extraction.

## Conclusion

No remaining no-OA local implementation gap was found in `server.py` for the audited support surface. Local server support is accounted for after:

- route callback collapse;
- refresh producer extraction;
- post-refresh audit;
- Workbench payload decorator extraction;
- post-decorator audit;
- Workbench display policy extraction;
- this post-display-policy audit.

This is not no-OA module/global closure. Real PostgreSQL/worker/App Status/high-row/browser/write-flow production evidence remains deferred.

## Selected Next Boundary

`planning:post-no-oa-server-local-support-next-boundary-selection`

Select the next safe non-production local boundary from the residual `server.py` route/support queue. Do not start production validation while local modularization gaps remain elsewhere.

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```
