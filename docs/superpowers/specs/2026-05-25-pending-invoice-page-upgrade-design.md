# 待找发票页面升级设计

日期：2026-05-25

## 背景

现有 `待找发票` 页面已经位于左侧菜单和 `/pending-invoices` 路由，第一版能力是按银行流水展示已关联发票和 OA 申请人，并支持手工补票。用户希望基于 `/Users/yu/Desktop/sy/财务运营平台/界面.xlsx` 中 `（待找发票）以支出流水查看发票和OA`、`Sheet1`、`Sheet2`，把该页面升级为生产级、低耦合、高聚合的支出流水发票获取工作台。

本次不是新增一个相邻页面，而是原地升级现有 `待找发票`。页面布局参考已经落地的 `进项发票使用情况页面设计`，但主对象从进项发票反查改为支出银行流水查看发票、OA 和支付关系。用户明确要求继续使用 MUI `Table`，不使用 `DataGrid`。

## 已确认口径

- 原地升级现有 `待找发票` 菜单和 `/pending-invoices` 路由。
- 选择四大区布局 A：
  - `支出流水`
  - `发票获取状态`
  - `进项发票`
  - `OA`
- 主表继续使用 MUI `Table` 组件族，不使用 MUI X `DataGrid`。
- 表格必须尽量在一个页面宽度内展示，不出现横向滚动。
- 一行 = 一条支出流水。多发票、多 OA、多次支付不展开成多行，只展示 primary 摘要和 `+N`，完整关系进右侧抽屉。
- `Sheet1` 的入口放在 `发票获取状态` 列。状态列处理业务关系和支付明细；流水列、发票列、OA 列只负责对象详情。
- `支出流水无需开票规则设置` 的按钮范围调整为三组规则，按钮文案建议为 `待找发票规则设置`：
  - `需要开票`
  - `流水代替发票`
  - `无需开票`
- 三组规则使用同一份后端 `pending_invoice_tag_groups` 设置事实源，不新增另一套规则表。
- Redis 不作为首版必需依赖。首版正确性主链路是 PostgreSQL read model + durable refresh queue；Redis 只保留为后续短 TTL 热点缓存优化。
- 需要支持“筛选的内容可以导出”，导出当前筛选/排序命中的全量结果，不只导出当前页。
- 只读导出用户可查看、筛选、详情、导出；不可保存规则、补票、选择发票或建立关系。

## Excel 事实摘录

`（待找发票）以支出流水查看发票和OA` 表中原始列包括：

- 支出流水：支出银行、账户名称、交易时间、借方发生额、贷方发生额、余额、币种、对方户名、对方账号、对方开户机构、记账日期、摘要、备注、账户明细编号-交易流水号、企业流水号、凭证种类、凭证号。
- 发票获取状态：自动识别或人工标记的发票获取状态。
- 发票情况：数电发票号码、销方名称、开票日期。
- 操作入口：`支出流水无需开票规则设置（按钮）sheet2`、`筛选的内容可以导出（按钮）`、`增加备注类型（按钮）暂时想到五种`。

Excel 示例状态包含：

- `未支付完已开票`：点击详情可看每期支付并计算剩余未支付金额，参考 `Sheet1`。
- `已支付待后期集中开票`：多流水关联同一发票，计算支付金额和发票金额是否一致，参考 `Sheet1`。
- `无需开票`：只能根据规则自动识别，不能人工标记。
- `已支付已开票`：自动识别，关联台完全匹配。
- `已支付待开票`：关联台没找到发票且未命中筛选规则。

`Sheet1` 表示“选择之前开过的发票（自动带出上次和流水的关联情况）”和“增加这次支付情况”，需要展示：

- 已关联发票完整摘要。
- 历史支付日期和金额。
- 已支付合计。
- 待支付金额。
- 支付详情入口。

`Sheet2` 在 workbook 中是截图，内容对应现有设置页的 `待找发票筛选`：三组规则映射到银行明细标签。

