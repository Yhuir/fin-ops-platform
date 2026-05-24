# 进项发票使用情况页面设计

日期：2026-05-24

## 背景

用户希望在左侧菜单新增一个按进项发票反查 OA 和银行流水的页面。页面参考 `/Users/yu/Desktop/sy/财务运营平台/界面.xlsx` 中 `（进项发票使用情况）以进项发票查询oa和流水`、`Sheet4` 和 `Sheet5`，但不能照搬 Excel 的密集表格形态。

本页面是生产级整合需求，不接受救急或临时方案。实现必须融合现有架构，保持低耦合、高聚合，并使用 MUI 原生高性能组件。第一版范围是“真实只读查询 + 生产级 API 契约设计”。`发票反提 OA` 已确认是后续必须做的正式能力，设计必须提前纳入，并参考 ETC 管理页面的“提交 OA / 创建 OA 草稿”流程。

## 已确认口径

- 新增左侧菜单页面，页面名为 `进项发票使用情况`，建议路由 `/input-invoice-usage`。
- 页面 UI 参考 Excel 的 `（进项发票使用情况）以进项发票查询oa和流水` 子表，但必须降低信息密度。
- 不使用 `DataGrid`。页面表格使用 MUI 原生 `Table` 组件族，例如 `TableContainer`、`Table`、`TableHead`、`TableBody`、`TableRow`、`TableCell`、`TablePagination`、`TableSortLabel`、`Menu`、`Checkbox`、`Radio`。
- 使用服务端分页、筛选和排序，避免一次性把大量行放到前端。
- 一行 = 一张发票。Excel 中同一张发票可能有 3 条货物/劳务明细，落到页面时必须聚合为一张发票一行，明细进入详情。
- 不做两层表头。可以分大列，大列下面有小列；小列标题只在表头出现一次，数据行里不能每项上方都重复显示“表 col”。
- 如果一行不够，每个小列内允许自然换行；第二行还放不下时显示向下箭头/展开按钮。
- 每个大列下面的小列之间要有分隔，小列分隔不能和大列分割线一样，需要更轻、更细，视觉上有层级。
- `支付状态` 大列需要合适背景色，和其余大列区分。
- 每个小列都要有合适的筛选/排序菜单：
  - 枚举字段用单选或多选。
  - 菜单包含全选、清空。
  - 菜单包含升序、降序排序。
  - 筛选和排序都必须走后端 API。
- `发票号码` 小列显示发票号码，日期右侧新增 `详情` 按钮。
- `流水` 的 `对方户名` 小列下方显示交易日期，日期右侧新增 `详情` 按钮。
- 所有 `详情` 按钮都要打开该项完整信息，不能只重复当前行摘要。
- `以发票反提 OA` 不使用弹窗，不新增左侧菜单项，点击后从右侧弹出工作流抽屉。
- `发票与支付状态规则设置` 不使用弹窗，不新增左侧菜单项，点击后从右侧弹出工作流抽屉。
- 右侧工作流抽屉交互要类似 Codex 的“显示/隐藏侧边栏”，滑动必须丝滑。抽屉打开/关闭不能触发表格整页重取和明显卡顿。
- `发票反提 OA` 后续必须做。第一版先做真实只读查询和正式 API 契约；反提 OA 的正式写入路径按 ETC 的“创建 OA 草稿、打开草稿、检测 OA 进入进行中、撤销草稿/释放本地绑定、审计和幂等”设计。

## Excel 事实摘录

目标 sheet 标题为 `（进项发票使用情况）以进项发票查询oa和流水`，表内标题为 `（进项发票使用情况）以发票查询oa和流水`。

主要按钮：

- `以发票反提OA(详见sheet5)`。
- `发票与支付状态规则设置（按钮）详见sheet4`。
- `筛选的内容可以导出`。

目标 sheet 原始列：

- 发票：发票代码、发票号码、数电发票号码、销方识别号、销方名称、购方识别号、购买方名称、开票日期、税收分类编码、特定业务类型、货物或应税劳务名称、规格型号、单位、数量、单价、金额、税率、税额、价税合计、发票来源、发票票种、发票状态、是否正数发票、发票风险等级、开票人、备注。
- 支付状态：支付状态。
- OA：申请人、报销/支付、项目名称、查看详情。
- 流水：支付银行、交易时间、借方发生额、支出、币种、对方户名、对方账号、对方开户机构、记账日期、摘要、备注。

Sheet4 支付状态规则：

