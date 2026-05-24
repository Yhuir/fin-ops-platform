# 待找发票 API

## 契约原则

- API 请求和响应字段使用 `snake_case`。
- 前端在 `web/src/features/pendingInvoices/api.ts` 映射为 TypeScript `camelCase`。
- 状态、金额关系、权限和写入结果以后端为准。
- 列表、筛选项、导出预览和导出复用同一套筛选/排序解析。
- 候选进项发票接口使用专用搜索参数和稳定默认排序，不接收列表页 `filters` JSON。
- 无效字段、无效操作符、非法日期/金额返回结构化 `400`。
- 无查看权限返回 `403`；只读导出用户可导出但不可写。

## 列表

`GET /api/pending-invoices/rows`

参数：

| 参数 | 说明 |
| --- | --- |
| `direction` | `expense` 或 `income`；复杂工作流首版只升级 `expense` |
| `filter` | `all`、`requires_invoice`、`bank_statement_as_invoice`、`no_invoice_required` |
| `keyword` | 全局关键字 |
| `date_from` / `date_to` | 交易日期范围 |
| `page` / `page_size` | 服务端分页 |
| `filters` | URL-encoded JSON array |
| `sort_field` | 排序字段白名单 |
| `sort_direction` | `asc` 或 `desc` |

`filters` 示例：

```json
[
  { "field": "status_code", "operator": "in", "values": ["paid_pending_invoice"] },
  { "field": "trade_date", "operator": "between", "value": { "from": "2026-01-01", "to": "2026-01-31" } },
  { "field": "amount", "operator": "between", "value": { "min": "1000.00", "max": "20000.00" } },
  { "field": "summary_remark", "operator": "contains", "value": "维护费" }
]
```

允许字段：

| 字段 | 操作符 |
| --- | --- |
| `trade_date` | `between` |
| `bank_name` | `in`, `contains` |
| `account_name` | `in`, `contains` |
| `counterparty_name` | `contains`, `in` |
| `amount` | `between`, `eq` |
| `summary_remark` | `contains` |
| `status_code` | `in` |
| `rule_group` | `in` |
| `seller_name` | `contains`, `in` |
| `invoice_total` | `between`, `eq` |
| `oa_applicant` | `contains`, `in` |
| `project_name` | `contains`, `in` |

排序字段白名单：

- `trade_date`
- `amount`
- `counterparty_name`
- `status_code`
- `seller_name`
- `invoice_total`
- `oa_applicant`
- `project_name`

## 行 DTO

响应行包含四个大区：

- `bank_transaction`
- `invoice_acquisition_status`
- `input_invoices`
- `oa`

`invoice_acquisition_status.code` 固定为：

- `paid_invoiced`
- `paid_pending_invoice`
- `paid_pending_future_invoice`
- `invoice_not_fully_paid`
- `no_invoice_required`
- `bank_statement_as_invoice`
- `pending`

状态优先级和业务口径见 [`../product-specs/pending-invoices.md`](../product-specs/pending-invoices.md)。

## 筛选项

`GET /api/pending-invoices/filter-options`

返回当前查询上下文下的字段配置、候选项和计数。字段至少覆盖交易时间、银行、账户、对方户名、金额、摘要/备注、状态、规则组、销方、发票金额、OA 申请人和项目。

## 关系明细

`GET /api/pending-invoices/rows/{transactionId}/relation-detail`

用于 `Sheet1` 抽屉，返回：

- 当前流水摘要。
- 已关联发票摘要。
- 历史支付流水。
- `paid_total`、`invoice_total`、`remaining_amount`、`difference_amount`。
- 可用动作。

## 候选进项发票

`GET /api/pending-invoices/invoice-candidates`

参数：

| 参数 | 说明 |
| --- | --- |
| `transaction_id` | 当前支出流水 |
| `keyword` | 发票号、销方、备注等关键字 |
| `seller_name` | 销方筛选 |
| `issue_date_from` / `issue_date_to` | 开票日期范围 |
| `amount_min` / `amount_max` | 价税合计范围 |
| `sort_field` | 可选：`issue_date`、`total_with_tax`、`seller_name`、`amount_difference_abs` |
| `sort_direction` | 可选：`asc` 或 `desc` |
| `page` / `page_size` | 服务端分页 |

候选项包含发票身份、销方、价税合计、已关联支付合计、待支付金额和可关联状态：

- `available`
- `already_related`
- `conflict`

默认稳定排序：

1. `candidate_status` 排序：`available`、`already_related`、`conflict`。
2. `amount_difference_abs` 升序。
3. `issue_date` 倒序。
4. `invoice_id` 升序。

候选接口只读，不写关系。无效 `sort_field`、`sort_direction`、日期或金额返回结构化 `400`。

## 选择已有发票

```text
POST /api/pending-invoices/rows/{transactionId}/attach-existing-invoice/preview
POST /api/pending-invoices/rows/{transactionId}/attach-existing-invoice
```

