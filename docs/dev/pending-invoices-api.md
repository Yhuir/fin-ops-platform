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

列表响应的 `summary.source_summary` 用于说明当前读模型中的流水方向边界：

| 字段 | 说明 |
| --- | --- |
| `bank_transaction_rows` | 当前日期范围内的全部银行流水数，等于支出和收入之和。 |
| `expense_rows` | 当前日期范围内进入待找发票支出侧口径的流水数。 |
| `income_rows` | 当前日期范围内收入流水数；收入侧不进入待找发票支出工作台。 |
| `current_direction_rows` | 当前 `direction` 的流水数。 |
| `excluded_direction_rows` | 当前页面方向之外的流水数。 |

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

OA 详情必须优先从 OA projection / OA 只读适配层读取，不允许只用关联关系 metadata 拼接完整表单。支付申请类详情额外返回 `oa_print_layout`，用于前端按 OA 打印预览样式展示：

```json
{
  "title": "打印选择",
  "subtitle": "支付申请",
  "detail_available": true,
  "oa_print_layout": {
    "form_title": "支付申请",
    "download_label": "打印下载",
    "fields": [
      { "label": "申请人", "value": "杨丽萍" },
      { "label": "申请日期", "value": "2026-05-25" },
      { "label": "金额", "value": "¥ 7680.00元（大写：柒仟陆佰捌拾元整）" }
    ],
    "approvals": [
      { "title": "支付申请", "lines": ["杨丽萍发起流程申请", "2026-05-25 11:20:27", "杨丽萍"], "signature": "杨丽萍" }
    ]
  },
  "sections": []
}
```

`fields` 和 `approvals` 中只能放 OA projection 实际提供的字段或由其确定性派生的金额大写、发起节点等展示字段；缺失审批记录时不得伪造审批意见或签名。

## 规则

```text
GET /api/pending-invoices/rules
PUT /api/pending-invoices/rules
```

规则保存仍复用同一份 `pending_invoice_tag_groups`，不新增规则表。当前规则专用接口只持久化两组可编辑规则：`bank_statement_as_invoice`、`no_invoice_required`；`requires_invoice` 由后端按银行明细 `自动标签规则` 的 active 补集派生。

`GET /api/pending-invoices/rules` 返回：

- `available_tags`：待找发票规则抽屉唯一可用标签全集，来源等同于 `/api/bank-details/auto-tag-rules` 的 `system_rule + active_rules`，每项至少包含 `code`、`label`、`status`、`output_primary_label`、`output_sub_label`、`output_third_label`。
- `groups.requires_invoice`、`groups.bank_statement_as_invoice`、`groups.no_invoice_required` 三组，供前端展示。
- 每组 `tags[*]` 至少包含 `code`、`label`、`status`、`output_primary_label`、`output_sub_label`、`output_third_label`。
- `groups.requires_invoice.tag_codes` 等于 `available_tags` 中所有 `status=active` 标签 code 减去两个可编辑组 code 后的有序补集。
- 兼容字段 `pending_invoice_tag_groups.groups.requires_invoice.tag_codes` 在响应中也镜像派生结果，但不作为可编辑持久化事实。
- 兼容字段 `bank_transaction_tags` 可能包含历史流水分类字典或非规则 taxonomy，客户端不得用它替代 `available_tags` 渲染规则抽屉。

`PUT /api/pending-invoices/rules` 接受：

```json
{
  "groups": {
    "bank_statement_as_invoice": { "tag_codes": ["internal_transfer"] },
    "no_invoice_required": { "tag_codes": ["salary"] }
  }
}
```

- 后端只保存 `bank_statement_as_invoice` 和 `no_invoice_required`。
- 旧客户端如果提交 `requires_invoice`，后端接受但忽略，并在响应中按 active 补集重算。
- unknown tag、archived tag、重复分组校验只适用于两个可编辑持久化组。
- 成功后沿用设置服务版本、审计和持久化路径，并标记 pending invoice read model dirty。

规则组持久化银行明细标签 `code`，响应展示时实时从 `available_tags` 解析当前标签名称。银行标签改名后，本接口返回的新规则名称应同步变化；被两个可编辑规则组引用的银行标签不得在 `/api/bank-details/auto-tag-rules` 中停用。

`GET /api/pending-invoices/rows?direction=expense&filter=requires_invoice`、导出和 SQL pending invoice read model 也使用同一 active 补集语义：只有有效标签 code 位于 `available_tags` 补集中的支出流水才属于 `requires_invoice`。无有效标签、未知标签、已停用标签或仅存在于历史分类字典中的标签不得被强制归入 `requires_invoice`。

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
- stale/dirty 但已有可用 SQL 行：`200 OK`，返回最近一次稳定行数据，`read_model_status=refreshing` 或 `stale`，由后台 worker 收敛新版本；读请求不得重复写 dirty scope/outbox。
- missing 或 schema 不兼容：`202 Accepted`、`rows=[]`、`read_model_status=refreshing`，enqueue `pending_invoice.read_model.refresh`。
- API 热路径不得因 read model miss/stale 同步扫描全量事实。

实现阶段需要扩展 SQL query columns 和索引，至少覆盖 `status_code`、`seller_name`、`invoice_total`、`oa_applicant`、`project_name` 和筛选/排序需要的日期金额字段。