- `待付款（自动识别有oa无流水）`：有发票、有 OA、无流水。
- `已付款（自动识别有oa有流水）`：有发票、有 OA、有流水，并且关联台完全匹配。
- `现金往来（自动识别陈秀云oa，有流水）`：有发票、有流水、OA 申请人为陈秀云，并且关联台完全匹配。
- `冲（自动识别周洁莹oa，无流水）`：有发票、OA 申请人为周洁莹、无流水，发票和 OA 金额匹配。
- `冲（自动识别刘树刚不付oa，无流水）`：有发票、OA 申请人为刘树刚不付、无流水。
- `冲（自动识别韦代连oa，无流水）`：有发票、OA 申请人为韦代连、无流水。
- `待处理（详见下表待处理下拉框）`：有发票但规则不能自动闭环。

Sheet4 待处理下拉方向：

- `待处理`
- `韦代连批量反提oa`
- `陈秀云批量反提oa`
- `周洁莹批量反提oa`
- `刘树刚付批量反提oa`
- `刘树刚不付批量反提oa`
- `刘涵静批量反提oa`

Sheet5 反提 OA 预览：

- 主表按上述状态/标签筛选后集中处理提交 OA。
- 预览区展示发票号码、销方、开票日期、价税合计、状态。
- 同一发票多行明细可勾选/合并，最后按目标 OA 账号提交一张 OA。
- 示例为以陈秀云账号提交合计金额 `99.72` 的 OA，并记录这些发票和 OA 的关系。

## 目标

- 新增 `进项发票使用情况` 页面，以发票为主对象反查支付状态、OA 和银行流水。
- 页面在一个页面宽度内显示核心信息，不出现横向滚动。
- 通过大列和小列合并降低 Excel 式密度。
- 每张发票只显示一行，发票明细和完整字段通过详情查看。
- 提供服务端分页、筛选、排序、详情加载、状态汇总和规则读取 API。
- 为后续 `发票反提 OA` 和 `支付状态规则设置` 设计生产级写入契约，但第一版不做临时写逻辑。
- 保持前后端模块边界清晰，不把税金、关联台、ETC、银行明细页面职责混到一个大服务中。

## 非目标

- 第一版不创建真实 OA 草稿，不提交 OA，不轮询 OA 系统。
- 第一版不把支付状态规则改成前端硬编码可保存配置。
- 第一版不新增持久化 `input_invoice_usage_rows` read model 表。
- 不重做关联台三栏匹配流程。
- 不迁移或重构 ETC 页面，只参考其 OA 草稿模式。
- 不引入新的表格库或 UI 库。
- 不为了展示方便复制业务事实到页面私有存储。

## 推荐架构

采用独立页面模块 + 独立查询服务 + 可升级 DTO/read-model 边界。

后端新增 `InputInvoiceUsageQueryService`。它只负责聚合读取现有事实源并输出页面 DTO：

- 进项发票事实源。
- 发票行项目或导入原始字段。
- 银行流水事实源。
- 关联台 active pair relations。
- OA 行或 OA 关系投影。
- 支付状态规则。

第一版服务可以实时查询和聚合，不新增持久 read model。API DTO 命名、字段和分页契约必须按 read model 方式设计，后续如果性能不足，可新增物化 read model 或 SQL 视图，而不改变前端契约。

后续写入能力拆成两个高聚合服务：

- `InputInvoiceUsageOaReverseService`：负责反提 OA 预览、批次、创建 OA 草稿、检测、撤销、审计、幂等。
- `InputInvoicePaymentStatusRuleService`：负责规则读取、版本化保存、冲突校验、重算触发、审计。

## 页面信息架构

页面主区域为单页工作台。

顶部工具条：

- 关键字搜索。
- 开票日期范围或月份。
- 支付状态筛选快捷入口。
- `以发票反提 OA` 按钮。
- `发票与支付状态规则设置` 按钮。
- 导出按钮可作为后续能力，第一版如未实现必须不展示或以明确权限/能力状态控制，不能做假导出。

主体表格分 4 个大列：

1. `进项发票`
2. `支付状态`
3. `OA`
4. `流水`

### 大列 1：进项发票

小列建议：

- `发票号码`
  - 优先显示数电发票号码。
  - 没有数电发票号码时显示 `发票代码 + 发票号码`。
  - 下方显示开票日期 tag。
  - 日期右侧显示 `详情` 按钮，打开完整发票详情。
- `销方`
  - 第一行销方名称。
  - 第二行销方识别号。
- `价税合计`
  - 显示价税合计。
- `不含税 / 税率税额`
  - 第一行不含税金额。
  - 第二行 `税率 (税额)`，例如 `6% (3.96)`。
- `业务 / 货物劳务`
  - 第一行业务类型。
  - 第二行货物或应税劳务名称。

### 大列 2：支付状态

