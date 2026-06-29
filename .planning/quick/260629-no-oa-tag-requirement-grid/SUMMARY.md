# 260629 no-OA tag requirement grid

## Scope

- Redesign the no-OA bank batch tag drawer from an editable tag selection UI to a compact grid.
- Left grid facts come from Bank Details auto tag rules: direction, primary label, sub label.
- Right grid writes only paired requirements: OA and invoice.
- Workbench paired/open grouping must consume no-OA paired requirements.

## Boundary / I/O

- `bank-details` owns bank transaction tag facts and auto tag rule labels.
- `no-oa-bank-batches` owns the tag requirement settings, no-OA candidate generation, submit/withdraw, and no-OA read model refresh.
- `workbench-relations` owns relation persistence and projections; it stores no-OA metadata but does not interpret tag rules.
- `reconciliation-workbench` owns candidate grouping and paired/open presentation.

## Decisions

- `rules` / `requirements_by_tag_code` are the new primary contract.
- `selected_tag_codes` remains a compatibility field derived from rules where both `requires_oa=false` and `requires_invoice=false`.
- New bank auto tags default to `requires_oa=true` and `requires_invoice=true` so they do not silently become no-OA candidates.
- A no-OA relation with checked OA or invoice must remain open until the required row type exists.
- Existing legacy selections are interpreted as no requirements for those selected tag codes.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping tests.test_app_settings_service tests.test_no_oa_bank_batch_tag_selection_api -v`
- `npm test -- --run NoOaBankBatchApi.test.ts NoOaBankBatchPage.test.tsx`