## 目标

- 把现有 `待找发票` 页面升级为生产级支出流水发票获取工作台。
- 主表以支出流水为主对象，在一屏宽度内展示核心流水、状态、发票和 OA 信息。
- 将 Excel 的密集列合并为可扫描的小列，上下两行展示强相关字段。
- 发票获取状态由后端根据规则、关联事实和金额关系计算，前端不手算、不直接改状态。
- 通过右侧抽屉承载规则设置、支付关系、选择已有发票、对象详情和导出预览。
- 扩展现有 `/api/pending-invoices` 和 `read_model.pending_invoice_rows`，不新增平行业务模块。
- 导出、主表和抽屉使用同一套服务端事实和筛选口径。
- 保持权限、审计、幂等、read model 失效和可验证性。

## 非目标

- 不新增另一个左侧菜单页面。
- 不把收入侧 `待开发票` 一起升级为同等复杂工作台；收入方向保留旧能力，后续单独设计。
- 不使用 MUI X `DataGrid`。
- 不把 Sheet1 支付明细存成前端私有状态。
- 不绕过 `WorkbenchPairRelationService` 直接写关系。
- 不把 Redis 作为首版正确性依赖。
- 不在规则抽屉里新建银行明细标签；新增标签仍在设置页 `银行明细标签管理` 完成。
- 不在本次实现 Excel 中的 `增加备注类型` 入口；备注类型如果要做，需要单独确认字段来源、权限和审计口径。
- 不做假导出、假关系写入或假规则保存。

## 推荐方案

采用方案 B：升级现有待找发票模块，扩展 DTO、PostgreSQL read model、服务端导出和右侧工作流抽屉。

方案比较：

| 方案 | 内容 | 结论 |
| --- | --- | --- |
| A | 只改前端表格，复用现有 `/api/pending-invoices/rows` | 改动小，但 DTO 太薄，状态和 Sheet1 逻辑会被迫落前端，耦合高 |
| B | 原地升级现有模块、DTO、read model 和抽屉 | 推荐；符合现有架构，也支撑导出、权限和审计 |
| C | 新建统一“发票获取工作台”领域模块 | 长期完整，但扩大到跨页面重构，超出本次范围 |

## 架构边界

### 前端

- `PendingInvoicesPage`：页面状态、查询参数、抽屉开关、刷新协调。
- `PendingInvoicesTable`：四大区 MUI Table 展示，不写业务判断。
- `PendingInvoiceRulesDrawer`：三组规则设置。
- `PendingInvoiceRelationDrawer`：Sheet1 支付/发票关系明细。
- `PendingInvoiceInvoicePickerDrawer`：选择之前开过的发票并建立关系。
- `PendingInvoiceDetailDrawer`：流水、发票、OA 完整详情。
- `PendingInvoiceExportDrawer`：筛选导出预览和下载。
- `features/pendingInvoices/api.ts`：统一 API mapping，不在组件里拼后端字段。

### 后端

- 继续使用并升级 `PendingInvoiceQueryService`，输出四大区 DTO。
- 继续使用 `read_model.pending_invoice_rows` 作为列表热路径。
- 规则保存走 `AppSettingsService.pending_invoice_tag_groups`，由待找发票规则抽屉发起。
- 选择已有发票、手工补票、关系写入走 `PendingInvoiceApplicationService` 和 `WorkbenchPairRelationService`，不写页面私有事实。
- Sheet1 支付明细由 bank+invoice active relations 聚合得到。
- 导出服务使用同一套查询条件读取 read model。

数据流：

```text
导入事实 / OA projection / pair relations / 银行标签设置
        ↓ dirty scope + durable queue
read_model.pending_invoice_rows
        ↓
GET /api/pending-invoices/rows
        ↓
MUI Table 四大区列表
        ↓
状态列打开关系/规则/选择发票/导出抽屉
```

## 页面布局与列合并

主表四大区固定布局，建议宽度：