### Preview 请求

```json
{
  "invoice_id": "inv_001",
  "request_id": "attach-preview:txn_001:inv_001:uuid"
}
```

`request_id` 用于链路追踪和预览去重；如果调用方不能提供，后端可以生成预览 id，但 confirm 仍必须提供 `request_id`。

### Preview 响应

```json
{
  "preview_id": "attach_preview_001",
  "request_key": "pending_invoice_attach_existing:txn_001:inv_001",
  "can_confirm": true,
  "transaction_summary": {
    "id": "txn_001",
    "counterparty_name": "云南供应商",
    "trade_time": "2026-01-08 14:59:45",
    "debit_amount": "19370.00"
  },
  "invoice_summary": {
    "id": "inv_001",
    "digital_invoice_no": "2653...",
    "issue_date": "2026-01-31",
    "seller_name": "云南供应商",
    "seller_tax_no": "9153...",
    "total_with_tax": "19370.00"
  },
  "payment_impact": {
    "paid_total_before": "0.00",
    "paid_total_after": "19370.00",
    "invoice_total": "19370.00",
    "remaining_amount_after": "0.00",
    "difference_amount_after": "0.00"
  },
  "affected_months": ["2026-01"],
  "warnings": [],
  "conflicts": [],
  "expires_at": "2026-05-25T10:10:00+08:00"
}
```

### Confirm 请求

```json
{
  "preview_id": "attach_preview_001",
  "invoice_id": "inv_001",
  "request_id": "attach-existing:txn_001:inv_001:uuid"
}
```

`request_id` 是 confirm 的幂等键。若现有平台路由已经支持 `Idempotency-Key` header，可以同时接受，但 body 中的 `request_id` 是本接口的规范字段。

### Confirm 响应

```json
{
  "status": "completed",
  "request_id": "attach-existing:txn_001:inv_001:uuid",
  "request_key": "pending_invoice_attach_existing:txn_001:inv_001",
  "transaction_id": "txn_001",
  "invoice_id": "inv_001",
  "relation_case_id": "case_001",
  "relation_mode": "pending_invoice_attach_existing_invoice",
  "affected_transaction_ids": ["txn_001"],
  "affected_invoice_ids": ["inv_001"],
  "affected_months": ["2026-01"],
  "row": {}
}
```

`row` 为可选的更新后 pending invoice row DTO；如果 read model 正在刷新，可以返回 `null` 或省略，由前端按 affected ids 刷新当前列表。

### 错误示例

```json
{
  "error": {
    "code": "active_relation_conflict",
    "message": "The invoice already has an active conflicting relation.",
    "details": {
      "invoice_id": "inv_001",
      "relation_case_id": "case_existing"
    }
  }
}
```

要求：

- preview 校验交易存在、方向为支出、发票为进项发票、active relation 冲突、权限和金额影响。
- confirm 必须带 `preview_id` 和 `request_id`。
- confirm 通过 `WorkbenchPairRelationService` 创建 active bank+invoice pair relation。
- confirm 写审计、命令记录和 read model dirty scope。
- 重复确认返回同一事实结果，不创建重复关系。
- relation 已创建但响应、审计或 dirty enqueue 失败后重试，必须补齐可恢复状态。

## 对象详情

```text
GET /api/pending-invoices/bank-transactions/{id}/detail
GET /api/pending-invoices/invoices/{id}/detail
GET /api/pending-invoices/oa/{id}/detail
```

详情接口返回对象完整字段。OA 无稳定投影时返回 `detail_available=false` 和原因。

## 规则

```text
GET /api/pending-invoices/rules
PUT /api/pending-invoices/rules
```

规则保存同一份 `pending_invoice_tag_groups`，不新增规则表。`PUT` 校验 unknown tag、archived tag 和重复分组，成功后写设置审计并标记 pending invoice read model dirty。

## 导出

```text
GET /api/pending-invoices/export-preview
GET /api/pending-invoices/export
```

- 使用与列表相同 query 参数。
- 导出当前筛选/排序命中的全量结果，不只当前页。
- 文件格式优先使用现有平台导出模式的 xlsx。
- 导出字段包含主表隐藏的流水凭证字段、发票字段、OA 字段、状态依据和关系金额。
- 下载动作写导出审计或结构化操作记录。

## Read Model 行为

`read_model.pending_invoice_rows` 必须区分 fresh empty、missing scope 和 stale/dirty scope：

- fresh empty：`200 OK`、`rows=[]`、`read_model_status=fresh`。
- missing/stale：`202 Accepted`、`rows=[]`、`read_model_status=refreshing`，enqueue `pending_invoice.read_model.refresh`。
- API 热路径不得因 read model miss/stale 同步扫描全量事实。

实现阶段需要扩展 SQL query columns 和索引，至少覆盖 `status_code`、`seller_name`、`invoice_total`、`oa_applicant`、`project_name` 和筛选/排序需要的日期金额字段。