单独大列，使用浅色背景区分。建议背景使用 warning 低饱和 token，例如 `warning.light` 叠加低透明度，文本仍保持高对比。

内容：

- 状态 tag，例如 `待处理`、`待付款`、`已付款`、`冲`、`现金往来`。
- 第二行显示命中依据摘要，例如 `自动识别有 OA 无流水`。
- 如果规则说明或待处理标签过长，第二行后显示展开箭头。

### 大列 3：OA

小列建议：

- `OA申请人`
  - 第一行申请人。
  - 第二行 `报销` / `支付` tag。
  - tag 右侧或同一行末尾显示 `详情` 按钮，打开完整 OA 信息。
- `项目名称`
  - 显示项目名称。
  - 过长允许两行，超过两行显示展开箭头。

OA 字段不能猜。没有稳定 OA 关系时显示 `—`，详情按钮不展示或置为不可点击状态。

### 大列 4：流水

小列建议：

- `对方户名`
  - 第一行对方户名。
  - 第二行交易时间 tag。
  - 日期右侧显示 `详情` 按钮，打开完整流水详情。
- `金额`
  - 第一行金额。
  - 第二行 `收/支` tag + 支付银行和账号后四位。
- `摘要/备注`
  - 第一行摘要。
  - 第二行备注。
  - 超过两行显示展开箭头。

## 表格布局与性能

页面必须在常见桌面宽度内避免横向滚动。建议使用固定表格布局和响应式宽度：

- `进项发票`：约 44%。
- `支付状态`：约 12%。
- `OA`：约 18%。
- `流水`：约 26%。

每个小列使用 `maxWidth`、`minWidth`、`line-clamp` 或等价 CSS 控制两行显示。展开按钮只展开当前行或当前单元，不改变所有行高度。

MUI Table 性能原则：

- 每页默认 50 条，可选 20/50/100。
- 服务端分页、筛选和排序。
- `filter-options` 按当前查询上下文懒加载。
- 详情接口按需加载，不随列表一起拉全量详情。
- 抽屉数据按打开后加载，并显示 skeleton。
- 打开/关闭抽屉不重取主表。
- 避免大面积 box-shadow、blur 和 layout animation。

## 筛选与排序

每个小列表头都有菜单入口。菜单能力由后端字段配置驱动，不在前端硬编码完整枚举。

字段模式：

- `text`：关键字包含、清空、排序。
- `enum_single`：单选、清空、排序。
- `enum_multi`：多选、全选、清空、排序。
- `date`：日期范围、清空、排序。
- `money`：金额区间、清空、排序。

关键字段建议：

- 发票号码：文本 + 排序。
- 开票日期：日期范围 + 排序。
- 销方：多选/搜索 + 排序。
- 价税合计：金额区间 + 排序。
- 税率：多选 + 排序。
- 业务类型：多选。
- 支付状态：多选。
- OA 申请人：多选 + 排序。
- 报销/支付：单选或多选。
- 项目名称：文本/多选。
- 对方户名：文本/多选 + 排序。
- 交易时间：日期范围 + 排序。
- 流水金额：金额区间 + 排序。
- 支付银行：多选。

## 右侧工作流抽屉

两个按钮均打开右侧工作流抽屉，不使用 `Dialog`，不新增左侧菜单项。

通用要求：

- 使用 MUI `Drawer anchor="right"` 或封装后的 `AppDrawer`。
- 桌面宽度建议 `min(720px, 48vw)` 到 `min(920px, 58vw)`，移动端全屏。
- `transitionDuration` 建议 enter 180ms、exit 140ms。
- 抽屉移动使用 transform，不推动主表布局。
- 抽屉内部可滚动，主页面不抖动。
- 两个工作流抽屉互斥，同时只能打开一个。
- 抽屉状态可进入 `usePageSessionState`，避免关闭/切页后丢失当前预览选择。

### 反提 OA 工作流抽屉

组件建议命名 `OaReverseWorkspaceDrawer`。

第一版能力：

- 基于当前筛选条件或选中发票打开预览。
- 调用后端真实只读 `oa-reverse/preview`，展示后端返回的候选发票数、价税合计、目标 OA 账号/申请人分组、不可提交原因。
- 展示发票清单，仍然一张发票一行。
- 不创建真实 OA 草稿。
- 前端不能在浏览器本地自行计算预览总数、合计金额或不可提交原因，不能伪造成功写入。

后续正式写入能力：