| 大区 | 宽度 | 小列 |
| --- | ---: | --- |
| `支出流水` | 42% | `对方 / 时间`、`金额 / 银行账户`、`摘要 / 凭证` |
| `发票获取状态` | 13% | `状态 / 依据 / 主操作` |
| `进项发票` | 28% | `发票号码 / 开票日期`、`销方 / 识别号`、`金额 / 支付差额` |
| `OA` | 17% | `申请人 / 类型`、`项目 / 详情` |

### 支出流水

`支出流水` 原 Excel 17 个字段合并为 3 个小列：

- `对方 / 时间`
  - 第一行：对方户名。
  - 第二行：交易时间 tag；必要时补对方账号尾号或开户行提示。
- `金额 / 银行账户`
  - 第一行：借方发生额，固定两位小数。
  - 第二行：银行 + 本方账户尾号 + 币种。
- `摘要 / 凭证`
  - 第一行：摘要。
  - 第二行：备注。
  - 凭证种类、凭证号、账户明细编号、企业流水号进入详情，不塞主表。

### 发票获取状态

独立一列，使用低饱和 warning 背景或语义色强调。

- 第一行：状态 chip。
- 第二行：规则命中依据或关系判断依据。
- 操作区：根据状态展示 `查看关系`、`查看支付明细`、`选择发票`、`补票`、`查看规则依据`。

### 进项发票

合并为 3 个小列：

- `发票号码 / 开票日期`
  - 第一行：优先数电发票号码；没有时显示发票代码 + 发票号码。
  - 第二行：开票日期 + `详情`。
- `销方 / 识别号`
  - 第一行：销方名称。
  - 第二行：销方识别号。
- `金额 / 支付差额`
  - 第一行：价税合计。
  - 第二行：已付合计 / 待付金额 / 差额摘要。
  - 复杂明细进入状态列关系抽屉。

### OA

合并为 2 个小列：

- `申请人 / 类型`
  - 第一行：申请人。
  - 第二行：报销/支付 tag + `详情`。
- `项目 / 关系`
  - 第一行：项目名称。
  - 第二行：关系数量或 OA 状态；多 OA 显示 `+N`。

### 显示规则

- 一行一条支出流水。
- 多发票、多 OA、多支付展示 primary 摘要和 `+N`。
- 文本默认两行收敛，超过显示展开箭头。
- 展开只影响当前单元格，不全表展开。
- 金额、日期、状态必须稳定宽度，避免表格跳动。
- 大区分隔线比小列分隔线更重。

## 发票获取状态

第一版固定 7 类：

| 状态 | 计算来源 | 主操作 |
| --- | --- | --- |
| `已支付已开票` | 当前支出流水已有 active bank+input invoice relation，金额闭合或关系完整 | 查看关系 |
| `已支付待开票` | 支出流水无进项发票，且未命中 `无需开票` / `流水代替发票` | 补票 / 选择发票 |
| `已支付待后期集中开票` | 已有稳定后端事实证明该流水进入后期开票累计，但尚未闭合正式发票 | 选择发票 / 查看累计 |
| `未支付完已开票` | 已有关联发票，但发票价税合计大于历史/当前支付合计 | 查看支付明细 |
| `无需开票` | 命中规则组 `no_invoice_required` | 查看规则依据 |
| `流水代替发票` | 命中规则组 `bank_statement_as_invoice`，且当前未绑定正式发票 | 选择发票 / 保留 |
| `待处理` | 规则和关系无法自动闭环 | 选择处理方向 |

状态只由后端规则和事实关系计算。前端只展示 `invoiceAcquisitionStatus` DTO 和可用操作。

首版状态优先级必须固定，避免前端或不同 worker 各自推断：

