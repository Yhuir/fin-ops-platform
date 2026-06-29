# Canonical Facts Wave 5: ETC Web Legacy Mutation Removal

日期：2026-06-28

## Scope

删除前端 ETC API client 对 legacy `/api/etc/batches*` list 和 mutation endpoint 的调用面，避免页面继续通过旧兼容 API 写 ETC canonical facts。

## Changes

- `web/src/features/etc/api.ts`
  - 删除 `fetchEtcBatches(...)`。
  - 删除 `createEtcOaDraft(...)`、`createEtcOaDraftForBatch(...)`。
  - 删除 `confirmEtcBatchSubmitted(...)`、`markEtcBatchNotSubmitted(...)`。
  - 删除 `deleteEtcBatch(...)`。
- `web/src/pages/EtcTicketManagementPage.tsx`
  - 删除 `deleteEtcBatch` / `fetchEtcBatches` import。
  - 删除 `legacyBatch` delete plan 分支；页面 batch delete 只走 `/api/etc/business-batches/{id}`。
  - 非 business-batch row 不再允许走旧 delete fallback。
- `tests/test_platform_runtime_boundary_guards.py`
  - 新增 `test_web_etc_api_does_not_call_legacy_batch_mutations_or_list`，禁止旧前端 list/mutation client 回归。
- `web/src/test/EtcApi.test.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`
  - state-changing action 测试改走 business-batches mutation。
  - 删除对已移除旧 client 的 spy。

## Verification

```bash
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_web_etc_api_does_not_call_legacy_batch_mutations_or_list -v
cd web && npm test -- --run src/test/EtcApi.test.ts src/test/EtcTicketManagementPage.test.tsx
cd web && npm run build
```

Result: passed.

## Remaining

`fetchEtcBatchDetail(...)` still reads `/api/etc/batches/{id}` for task import detail when no business batch exists. Backend `routes_etc_legacy_batches.py` and `etc_legacy_batch_*` services therefore remain production-reachable and are not closure. Next ETC slice must migrate this remaining detail read to a canonical import/business-batch/read endpoint, then delete the backend legacy route/service files and their compatibility tests.