- 创建 `input_invoice_usage_oa_reverse_batch` 或等价业务批次。
- 使用 `expectedVersion` 做乐观锁。
- 使用 `idempotencyKey` 做幂等。
- 创建 OA 草稿，而不是直接提交 OA。
- 成功后保存 `oaDraftId`、`oaDraftUrl`、本地批次状态和发票-OA 关系。
- 打开 OA 草稿 URL。
- 后台检测 OA 是否进入 `进行中`。
- 如果金额错误、发票缺漏或不准备提交，提供“撤销草稿/释放本地绑定”，系统不删除 OA 源系统草稿，只解绑本地 active 草稿并保留审计。
- 人工标记只作为检测异常兜底。

该流程参考现有 ETC 管理页面：

- `POST /api/etc/business-batches/{businessBatchId}/oa-draft`
- `POST /api/etc/business-batches/{businessBatchId}/oa-draft/revoke`
- `POST /api/etc/business-batches/{businessBatchId}/oa-status/refresh`
- `POST /api/etc/business-batches/{businessBatchId}/manual-oa-status`

进项发票反提 OA 不能复用 ETC 业务批次模型本身，但必须复用其设计原则：草稿、检测、撤销、版本、幂等、审计和权限。

### 支付状态规则工作流抽屉

组件建议命名 `PaymentStatusRulesDrawer`。

第一版能力：

- 展示 Sheet4 的状态规则矩阵。
- 展示待处理下拉方向。
- 从后端读取规则配置或服务内规则投影。
- 只读查看，不展示可编辑控件、保存按钮或“已保存”状态。

后续正式写入能力：

- 支持版本化保存规则。
- 支持规则冲突校验。
- 保存后写审计。
- 保存后触发支付状态重算或标记相关读模型失效。
- 与列表 API 使用同一套规则事实源。

## API 契约

新增 API 分组 `/api/input-invoice-usage`。

### 查询列表

```text
GET /api/input-invoice-usage/rows
```

查询参数：

```text
page=1
page_size=50
keyword=...
invoice_date_from=YYYY-MM-DD
invoice_date_to=YYYY-MM-DD
month=YYYY-MM
filters=<url-encoded json array>
sort_field=invoice_date
sort_direction=asc|desc
```

第一版只支持单字段排序，不做多字段排序。`filters` 使用 URL 编码 JSON 数组，不能混用重复 query key，避免前后端各自发明解析规则。

筛选对象结构：

```json
[
  {
    "field": "seller_name",
    "operator": "in",
    "values": ["云南中招招标有限公司"]
  },
  {
    "field": "total_with_tax",
    "operator": "between",
    "value": { "min": "0.00", "max": "1000.00" }
  }
]
```

允许字段和操作符：

| field | 类型 | 支持操作符 | 可排序 |
| --- | --- | --- | --- |
| `invoice_no` | text | `contains`, `equals` | 是 |
| `invoice_date` | date | `between`, `equals` | 是 |
| `seller_name` | enum_multi/text | `in`, `contains` | 是 |
| `seller_tax_no` | text | `contains`, `equals` | 是 |
| `total_with_tax` | money | `between`, `equals` | 是 |
| `amount` | money | `between`, `equals` | 是 |
| `tax_rate` | enum_multi | `in` | 是 |
| `tax_amount` | money | `between`, `equals` | 是 |
| `specific_business_type` | enum_multi | `in` | 否 |
| `taxable_item_name` | enum_multi/text | `in`, `contains` | 否 |
| `payment_status` | enum_multi | `in` | 是 |
| `oa_applicant` | enum_multi | `in` | 是 |
| `oa_application_type` | enum_single/enum_multi | `in`, `equals` | 是 |
| `oa_project_name` | enum_multi/text | `in`, `contains` | 是 |
| `bank_counterparty_name` | enum_multi/text | `in`, `contains` | 是 |
| `bank_trade_time` | date | `between`, `equals` | 是 |
| `bank_amount` | money | `between`, `equals` | 是 |
| `bank_name` | enum_multi | `in` | 是 |
| `bank_summary` | text | `contains` | 否 |

无效字段、无效操作符、金额/日期格式错误必须返回结构化 `400`，不能静默忽略。

响应：