1. 已有 active bank+input invoice relation 且发票价税合计大于已付合计：`未支付完已开票`。
2. 已有 active bank+input invoice relation 且金额闭合或关系事实完整：`已支付已开票`。
3. 命中 `no_invoice_required` 规则组且没有正式发票关系：`无需开票`。
4. 命中 `bank_statement_as_invoice` 规则组且没有正式发票关系：`流水代替发票`。
5. 有明确后期开票累计事实（例如已存在的关系/命令/后端规则事实能证明多流水未来集中开票），但尚未闭合正式发票：`已支付待后期集中开票`。
6. 未命中免票/流水替票规则且未发现进项发票关系：`已支付待开票`。
7. 以上事实都不能可靠证明时：`待处理`。

`已支付待后期集中开票` 不能仅因为前端猜测、多条相似流水或普通 `bank_statement_as_invoice` 标签就自动成立；没有稳定后端事实时应落到 `流水代替发票`、`已支付待开票` 或 `待处理`。

## 右侧抽屉

### 待找发票规则设置

按钮文案建议 `待找发票规则设置`。抽屉管理同一份 `pending_invoice_tag_groups`：

- `需要开票`
- `流水代替发票`
- `无需开票`

规则：

- 每组只选择已有 active 银行明细标签。
- 同一标签不能同时归入多个组。
- 不存在或已停用标签不能保存。
- 保存后写设置审计，标记 pending invoice read model dirty，刷新当前列表和筛选项。
- 只读导出用户不可保存。

### Sheet1 关系抽屉

状态列打开 `PendingInvoiceRelationDrawer`，用于：

- 查看“选择之前开过的发票”。
- 查看发票已关联的历史支付流水。
- 展示本次支付、本次流水、已付合计、待付金额。
- 对 `已支付待后期集中开票` 执行“选择已有发票并建立关系”。
- 对 `未支付完已开票` 展示分期/多次支付明细。

写入规则：

- 选择已有发票时创建正式 bank+invoice pair relation。
- 后端重新计算金额差额和状态。
- 不把历史支付明细存成页面私有字段。
- 关系写入需要幂等 key、权限校验和审计。

### 对象详情抽屉

流水、发票、OA 的 `详情` 按钮只展示对象完整字段：

- 流水详情：Excel 中所有流水原始字段、账户明细编号、企业流水号、凭证字段、摘要备注。
- 发票详情：完整发票字段、货物/劳务明细、来源批次。
- OA 详情：申请人、类型、项目、金额、流程号、状态、可打开链接。

### 导出抽屉

`筛选的内容可以导出` 打开导出抽屉：

- 展示当前筛选、排序和预计导出行数。
- 调用服务端 export-preview。
- 下载服务端生成文件。
- 导出当前筛选/排序命中的全量结果，不只当前页。

## API 契约

扩展现有 `/api/pending-invoices`。

### 列表

```text
GET /api/pending-invoices/rows
```

参数：

```text
direction=expense
filter=all|requires_invoice|bank_statement_as_invoice|no_invoice_required
keyword=...
date_from=YYYY-MM-DD
date_to=YYYY-MM-DD
page=1
page_size=50
filters=<url-encoded json array>
sort_field=trade_date
sort_direction=desc
```

第一版复杂工作流只升级 `direction=expense`。收入方向保留旧能力。

### 筛选、排序和字段映射契约

后端 API 请求和响应字段使用 `snake_case`，前端 `web/src/features/pendingInvoices/api.ts` 负责映射为 TypeScript `camelCase`。组件不得直接猜后端字段。

`filters` 是 URL-encoded JSON array。每个元素结构固定：

```json
[
  { "field": "status_code", "operator": "in", "values": ["paid_pending_invoice"] },
  { "field": "trade_date", "operator": "between", "value": { "from": "2026-01-01", "to": "2026-01-31" } },
  { "field": "amount", "operator": "between", "value": { "min": "1000.00", "max": "20000.00" } },
  { "field": "summary_remark", "operator": "contains", "value": "维护费" }
]
```

允许字段和操作符：

