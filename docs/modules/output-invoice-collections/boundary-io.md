# Output Invoice Collections Boundary I/O

销项收款页是 direct API 页面。读取路径为 route -> `OutputInvoiceCollectionQueryService` -> import invoice facts / bank facts / `WorkbenchRelationReadFacade` / OA projection / lifecycle repository / receipt service。

## 已下线

- `output_invoice_collection.read_model.refresh`
- `invoice-usage-collection` worker
- `OutputInvoiceCollectionReadModelRepositoryPort`
- `invoice_usage_collection_sql_projection.py`
- `invoice_usage_collection_read_model_refresh.py`
- `read_model.output_invoice_collection_rows/scopes` 当前运行读写路径

历史 migrations 中的 read model 表只作为数据库历史存在，不是页面 freshness proof 或 worker 合同。
