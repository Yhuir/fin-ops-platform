# server-py:no-oa-bank-batch-workbench-payload-decorator-extraction

## Status

- Boundary: `server-py:no-oa-bank-batch-workbench-payload-decorator-extraction`
- Result: `local-implementation-closed`
- Module closure: `implementation-gap-open`
- Production evidence: `production-evidence-deferred`
- Worker threads: none; the slice touched a shared Workbench row decorator path in `server.py`, so inline execution avoided same-file conflicts.

## Goal

Move no-OA-specific Workbench relation payload decoration out of `Application` and into a focused service boundary while preserving Workbench row payload semantics.

## Implementation

- Added `NoOaBankBatchWorkbenchPayloadDecorator`.
- Moved source-batch metadata enrichment out of `Application._relation_with_no_oa_bank_batch_metadata(...)`.
- Moved no-OA tag/display tag/cost field decoration out of `Application._apply_no_oa_bank_batch_pair_metadata(...)`.
- Moved `withdraw_no_oa_batch` action injection out of `Application._apply_no_oa_bank_batch_available_actions(...)`.
- Added `Application._no_oa_bank_batch_workbench_payload_decorator(...)` as dependency assembly only.
- Kept `Application._apply_pair_relation_to_row(...)` as the generic Workbench row decoration dispatcher; it now delegates no-OA-specific shaping to the decorator.

## Preserved Contracts

- `special_metadata.source_batch_id` still enriches relation payloads from the current no-OA batch snapshot when available.
- Enriched metadata still includes `batch_version`, `batch_type`, `batch_label`, `row_count`, `total_amount` and `withdrawable`.
- Missing batch or missing source batch id still leaves relation payload unchanged.
- `tags` and `display_tags` still include no-OA display tags without duplicating existing row tags.
- `cost_policy=exclude_all` still sets `cost_excluded=True` and writes `成本统计=不计入`.
- `summary_fields` and `detail_fields` still include `免OA批次`.
- Withdrawable no-OA batches still expose `withdraw_no_oa_batch` while preserving `detail`.
- Non-withdrawable no-OA batches do not get the withdraw action.

## Boundary Evidence

- `server.py` no longer defines:
  - `_relation_with_no_oa_bank_batch_metadata(...)`
  - `_apply_no_oa_bank_batch_pair_metadata(...)`
  - `_apply_no_oa_bank_batch_available_actions(...)`
- `server.py` delegates no-OA relation decoration through `NoOaBankBatchWorkbenchPayloadDecorator`.
- Static Guard prevents the removed app-owned helpers from returning.

## Tests Added Or Changed

- Added `tests/test_no_oa_bank_batch_workbench_payload_decorator.py`
  - covers source batch metadata enrichment;
  - covers tag/display tag/cost field decoration;
  - covers withdraw action injection and non-withdrawable skip behavior.
- Updated `tests/test_platform_runtime_boundary_guards.py`
  - adds `test_no_oa_bank_batch_workbench_payload_decoration_uses_service_boundary`.

## Seven Test Categories

- Business core unit tests: not applicable; no no-OA batch lifecycle, classification, submit/withdraw or amount rule changed.
- Service-layer tests: applicable and covered by the new decorator unit tests.
- API contract tests: no new HTTP contract test added; Workbench/no-OA payload shape is preserved and covered by existing Workbench integration/grouping regressions.
- Read model/cache/background job tests: not applicable for new coverage; no read model schema, worker event, dirty/outbox or readiness behavior changed.
- Frontend component and interaction tests: not applicable; UI behavior and operation barrier targets did not change.
- End-to-end business-flow integration tests: applicable as regression and covered by targeted no-OA Workbench integration tests.
- Existing feature regression tests: applicable and covered by Workbench grouping/no-OA integration regressions plus static Guard.

## Verification

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/no_oa_bank_batch_workbench_payload_decorator.py backend/src/fin_ops_platform/app/server.py tests/test_no_oa_bank_batch_workbench_payload_decorator.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_workbench_payload_decorator -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_bank_batch_workbench_payload_decoration_uses_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_bank_batch_refresh_enqueue_uses_producer_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_workbench_integration.NoOaBankBatchWorkbenchIntegrationTests.test_salary_auto_candidate_does_not_create_active_relation_before_batch_submit tests.test_no_oa_bank_batch_workbench_integration.NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_salary_batch_relation_pairs_then_cancel_returns_to_open tests.test_no_oa_bank_batch_workbench_integration.NoOaBankBatchWorkbenchIntegrationTests.test_submit_selection_fee_rows_render_as_collapsed_paired_workbench_group tests.test_no_oa_bank_batch_workbench_integration.NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_internal_transfer_relation_groups_bank_rows_until_cancelled -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping.WorkbenchCandidateGroupingTests.test_no_oa_bank_batch_group_collapses_to_summary_and_preserves_bank_rows tests.test_workbench_candidate_grouping.WorkbenchCandidateGroupingTests.test_internal_transfer_no_oa_summary_uses_business_amount_not_bank_row_sum tests.test_workbench_candidate_grouping.WorkbenchCandidateGroupingTests.test_oa_exempt_relation_uses_projection_metadata_for_display_tags -v
```

All commands above passed locally.

## Deferred Evidence And Risks

- No production command was run.
- No staging database and no local PostgreSQL URL are available.
- Real PostgreSQL/worker/App Status/browser/write-flow closure remains deferred.
- no-OA module/global closure is not claimed.

## Next Boundary

`server-py:no-oa-bank-batch-post-decorator-local-closure-audit`

Audit remaining no-OA `Application` surfaces after payload decorator extraction and decide whether local `server.py` support is accounted for or another implementation gap remains.
