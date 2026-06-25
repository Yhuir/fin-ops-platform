# server-py:no-oa-bank-batch-post-decorator-local-closure-audit

## Status

- Boundary: `server-py:no-oa-bank-batch-post-decorator-local-closure-audit`
- Result: `analysis-closed`
- Module closure: `implementation-gap-open`
- Production evidence: `production-evidence-deferred`
- Worker threads: none; this was a read-only controller audit.

## Goal

Audit remaining no-OA `Application` surfaces after route callback collapse, refresh producer extraction and Workbench payload decorator extraction.

## Evidence Checked

- `git status --short --branch`: clean before audit.
- Text inventory of `no_oa_bank_batch`, `NoOaBankBatch`, `NO_OA_BANK_BATCH` and `/api/no-oa-bank-batches` in `server.py`.
- Targeted search for removed route callbacks, removed refresh helper, removed payload decorator helpers and direct no-OA refresh enqueue bypass.
- Source review of remaining no-OA branches inside Workbench grouping/tag/display helpers.

## Accounted Surfaces

- Route dispatch and route factory are route-owner wiring.
- Application service factory is dependency assembly.
- Mutation session is HTTP/auth platform mapping.
- Refresh producer factory and tag-selection refresh callback are dependency assembly/delegation.
- Derived lifecycle factory and registry entry are dependency assembly/delegation.
- Source-version provider is a Workbench source-version provider wrapper.
- Workbench submit-internal-transfer callback delegates to `NoOaBankBatchApplicationService`.
- Workbench payload decorator factory delegates no-OA metadata/tag/action shaping to `NoOaBankBatchWorkbenchPayloadDecorator`.
- Removed helpers remain absent:
  - `_handle_api_no_oa_bank_batch*`
  - `_enqueue_no_oa_bank_batch_read_model_refreshes(...)`
  - `_relation_with_no_oa_bank_batch_metadata(...)`
  - `_apply_no_oa_bank_batch_pair_metadata(...)`
  - `_apply_no_oa_bank_batch_available_actions(...)`

## Remaining Local Implementation Gap

`server.py` still directly owns no-OA-specific Workbench display policy in generic Workbench helper code:

- `_derive_workbench_row_tags(...)` has a `NO_OA_BANK_BATCH_RELATION_MODE` branch that:
  - filters managed no-OA labels;
  - reads relation/group/special metadata display tags;
  - maps `batch_type` through current bank tag labels;
  - adds `batch_label` when it is not managed.
- `_pair_relation_display_payload(...)` has a `NO_OA_BANK_BATCH_RELATION_MODE` branch that returns:
  - code `no_oa_bank_batch`;
  - label `已匹配：<batch_label>` or `已匹配：免OA流水`;
  - tone `success`.

These branches are not only composition-root wiring. They encode no-OA-specific Workbench display behavior and should move behind an explicit no-OA Workbench display policy/provider while the generic Workbench helper delegates by relation mode.

## Selected Next Boundary

`server-py:no-oa-bank-batch-workbench-display-policy-extraction`

Expected implementation:

- Add a focused no-OA Workbench display policy service.
- Move no-OA row tag derivation and relation display payload logic out of `Application`.
- Keep generic Workbench display helpers as dispatchers/delegators.
- Preserve visible tags, managed-label filtering, batch type label lookup, batch label display and relation display payload shape.
- Add focused unit tests and static Guard coverage.

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
