# Input Invoice Usage Boundary I/O

进项发票使用页是 direct API 页面。读取路径为 route -> `InputInvoiceUsageQueryService` -> import invoice facts / bank facts / `WorkbenchRelationReadFacade` / OA projection / payment rules。

## 已下线

- `input_invoice_usage.read_model.refresh`
- `invoice-usage-collection` worker
- `InputInvoiceUsageReadModelRepositoryPort`
- `invoice_usage_collection_sql_projection.py`
- `invoice_usage_collection_read_model_refresh.py`
- `read_model.input_invoice_usage_rows/scopes` 当前运行读写路径

历史 migrations 中的 read model 表只作为数据库历史存在，不是页面 freshness proof 或 worker 合同。
