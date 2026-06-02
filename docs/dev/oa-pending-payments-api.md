# OA 待付款核对 API

## 架构边界

OA 待付款核对归入 Invoices 模块。HTTP route facade 位于 `app/routes_oa_pending_payments.py`，业务查询在 `services/oa_pending_payment_service.py`，PostgreSQL read model 在 `read_model.oa_pending_payment_rows` 和 `read_model.oa_pending_payment_scopes`。

生产模式要求读取 PostgreSQL read model。API 命中缺失、脏 scope、source version 不匹配或 SQL repository 不可用时返回 `202` 和 `read_model_status=refreshing`，并通过 durable queue 排队刷新 `scope_type=oa_pending_payment`，不会回退到 live scan。

所有接口都走财务运营平台 OA 读权限校验。未通过 `can_access_app` 的 OA 账户不能读取列表、筛选项或任一详情接口。

## Endpoints

### `GET /api/oa-pending-payments/rows`

Query:

- `page`
- `page_size`
- `keyword`
- `month`
- `trade_date_from`
- `trade_date_to`
- `filters`
- `sort_field`
- `sort_direction`

Response:

- `rows`
- `pagination`
- `summary`
- `filterConfig`
- `read_model_status` / `readModelStatus`
- `source_versions` / `sourceVersions`

Row payload notes:

- `bankTransaction.accountNo`、`bankTransaction.accountLast4`、`bankTransaction.directionLabel` 是 `read_model.oa_pending_payment_rows.payload` JSON 字段，不是新增 SQL 列。
- `bankTransaction.accountLast4` 优先来自导入时识别的银行账号后四位；缺失时从 `accountNo` 截取后四位。
- `bankTransaction.directionLabel` 使用面向页面展示的中文收支方向，当前支出流水展示为 `支出`。
- `bankTransaction.summaries` 可包含多条关联流水摘要；前端 `摘要/备注` 列按摘要和备注去重合并展示。
- 进项发票方展示文案为 `进项发票方名称`，字段名仍为 `invoice.sellerName` / payload 中的 `sellerName`。

### `GET /api/oa-pending-payments/filter-options`

返回当前查询上下文下可用筛选项。生产模式同样优先从 SQL read model 拉取全量分页结果，再用模块服务生成筛选项。

### Detail endpoints

- `GET /api/oa-pending-payments/oa/{oa_id}/detail`
- `GET /api/oa-pending-payments/bank-transactions/{bank_transaction_id}/detail`
- `GET /api/oa-pending-payments/invoices/{invoice_id}/detail`
- `GET /api/oa-pending-payments/rows/{row_id}/relation-details?kind=bank|invoice`

详情响应使用统一 drawer payload：`title`、`subtitle`、`detailAvailable`、`sections`。关联详情额外返回 `kind`、`relationCount`、`hasMultiple`、`summaries` 和 Workbench relation summaries。

生产 PostgreSQL runtime 下，详情接口同样读取 `read_model.oa_pending_payment_rows`，按 `oa_id`、`bank_transaction_id`、`invoice_id` 或 `row_id` 做 SQL-native 单行查询。缺少 repository、scope stale、source version stale 或 read model 未初始化时返回 `202` + `read_model_status=refreshing` 并入队刷新；fresh read model 中目标不存在时返回 `404`。详情接口不得通过 `OaPendingPaymentQueryService` 重新扫描全部 OA、银行流水、发票或 Workbench relations。

## Source Versions

`source_versions` 至少包含：

- `oa_pending_payment_source_version`
- `oa_pending_payment_workbench_relation_schema_version`
- `oa_pending_payment_bank_import_fact_schema_version`
- `oa_pending_payment_input_invoice_import_fact_schema_version`
- `oa_projection_sync_version`

任一 key 缺失或值不匹配时，API 按 stale 处理并触发 `oa_pending_payment.read_model.refresh`。

## Read Model Refresh

刷新事件类型为 `oa_pending_payment.read_model.refresh`。worker 参数为 `--enable-oa-pending-payment-read-model-refresh`。`all` scope 会拆成月份 shard 执行；空 scope 也会写入 scope 行和 source versions，避免 API miss 重复刷新。
