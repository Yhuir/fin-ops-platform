# server-py:no-oa-bank-batch-workbench-display-policy-extraction

## Status

- Boundary: `server-py:no-oa-bank-batch-workbench-display-policy-extraction`
- Result: `local-implementation-closed`
- Module closure: `implementation-gap-open`
- Production evidence: `production-evidence-deferred`
- Worker threads: none; the slice touched shared Workbench display helpers in `server.py`.

## Goal

Move no-OA-specific Workbench tag derivation and relation display payload policy out of generic `Application` helpers.

## Implementation

- Added `NoOaBankBatchWorkbenchDisplayPolicy`.
- Moved no-OA relation display payload shape out of `Application._pair_relation_display_payload(...)`.
- Moved no-OA row tag derivation out of `Application._derive_workbench_row_tags(...)`.
- Added `Application._no_oa_bank_batch_workbench_display_policy(...)` as dependency assembly only.
- Kept generic Workbench helpers as dispatchers/delegators for relation-mode-specific behavior.

## Preserved Contracts

- no-OA relation display payload remains:
  - `code=no_oa_bank_batch`;
  - label `已匹配：<batch_label>` when batch label exists;
  - fallback label `已匹配：免OA流水`;
  - tone `success`.
- no-OA row tag derivation still merges relation, group and special metadata display tags.
- Managed no-OA labels are still filtered from relation/group/metadata display-tag sources.
- `batch_type` still maps through the current bank transaction tag label provider.
- Non-managed `batch_label` still becomes visible.

## Boundary Evidence

- `_derive_workbench_row_tags(...)` delegates no-OA display tags to `NoOaBankBatchWorkbenchDisplayPolicy.row_tags(...)`.
- `_pair_relation_display_payload(...)` delegates no-OA display payload to `NoOaBankBatchWorkbenchDisplayPolicy.relation_display_payload(...)`.
- Static Guard prevents no-OA managed-label filtering and relation display labels from returning to generic `Application` helpers.

## Tests Added Or Changed

- Added `tests/test_no_oa_bank_batch_workbench_display_policy.py`
  - covers no-OA relation display payload with batch label and fallback label;
  - covers display-tag source merging and managed-label filtering.
- Updated `tests/test_platform_runtime_boundary_guards.py`
  - adds `test_no_oa_bank_batch_workbench_display_policy_uses_service_boundary`.

## Seven Test Categories

- Business core unit tests: not applicable; no no-OA lifecycle, submit/withdraw or classification rules changed.
- Service-layer tests: applicable and covered by display policy unit tests.
- API contract tests: no new HTTP contract test added; Workbench/no-OA payload shape is preserved and protected by existing grouping/integration regressions.
- Read model/cache/background job tests: not applicable; no read model, dirty/outbox, worker or readiness behavior changed.
- Frontend component and interaction tests: not applicable; UI behavior and operation barriers did not change.
- End-to-end business-flow integration tests: applicable as regression and covered by targeted no-OA Workbench integration tests.
- Existing feature regression tests: applicable and covered by Workbench grouping/no-OA integration regressions plus static Guard.

## Verification

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/no_oa_bank_batch_workbench_display_policy.py backend/src/fin_ops_platform/app/server.py tests/test_no_oa_bank_batch_workbench_display_policy.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_workbench_display_policy -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_bank_batch_workbench_display_policy_uses_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_bank_batch_workbench_payload_decoration_uses_service_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping.WorkbenchCandidateGroupingTests.test_no_oa_bank_batch_group_collapses_to_summary_and_preserves_bank_rows tests.test_workbench_candidate_grouping.WorkbenchCandidateGroupingTests.test_internal_transfer_no_oa_summary_uses_business_amount_not_bank_row_sum tests.test_workbench_candidate_grouping.WorkbenchCandidateGroupingTests.test_oa_exempt_relation_uses_projection_metadata_for_display_tags -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_workbench_integration.NoOaBankBatchWorkbenchIntegrationTests.test_salary_auto_candidate_does_not_create_active_relation_before_batch_submit tests.test_no_oa_bank_batch_workbench_integration.NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_salary_batch_relation_pairs_then_cancel_returns_to_open tests.test_no_oa_bank_batch_workbench_integration.NoOaBankBatchWorkbenchIntegrationTests.test_submit_selection_fee_rows_render_as_collapsed_paired_workbench_group tests.test_no_oa_bank_batch_workbench_integration.NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_internal_transfer_relation_groups_bank_rows_until_cancelled -v
bash scripts/verify.sh docs
git diff --check
```

All commands above passed locally.

## Deferred Evidence And Risks

- No production command was run.
- No staging database and no local PostgreSQL URL are available.
- Real PostgreSQL/worker/App Status/browser/write-flow closure remains deferred.
- no-OA module/global closure is not claimed.

## Next Boundary

`server-py:no-oa-bank-batch-post-display-policy-local-closure-audit`

Audit remaining no-OA `Application` surfaces after display policy extraction and decide whether local `server.py` support is accounted for or another implementation gap remains.