| 字段 | 类型 | 操作符 |
| --- | --- | --- |
| `trade_date` | date | `between` |
| `bank_name` | text/enum | `in`, `contains` |
| `account_name` | text/enum | `in`, `contains` |
| `counterparty_name` | text | `contains`, `in` |
| `amount` | decimal | `between`, `eq` |
| `summary_remark` | text | `contains` |
| `status_code` | enum | `in` |
| `rule_group` | enum | `in` |
| `seller_name` | text | `contains`, `in` |
| `invoice_total` | decimal | `between`, `eq` |
| `oa_applicant` | text | `contains`, `in` |
| `project_name` | text | `contains`, `in` |

排序白名单：

- `trade_date`
- `amount`
- `counterparty_name`
- `status_code`
- `seller_name`
- `invoice_total`
- `oa_applicant`
- `project_name`

`sort_direction` 只允许 `asc` 或 `desc`。无效字段、无效操作符、非法日期/金额必须返回结构化 `400`，例如：

```json
{
  "error": {
    "code": "invalid_filter_field",
    "message": "Unsupported pending invoice filter field.",
    "details": { "field": "unknown_field" }
  }
}
```

列表、筛选项、导出预览和导出必须复用同一套解析和白名单；不能在不同 endpoint 里各自解释筛选条件。`invoice-candidates` 使用专用搜索参数和稳定默认排序，不接收列表页 `filters` JSON。

示例 DTO：

```json
{
  "id": "txn_...",
  "bank_transaction": {
    "id": "txn_...",
    "counterparty_name": "...",
    "counterparty_account_no": "...",
    "counterparty_bank_name": "...",
    "trade_time": "2026-01-08 14:59:45",
    "booked_date": "2026-01-08",
    "debit_amount": "19370.00",
    "credit_amount": "0.00",
    "balance": "159834.14",
    "currency": "人民币元",
    "bank_name": "建设银行",
    "account_name": "云南溯源科技有限公司",
    "account_last4": "0520",
    "summary": "电子转账",
    "remark": "维护费",
    "statement_serial_no": "13295-...",
    "enterprise_serial_no": "",
    "voucher_type": "电子转账凭证",
    "voucher_no": "108111326386"
  },
  "invoice_acquisition_status": {
    "code": "paid_pending_invoice",
    "label": "已支付待开票",
    "reason": "未命中无需开票规则，且未发现进项发票关系",
    "severity": "warning",
    "primary_action": "attach_or_create_invoice",
    "matched_rule": {
      "source": "pending_invoice_tag_groups",
      "group": "requires_invoice",
      "tag_code": "maintenance_fee",
      "tag_label": "维护费"
    }
  },
  "input_invoices": {
    "primary": {
      "id": "inv_...",
      "digital_invoice_no": "2653...",
      "invoice_no": "",
      "invoice_code": "",
      "issue_date": "2026-01-31",
      "seller_name": "...",
      "seller_tax_no": "...",
      "total_with_tax": "19370.00"
    },
    "relation_count": 1,
    "has_multiple": false,
    "payment_summary": {
      "paid_total": "19370.00",
      "invoice_total": "19370.00",
      "remaining_amount": "0.00",
      "difference_amount": "0.00"
    }
  },
  "oa": {
    "primary": {
      "id": "oa_...",
      "applicant": "张三",
      "application_type": "支付",
      "project_name": "维护项目",
      "status": "进行中"
    },
    "relation_count": 1,
    "has_multiple": false,
    "detail_available": true
  }
}
```

### 筛选项

```text
GET /api/pending-invoices/filter-options
```

返回字段配置、候选项和计数。字段包括交易时间、银行、对方户名、金额、摘要/备注、状态、规则组、销方、发票金额、OA 申请人、项目等。

### 关系与选择已有发票

```text
GET /api/pending-invoices/rows/{transactionId}/relation-detail
GET /api/pending-invoices/invoice-candidates
POST /api/pending-invoices/rows/{transactionId}/attach-existing-invoice/preview
POST /api/pending-invoices/rows/{transactionId}/attach-existing-invoice
```