```json
{
  "rows": [
    {
      "id": "invoice_usage_row_...",
      "invoiceId": "invoice_...",
      "invoiceIdentityKey": "digital:26372000000458116231",
      "invoice": {
        "invoiceNo": "26372000000458116231",
        "invoiceCode": "",
        "digitalInvoiceNo": "26372000000458116231",
        "invoiceDate": "2026-05-08",
        "sellerName": "云南中招招标有限公司",
        "sellerTaxNo": "9153...",
        "totalWithTax": "70.00",
        "amount": "66.04",
        "taxRate": "6%",
        "taxAmount": "3.96",
        "specificBusinessType": "",
        "taxableItemName": "服务费",
        "lineItemCount": 3,
        "hasMoreInvoiceLines": true
      },
      "paymentStatus": {
        "code": "pending",
        "label": "待处理",
        "reason": "规则不能自动闭环",
        "matchedRuleId": "pending_default",
        "severity": "warning"
      },
      "oa": {
        "primaryOaId": "oa_...",
        "applicantName": "陈秀云",
        "applicationType": "报销",
        "projectName": "项目名称",
        "relationCount": 2,
        "hasMultiple": true,
        "detailMode": "list",
        "detailAvailable": true,
        "summaries": [
          {
            "oaId": "oa_...",
            "applicantName": "陈秀云",
            "applicationType": "报销",
            "projectName": "项目名称",
            "amount": "70.00",
            "status": "进行中"
          }
        ]
      },
      "bankTransactions": {
        "primaryBankTransactionId": "bank_txn_...",
        "counterpartyName": "云南中招招标有限公司",
        "tradeTime": "2026-05-09 10:20:00",
        "amount": "70.00",
        "direction": "outflow",
        "bankName": "中国银行",
        "accountLast4": "1234",
        "summary": "服务费",
        "remark": "",
        "relationCount": 1,
        "hasMultiple": false,
        "detailMode": "single",
        "summaries": [
          {
            "bankTransactionId": "bank_txn_...",
            "counterpartyName": "云南中招招标有限公司",
            "tradeTime": "2026-05-09 10:20:00",
            "amount": "70.00",
            "direction": "outflow",
            "bankName": "中国银行",
            "accountLast4": "1234"
          }
        ]
      }
    }
  ],
  "pagination": {
    "page": 1,
    "pageSize": 50,
    "total": 118
  },
  "summary": {
    "invoiceCount": 118,
    "totalWithTax": "12345.67",
    "matchedOaCount": 10,
    "matchedBankTransactionCount": 11,
    "pendingCount": 6
  },
  "appliedFilters": {},
  "sort": {
    "field": "invoice_date",
    "direction": "desc"
  }
}
```

一张发票可能关联多条 OA 或多条流水。列表行必须按确定性规则选择 primary summary 供表格展示，不能随机取第一条：

1. 优先选择与当前发票处在同一 active relation 且关系完整度最高的记录。
2. 其次选择金额与发票价税合计最接近的记录。
3. 再按业务时间倒序。
4. 最后按稳定 ID 升序。

如果 `hasMultiple=true`，表格显示 primary summary 和 `+N` 数量提示；详情按钮打开该行的关系列表详情，而不是只打开 primary 记录。关系列表内每条记录必须能继续查看完整字段。没有稳定 OA 或流水关系时，`detailMode="none"` 且前端不展示可点击详情。

### 筛选项

```text
GET /api/input-invoice-usage/filter-options
```

查询参数包含当前页面上下文，例如日期、关键字和已应用筛选。响应返回每个字段的候选项、计数、筛选模式和排序能力。

示例响应：

```json
{
  "fields": [
    {
      "field": "payment_status",
      "label": "支付状态",
      "mode": "enum_multi",
      "operators": ["in"],
      "sortable": true,
      "options": [
        { "value": "pending", "label": "待处理", "count": 6 },
        { "value": "paid", "label": "已付款", "count": 1 }
      ]
    },
    {
      "field": "invoice_date",
      "label": "开票日期",
      "mode": "date",
      "operators": ["between", "equals"],
      "sortable": true,
      "options": []
    }
  ],
  "context": {
    "keyword": "",
    "invoiceDateFrom": "2026-05-01",
    "invoiceDateTo": "2026-05-31",
    "filters": []
  }
}
```

`filter-options` 返回的是当前上下文中的候选项和计数。例如已经筛了月份，就只返回该月份内的销方、申请人和支付状态候选。

### 详情接口

```text
GET /api/input-invoice-usage/invoices/{invoiceId}/detail
GET /api/input-invoice-usage/bank-transactions/{bankTransactionId}/detail
GET /api/input-invoice-usage/oa/{oaId}/detail
GET /api/input-invoice-usage/rows/{rowId}/relation-details?kind=oa|bank
```

发票详情必须包含：

- 页面展示字段完整值。
- 购方字段。
- 发票来源、票种、状态、正数/负数、风险等级、开票人、备注。
- 货物/劳务明细数组。
- 来源批次和 source links。

流水详情必须包含：

- 页面展示字段完整值。
- 对方账号、开户机构、记账日期、原始摘要/备注。
- 银行原始文本字段。
- 关联关系摘要。

OA 详情必须包含：

- 申请人。
- 报销/支付类型。
- 项目名称。
- OA 单号、状态、金额、创建/提交时间、可打开 URL。
- 与当前发票的关系依据。

