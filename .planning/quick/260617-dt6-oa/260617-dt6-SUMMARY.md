---
status: complete
---

# Quick Task 260617-dt6 Summary

## Outcome

免 OA 流水批量处理页面不再把 relation-backed 的旧 `stale/category drift` 批次显示为“分类已变更，需复核”。当 SQL read model 返回 `status=stale` 但仍属于 submitted bucket 或可撤回时，后端 API 出口和前端 mapper 都按 `submitted` 投影，清除复核类 blocked reason，并保留撤回入口。

## Changed Files

- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `web/src/features/noOaBankBatches/api.ts`
- `web/src/pages/NoOaBankBatchPage.tsx`
- `tests/test_no_oa_bank_batch_application_service.py`
- `web/src/test/NoOaBankBatchApi.test.ts`
- `web/src/test/NoOaBankBatchPage.test.tsx`
- `docs/modules/no-oa-bank-batches/README.md`
- `docs/modules/no-oa-bank-batches/state-machine.md`
- `docs/modules/no-oa-bank-batches/tests.md`
- `docs/modules/no-oa-bank-batches/implementation-notes.md`

## Verification

- `PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_no_oa_salary_batch_relation_pairs_then_cancel_returns_to_open tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_no_oa_internal_transfer_relation_groups_bank_rows_until_cancelled -q`
- `cd web && npm test -- --run src/test/NoOaBankBatchPage.test.tsx src/test/NoOaBankBatchApi.test.ts`
- `bash scripts/verify.sh docs`

## Notes

- Existing Workbench integration tests confirm submitted no-OA items appear in the paired area and withdraw returns bank rows to open/unmatched.
- Real production stale rows without an active relation still require data cleanup/smoke inspection; this task only changes the user-visible projection for relation-backed submitted rows.