`invoice-candidates` 用于 `Sheet1` 的“选择之前开过的发票”。参数：

```text
transaction_id=txn_...
keyword=...
seller_name=...
issue_date_from=YYYY-MM-DD
issue_date_to=YYYY-MM-DD
amount_min=...
amount_max=...
sort_field=issue_date
sort_direction=desc
page=1
page_size=20
```

返回已存在的进项发票候选，不创建发票，不写关系。候选项必须包含：

- 发票 id、数电发票号码、发票代码/号码、开票日期。
- 销方名称、销方识别号。
- 价税合计、已关联支付合计、待支付金额。
- 与当前流水的可关联状态：`available`、`already_related`、`conflict`。
- 冲突或不可选原因。

候选接口只做搜索和展示；真正建立关系必须经过 preview/confirm。默认排序为 `available` 优先、金额差额绝对值升序、开票日期倒序、发票 id 升序。允许候选排序字段为 `issue_date`、`total_with_tax`、`seller_name`、`amount_difference_abs`。

`attach-existing-invoice` 必须：

- 预览后确认。
- Preview 请求体使用 `invoice_id` 和可选 `request_id`，返回 `preview_id`、`request_key`、`can_confirm`、`transaction_summary`、`invoice_summary`、`payment_impact`、`affected_months`、`warnings`、`conflicts`、`expires_at`。
- Confirm 请求体使用 `preview_id`、`invoice_id`、`request_id`，其中 `request_id` 是 confirm 幂等键。
- 后端校验发票方向、active relation 冲突、权限。
- 写 pair relation、审计和 read model dirty scope。
- Confirm 返回 `status`、`request_id`、`request_key`、`transaction_id`、`invoice_id`、`relation_case_id`、`relation_mode`、`affected_transaction_ids`、`affected_invoice_ids`、`affected_months`，并可选返回更新后的 `row` DTO。
- 使用稳定 request key / command record / relation case id 处理重复提交。若 relation 已创建但响应、审计或 dirty enqueue 失败，重试必须补齐审计/dirty scope 并返回同一关系事实，不能创建重复关系。

### 对象详情

```text
GET /api/pending-invoices/bank-transactions/{id}/detail
GET /api/pending-invoices/invoices/{id}/detail
GET /api/pending-invoices/oa/{id}/detail
```

### 规则

```text
GET /api/pending-invoices/rules
PUT /api/pending-invoices/rules
```

`PUT` 内部调用 `AppSettingsService` 保存同一份 `pending_invoice_tag_groups`。

### 导出

```text
GET /api/pending-invoices/export-preview
GET /api/pending-invoices/export
```

导出规则：

- 使用与列表相同 query 参数。
- 导出当前筛选/排序命中的全量结果。
- 文件内容可以比主表更全，包含被合并到详情里的流水凭证字段、发票字段、OA 字段、状态依据和关系金额。
- 只读导出用户可调用导出；无查看权限用户不能调用。
- 下载动作要写导出审计或结构化操作记录。审计写入失败不能改变导出数据，但必须记录结构化错误供运维排查。

## Read Model 与 Redis 边界

`read_model.pending_invoice_rows` payload 升级为页面 DTO，额外建立可查询字段：

- `direction`
- `filter_group`
- `status_code`
- `trade_date`
- `amount`
- `counterparty_name`
- `seller_name`
- `oa_applicant`
- `project_name`
- `searchable_text`

需要由实现阶段检查当前最新 migration 编号，并新增 PostgreSQL migration 扩展 `read_model.pending_invoice_rows` 的查询列和索引。至少覆盖：

- `status_code`
- `seller_name`
- `invoice_total`
- `oa_applicant`
- `project_name`
- 当前筛选/排序需要的稳定金额和日期字段

如果某些字段暂时只能从 JSON payload 得到，必须在实现报告里说明原因、性能影响和后续迁移计划；不能静默退化为 API 热路径全量扫描。