如果当前系统没有稳定 OA 详情投影，第一版必须明确返回 `detailAvailable=false`，前端不展示假详情。

`relation-details` 用于 `hasMultiple=true` 的行级详情。它返回当前发票关联的全部 OA 或流水 summary、关联依据、完整详情可用性，以及每条记录的详情 ID。前端点击列表内单条记录时再调用单条详情接口。

### 支付状态规则

```text
GET /api/input-invoice-usage/payment-status-rules
```

响应包含规则版本、规则矩阵和待处理下拉项。

第一版规则抽屉是只读查看。除非同时实现 `PUT`、版本校验、幂等、审计、重算/失效和测试，否则前端不能展示可编辑控件、保存按钮或“已保存”状态。

后续写接口：

```text
PUT /api/input-invoice-usage/payment-status-rules
```

请求必须包含：

- `expectedVersion`
- `idempotencyKey`
- 规则矩阵。
- 待处理下拉映射。

保存必须校验冲突、写审计、触发支付状态重算或失效。

### 反提 OA 契约

第一版实现真实只读 `preview`，用于右侧抽屉展示候选数量、合计、分组和不可提交原因。第一版不创建真实 OA 草稿，不保存批次，不提交 OA。后续正式写入接口如下。

```text
POST /api/input-invoice-usage/oa-reverse/preview
POST /api/input-invoice-usage/oa-reverse/batches
GET  /api/input-invoice-usage/oa-reverse/batches/{batchId}
POST /api/input-invoice-usage/oa-reverse/batches/{batchId}/oa-draft
POST /api/input-invoice-usage/oa-reverse/batches/{batchId}/oa-draft/revoke
POST /api/input-invoice-usage/oa-reverse/batches/{batchId}/oa-status/refresh
POST /api/input-invoice-usage/oa-reverse/batches/{batchId}/manual-oa-status
```

`preview` 请求可以基于当前筛选条件或显式发票 ID：

```json
{
  "source": "currentFilters",
  "filters": [],
  "invoiceIds": [],
  "targetApplicantCode": "chen_xiuyun"
}
```

`preview` 响应：

```json
{
  "previewId": "oa_reverse_preview_...",
  "source": "currentFilters",
  "invoiceCount": 8,
  "totalWithTax": "99.72",
  "groups": [
    {
      "targetApplicantCode": "chen_xiuyun",
      "targetApplicantName": "陈秀云",
      "invoiceCount": 8,
      "totalWithTax": "99.72",
      "candidateInvoiceIds": ["invoice_1"],
      "rejectedInvoices": [
        {
          "invoiceId": "invoice_2",
          "reasonCode": "already_has_active_oa",
          "reason": "发票已有 active OA 关系"
        }
      ]
    }
  ],
  "warnings": [],
  "canCreateDraft": false,
  "nextAction": "future_contract_only"
}
```

第一版前端只能展示后端返回的 preview 数据，不能在浏览器本地自行计算候选数量、金额合计或不可提交原因。

后续 `batches` 创建响应必须包含：

```json
{
  "batchId": "oa_reverse_batch_...",
  "version": 1,
  "status": "previewed",
  "selectedInvoiceIds": ["invoice_1"],
  "rejectedInvoices": [],
  "totalWithTax": "99.72",
  "targetApplicantCode": "chen_xiuyun",
  "auditEventId": "audit_..."
}
```

`oa-draft` 请求：

```json
{
  "expectedVersion": 3,
  "idempotencyKey": "oa-reverse-batch-001-create-draft"
}
```

`oa-draft` 成功响应必须包含：

```json
{
  "batchId": "oa_reverse_batch_...",
  "version": 4,
  "status": "oa_submission_detecting",
  "oaDraftId": "oa_draft_...",
  "oaDraftUrl": "https://oa.example/draft/...",
  "idempotentReplay": false,
  "auditEventId": "audit_..."
}
```

如果已有 active 草稿，重复调用返回同一个 `oaDraftId`、`oaDraftUrl`，并设置 `idempotentReplay=true` 或等价字段。撤销草稿响应必须包含新 `version`、`status=not_submitted|revoked`、释放的发票 ID、审计事件 ID。检测刷新响应必须包含 `oaProcessStatus`、`oaDetectionStatus`、`nextRunAt`、`attempts` 和冲突候选。所有写接口必须返回明确错误码，例如 `version_conflict`、`idempotency_conflict`、`invoice_already_bound`、`oa_draft_unavailable`、`permission_denied`。

状态建议：

```text
draft
previewed
oa_draft_creating
oa_submission_detecting
oa_submitted
oa_draft_failed
oa_detection_timeout
oa_detection_conflict
oa_detection_unavailable
not_submitted
manually_marked_submitted
manually_marked_not_submitted
revoked
```

