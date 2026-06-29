# Wave 5 - ETC imported task detail legacy read removal

日期：2026-06-28

## 目标

删除前端任务导入详情对 legacy `/api/etc/batches/{id}` 的读取依赖，使 ETC 页面读取已导入发票详情时只通过 canonical ETC invoice list 入口。

## 变更

- `web/src/features/etc/api.ts` 删除 `fetchEtcBatchDetail(...)`。
- `web/src/pages/EtcTicketManagementPage.tsx` 的已导入任务详情改为调用 `fetchEtcInvoices({ importBatchId, page: 1, pageSize: 500 })`，再由页面用任务 payload + invoice list 组装 `EtcBatchDetail` UI payload。
- `backend/src/fin_ops_platform/services/etc_service.py` 的 `list_invoices(...)` 增加 `import_batch_id` 过滤。
- `backend/src/fin_ops_platform/app/routes_etc_invoices.py` 的 `/api/etc/invoices` 支持 `importBatchId` / `import_batch_id` 查询参数。
- 前端 API 和页面测试不再 mock 旧 batch detail response，改为 mock canonical invoice list。
- `test_web_etc_api_does_not_call_legacy_batch_mutations_or_list` 追加禁止 `fetchEtcBatchDetail` 和旧 detail URL 回归。

## 边界结论

- 任务导入详情的输入 I/O 现在是：
  - reconciliation task payload：任务摘要、导入批次 id、补充凭证和 OA 状态。
  - canonical ETC invoice list：`/api/etc/invoices?importBatchId=...` 返回该导入批次下的发票事实。
- 页面不再读取 legacy batch summary 作为事实源；旧 batch detail response shape 不再是前端合同。
- 后端 legacy `/api/etc/batches*` route/service 仍存在，但前端已经没有生产调用点；下一步可以删除 `routes_etc_legacy_batches.py` 和 `etc_legacy_batch_*`，并清理对应测试/guard。

## 验证

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_invoices.py backend/src/fin_ops_platform/services/etc_service.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_web_etc_api_does_not_call_legacy_batch_mutations_or_list tests.test_etc_backend.EtcServiceTests.test_service_filters_invoices_by_import_batch_id -v
cd web && npm test -- --run src/test/EtcApi.test.ts src/test/EtcTicketManagementPage.test.tsx
cd web && npm run build
```

结果：通过。Vite build 仍有既有 CSS minify/chunk-size warning。

## 剩余

- 删除 backend legacy `/api/etc/batches*` route owner 和 `etc_legacy_batch_*` services。
- 更新 readiness/route guard：legacy gate 应从“临时允许”转为“入口不存在”。
- 清理旧 backend tests 中直接依赖 `/api/etc/batches*` 的用例，保留必要的 business-batches / reconciliation-task / invoice-list 回归。