API miss/stale：

- fresh scope 的合法空结果必须返回 `200 OK`、`rows=[]`、`read_model_status=fresh`，不能当作 miss 无限刷新。
- missing scope 或 stale/dirty scope 才返回 `202 Accepted` 和 `read_model_status=refreshing`。
- missing/stale 时 enqueue `pending_invoice.read_model.refresh`。
- 不同步扫描全量发票、流水、OA 或关系数据。
- SQL repository 必须用 scope freshness / dirty scope 元数据判断 miss/stale，不能只用 `total == 0` 判定 read model 不存在。

Redis：

- 首版不新增 Redis 依赖。
- 如果上线压测发现同一筛选分页查询 p95 不达标，可加短 TTL 缓存。
- 缓存 key 必须包含 schema version、read model version/scope、direction、filter、keyword、column filters、sort、page/pageSize、权限层级。
- Redis 清空不影响正确性。

## 数据一致性、恢复与回滚

- 规则保存、选择已有发票、补票确认都必须使用后端事务或现有可恢复命令模式，不能出现“关系已写但审计/read model dirty 未写”的半状态。
- `attach-existing-invoice` 和补票确认必须带 `request_id` 作为幂等键，重复提交返回同一事实结果，不创建重复发票或重复关系。
- 写动作成功后必须标记 pending invoice read model dirty，并尽量标记受影响的 workbench/search/cost 相关 read model；如果队列不可用，要保留可恢复的 dirty scope 或明确失败。
- read model 可以通过现有 worker/rebuild 机制重建；导出和列表必须以同一 read model/query contract 为准。
- 回滚策略不是前端撤销状态，而是通过撤销/失效对应关系事实或恢复设置版本，再重建 read model。首版若不提供 UI 撤销，必须至少保证审计记录和命令记录足以人工恢复。
- 导出为只读操作，不写业务状态；导出审计失败不能影响文件生成，但必须记录结构化错误。

## 权限与审计

- 只读导出用户：可查看、筛选、详情、导出。
- 只读导出用户不可保存规则、补票、选择发票、建立关系。
- 写动作全部后端校验权限。
- 前端隐藏按钮不是安全边界。
- 规则保存、关系创建、补票确认、导出下载都要写审计或结构化操作记录。

## 验收标准

- `/pending-invoices` 原地升级，左侧菜单仍为 `待找发票`。
- 主表使用 MUI Table，不使用 DataGrid。
- 四大区布局在常见桌面宽度下无横向滚动。
- 一行一条支出流水，多发票/多 OA/多支付摘要展示 `+N`。
- `Sheet1` 入口在状态列，能查看历史支付、已付合计、待付金额，并能选择已有发票建立关系。
- `待找发票规则设置` 抽屉管理三组规则，保存同一份 `pending_invoice_tag_groups`。
- 状态由后端计算，前端不直接改状态。
- 导出当前筛选/排序命中全量结果。
- 只读导出用户可查看/导出，不可保存规则或建立关系。
- API miss/stale 不同步重建大结果集，只 enqueue read model refresh。
- Redis 不作为首版依赖。
- 文档使用中文更新。

## 测试建议

后端：

- `PendingInvoiceQueryService` 状态计算测试。
- read model projection payload 测试。
- 规则保存校验测试。
- attach existing invoice preview/confirm 幂等和冲突测试。
- export 使用同一筛选条件测试。
- 只读导出权限测试。
- filter JSON 字段/操作符/排序白名单和错误码测试。
- candidate invoices 搜索、分页、冲突状态测试。
- read model fresh empty、missing scope、stale scope 三种路径测试。
- attach-existing-invoice 重复提交和部分失败恢复测试。

前端：

- 主表四大区表头和关键字段渲染测试。
- 筛选/排序参数传递测试。
- 状态列动作打开正确抽屉测试。
- 规则抽屉保存/权限禁用测试。
- 导出预览和下载测试。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test
cd web && npm run build
```
