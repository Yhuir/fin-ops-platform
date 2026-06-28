# OA Pending Payments Boundary I/O

OA 待付款页是 direct API 页面。读取路径为 route -> `OaPendingPaymentQueryService` -> OA projection / in-progress OA projection / import facts / `WorkbenchRelationReadFacade` / OA pending relation repository / payment status repository。

## 已下线

- `oa_pending_payment.read_model.refresh`
- `invoice-usage-collection` worker
- `OaPendingPaymentReadModelRepositoryPort`
- `invoice_usage_collection_sql_projection.py`
- `invoice_usage_collection_read_model_refresh.py`
- `read_model.oa_pending_payment_rows/scopes` 当前运行读写路径

`oa.sync` 仍是真实外部同步任务，但它不再 fan-out 到 OA pending payment read model refresh。历史 migrations 中的 read model 表只作为数据库历史存在。