## 前端模块边界

建议文件：

```text
web/src/pages/InputInvoiceUsagePage.tsx
web/src/features/inputInvoiceUsage/types.ts
web/src/features/inputInvoiceUsage/api.ts
web/src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx
web/src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx
web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx
web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx
web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx
web/src/components/inputInvoiceUsage/ExpandableCellText.tsx
```

职责：

- `InputInvoiceUsagePage`：页面状态、查询参数、抽屉互斥、调用 API。
- `api.ts`：只封装 `/api/input-invoice-usage`。
- `types.ts`：DTO 类型和筛选/排序类型。
- `InputInvoiceUsageTable`：纯展示表格，接收 rows、loading、pagination、sort/filter callbacks。
- `InputInvoiceUsageFilterMenu`：小列表头菜单。
- `InputInvoiceUsageDetailDrawer`：发票/流水/OA 详情统一查看。
- `OaReverseWorkspaceDrawer`：反提 OA 预览和后续草稿工作流。
- `PaymentStatusRulesDrawer`：规则查看和后续设置工作流。
- `ExpandableCellText`：两行截断、展开、收起，避免散落重复 CSS。

不要在 `InputInvoiceUsagePage` 里堆积所有单元格渲染和 drawer 逻辑。

并行实现时的前端集成契约：

- `InputInvoiceUsagePage` 统一拥有列表数据、查询状态、筛选状态、排序状态、详情目标和工作流抽屉状态。
- `InputInvoiceUsageTable` 只通过 props 发出事件：`onFilterMenuOpen(field)`, `onSortChange(field, direction)`, `onOpenDetail(target)`, `onToggleCellExpand(rowId, cellId)`。
- `InputInvoiceUsageFilterMenu` 只接收 `fieldConfig`, `currentFilter`, `options`, `onApply(filter)`, `onClear(field)`, `onSort(direction)`。
- `InputInvoiceUsageDetailDrawer` 只接收 `target`, `open`, `loadDetail(target)`, `onClose()`；详情 API 函数由 `features/inputInvoiceUsage/api.ts` 提供，页面注入。
- `OaReverseWorkspaceDrawer` 只接收 `open`, `sourceFilters`, `selectedInvoiceIds`, `loadPreview(request)`, `onClose()`；第一版没有 `onSubmit`。
- `PaymentStatusRulesDrawer` 只接收 `open`, `loadRules()`, `onClose()`；第一版没有 `onSave`。
- 工作流抽屉状态统一为 `activeWorkflow: "oaReverse" | "paymentRules" | null`，详情抽屉状态统一为 `detailTarget: { kind: "invoice" | "bank" | "oa" | "relationList"; id: string; rowId?: string } | null`。

## 后端模块边界

建议文件：

```text
backend/src/fin_ops_platform/services/input_invoice_usage_service.py
tests/test_input_invoice_usage_service.py
tests/test_input_invoice_usage_api.py
```

如当前 server 路由仍集中在 `backend/src/fin_ops_platform/app/server.py`，第一版可按现有模式接入，但处理函数应尽量薄，只做参数解析、权限检查、服务调用和响应编码。

服务实现前必须记录实际读取的事实源。优先检查并复用：

- 发票事实：`backend/src/fin_ops_platform/services/imports.py` 中的 `Invoice`、导入服务或现有 PostgreSQL repository。
- 银行流水事实：`BankTransaction`、银行明细服务或现有 PostgreSQL repository。
- 关系事实：`backend/src/fin_ops_platform/services/workbench_pair_relation_service.py` 的 active pair relations，尤其 `row_ids`、`row_types`、`relation_mode`、撤销/审计状态。
- OA 投影：现有 OA projection、manual OA import、workbench row 或 PostgreSQL OA projection repository。找不到稳定投影时，DTO 必须显式 `detailAvailable=false`。
- 支付状态规则：本服务内只读规则投影，后续可切换到规则服务。

服务职责：

- 参数校验。
- 发票身份聚合。
- 发票明细聚合。
- OA 和流水关系解析。
- 支付状态计算。
- 筛选和排序。
- DTO 输出。

不负责：

- 不创建 OA。
- 不保存规则。
- 不修改关联台关系。
- 不修改发票或流水事实。

## 支付状态计算原则

支付状态来自规则服务，不在前端计算。

第一版规则按优先级顺序匹配，先命中的规则返回状态：

1. `现金往来（自动识别陈秀云oa，有流水）`：当前发票有 active OA 关系、active 流水关系，OA 申请人精确匹配规则配置中的陈秀云账号/名称，并且满足“完全匹配”。
2. `已付款（自动识别有oa有流水）`：当前发票有 active OA 关系、active 流水关系，并且满足“完全匹配”。
3. `冲（自动识别周洁莹oa，无流水）`：当前发票有 active OA 关系、无 active 流水关系，OA 申请人精确匹配周洁莹，并且发票价税合计与 OA 金额可证明匹配。
4. `冲（自动识别刘树刚不付oa，无流水）`：当前发票有 active OA 关系、无 active 流水关系，OA 申请人精确匹配刘树刚不付规则。
5. `冲（自动识别韦代连oa，无流水）`：当前发票有 active OA 关系、无 active 流水关系，OA 申请人精确匹配韦代连规则。
6. `待付款（自动识别有oa无流水）`：当前发票有 active OA 关系、无 active 流水关系，且没有命中更高优先级冲账规则。
7. `待处理`：当前发票存在，但无法证明命中以上规则，或规则所需证据缺失。

“完全匹配”第一版定义为：存在 active relation 使当前发票、至少一条 OA 记录和至少一条银行流水处在同一组关系中；关系没有撤销/冲突标记；发票价税合计、OA 金额和流水收支金额在同一方向上可证明一致，金额差异容忍不超过 `0.01`。如果现有 relation 只能证明部分关系，或金额字段缺失，不能判为 `已付款` 或 `现金往来`，必须降级为 `待处理` 并返回 `reason`。

申请人匹配必须来自规则配置或稳定映射，不能用随意字符串包含匹配。规则配置缺失时，服务只能返回保守状态。

## 权限、审计和一致性

第一版读接口：

- 需要和发票、流水、关联台页面一致的查看权限。
- 详情接口必须复用相同权限边界。
- 不返回用户无权查看的 OA、流水或发票详情。

后续写接口：

- 反提 OA 和规则保存都需要操作权限。
- 所有写接口必须带 `expectedVersion` 和 `idempotencyKey`。
- 所有写入必须写审计。
- 规则保存后必须重算或失效受影响状态。
- 反提 OA 创建草稿必须幂等，已有 active 草稿时返回已有草稿。
- 撤销草稿只释放本地绑定，不删除 OA 源系统草稿。

## 验收标准

功能验收：

- 左侧菜单出现 `进项发票使用情况`。
- 页面能真实读取进项发票数据。
- 每行是一张发票，不因货物/劳务明细拆成多行。
- 页面主体在桌面宽度无横向滚动。
- 小列标题只在表头出现一次，数据行不重复显示列名。
- 长文本两行内展示，超过两行有展开按钮。
- 发票日期右侧有发票详情按钮。
- 流水交易日期右侧有流水详情按钮。
- OA 有详情时可查看完整 OA 信息，无详情时不伪造。
- 支付状态列有差异化背景。
- 每个小列有筛选/排序菜单，并通过 API 刷新。
- `以发票反提 OA` 打开右侧工作流抽屉，不弹窗。
- `发票与支付状态规则设置` 打开右侧工作流抽屉，不弹窗。
- 两个抽屉互斥，打开/关闭不触发表格整页重取。
- 第一版如果没有实现真实导出，不能展示可点击的假导出入口。
- 页面不使用 `DataGrid`。

技术验收：

- 前端新增模块边界清晰，组件高聚合。
- 后端查询服务不污染税金、ETC、关联台核心服务。
- API DTO 可后续平滑切换到物化 read model。
- 详情接口按需加载。
- 单元测试覆盖发票聚合、筛选、排序、详情、规则读取和状态计算。
- 前端测试覆盖无 DataGrid、表头结构、展开、菜单、详情和两个抽屉。
- 运行 `npm test`、`npm run build`、后端相关 `unittest`。

## 最终执行 Prompt

完整可执行 prompt 已同步保存到：

```text
docs/superpowers/prompts/2026-05-24-input-invoice-usage-subagents.md
```

该 prompt 包含：

- `/goal`。
- 共享约束。
- 串行准备步骤。
- 可并行 worker 拆分。
- 每个 worker 的读文件、写文件、禁止范围、TDD 要求、验收和返回格式。
- 反提 OA 后续设计必须参考 ETC 创建草稿流程的要求。

## 风险和后续决策

- OA 详情字段如果现有系统没有稳定投影，第一版只能展示可证明字段。
- 实时聚合如果在生产数据量下变慢，下一阶段引入物化 read model，但不改变 API。
- 支付状态规则保存属于写入功能，必须单独进入 TDD 实现，不能在第一版用前端假保存。
- 反提 OA 创建草稿属于正式工作流，必须参考 ETC 的批次状态机、草稿、检测、撤销、幂等和审计，不能做一次性提交按钮。
