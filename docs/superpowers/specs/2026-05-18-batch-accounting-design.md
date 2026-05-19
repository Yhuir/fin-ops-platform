# 日常报销批量账务管理设计

## 背景

财务需要一个独立页面处理银行流水中对方户名精确等于“批量账务集中处理”的支出流水，并由人工为每条流水选择一项或多项“日常报销”OA。页面提交后必须写入关联台统一的 pair relation，使关联台进入已配对状态；撤回后必须回到提交前状态，不能拆散提交前已经同组的 OA 与发票附件。

本设计不新增一套独立配对事实表。批量账务页面只是一个受控业务入口，底层继续使用工作台 pair relation、history、read model invalidation 和权限审计能力。

## 目标

- 左侧菜单新增“批量账务”页面，页面标题为“日常报销批量账务管理”。
- 页面支持 `未提交 / 已提交` 切换，左栏和右栏各自有年份选择器。
- 左栏显示流水年份内对方户名精确等于“批量账务集中处理”的银行流水。
- 右栏显示 OA 年份内可关联的未配对日常报销 OA，支持多选、跨年份保留已选项、实时合计、金额闭环校验。
- 提交时把一条银行流水、一条或多条 OA、以及这些 OA 在未配对区域同组的发票附件一起写成 pair relation。
- 已提交页签可查看已关联结果并撤回，撤回恢复提交前 pair relation 状态。

## 非目标

- 不做自动匹配或自动提交。
- 不重新实现发票匹配。只携带工作台未配对区域中已经与 OA 同组的发票附件。
- 不允许金额不一致通过备注放行。
- 不支持非“批量账务集中处理”对方户名的银行流水。
- 不做复杂搜索或自动推荐；跨年份选择仅通过左右栏独立年份筛选和人工多选完成。

## 业务口径

### 未提交

未提交指银行流水尚未通过批量账务页面创建 active `batch_accounting` relation。

左栏未提交流水必须同时满足：

- `counterparty_name` 精确等于 `批量账务集中处理`。
- 交易年份等于左栏流水年份。
- 是支出流水。
- 当前没有 active relation 占用，或者至少没有 active `batch_accounting` relation。

右栏未提交 OA 必须同时满足：

- 交易/申请年份等于右栏 OA 年份。
- OA `apply_type` 或 `expense_type` 属于“日常报销”。
- 是整单 OA 行，不按 schedule 明细拆分。
- 当前未处于 active pair relation 中。

### 已提交

已提交指存在 active pair relation，且该 relation 的 `special_metadata.source` 为 `batch_accounting`。已提交页签左栏显示这些 relation 中的银行流水，右栏显示选中流水所在 relation 关联的 OA 与发票附件摘要。

### 金额校验

提交前必须满足：

```text
选中 OA 金额总和 == 左侧银行流水支出金额
```

不相等时提交按钮禁用，接口也必须返回 400，错误码建议为 `batch_accounting_amount_mismatch`。

### 发票附件

每个选中 OA 只携带当前工作台未配对区域中已经与该 OA 同组展示的发票附件。提交时不额外搜索发票。

### 撤回

撤回只允许撤回 `special_metadata.source == "batch_accounting"` 的 active relation。撤回必须使用 pair relation history 恢复提交前状态：

- 银行流水回到批量账务未提交。
- 如果 OA 与发票附件在提交前已经同组，撤回后仍保持同组。
- 不按行逐个清空 relation，避免拆散前态。

## 后端 API

### GET /api/batch-accounting

查询批量账务页面数据。

Query:

- `bank_year`: 左栏银行流水四位年份，例如 `2026`。
- `oa_year`: 右栏 OA 四位年份，例如 `2025`。
- `year`: 兼容旧调用；未传 `bank_year` 或 `oa_year` 时作为两者的 fallback。
- `bucket`: `unsubmitted` 或 `submitted`。

Response:

```json
{
  "summary": {
    "unsubmitted_count": 3,
    "submitted_count": 8,
    "bank_year": "2026",
    "oa_year": "2025"
  },
  "bank_rows": [
    {
      "id": "txn_imported_0001",
      "trade_time": "2026-01-07 15:54:00",
      "counterparty_name": "批量账务集中处理",
      "direction": "expense",
      "direction_label": "支出",
      "amount": "1200.00",
      "bank_name": "建行",
      "account_last4": "8106",
      "relation_id": "",
      "version": 1
    }
  ],
  "oa_rows": [
    {
      "id": "oa-exp-1994",
      "applicant": "刘晨",
      "apply_time": "2026-01-06",
      "project_name": "品牌广告投放；市场活动项目",
      "amount": "1200.00",
      "reason": "1月日常报销",
      "linked_invoice_row_ids": ["oa-att-inv-oa-exp-1994-01"]
    }
  ]
}
```

未提交 bucket 的 `oa_rows` 是可选 OA 池。已提交 bucket 的 `oa_rows` 可以是当前默认选中或每个银行 relation 的已关联 OA 列表；实现上推荐返回 `relations_by_bank_row_id`，前端按左栏选中项读取。

### POST /api/batch-accounting/submit

提交关联。

Request:

```json
{
  "bank_year": "2026",
  "oa_year": "2025",
  "bank_row_id": "txn_imported_0001",
  "oa_row_ids": ["oa-exp-1994", "oa-exp-1995"],
  "expected_version": 1
}
```

服务端必须重新校验：

- 银行流水仍然是左栏流水年份、对方户名精确等于“批量账务集中处理”的支出流水。
- 银行流水没有 active relation 占用。
- 每个 OA 仍然是未配对、日常报销整单 OA；提交允许已选 OA 来自不同申请年份，以支持用户切换右栏年份后保留选择。
- OA 金额总和等于银行支出金额。
- 发票附件仍来自 OA 当前未配对同组。

成功后创建 pair relation：

- `relation_mode`: `manual_confirmed`
- `special_metadata.source`: `batch_accounting`
- `special_metadata.bank_row_id`: 提交的银行流水 id
- `special_metadata.oa_row_ids`: 提交的 OA id 列表
- `special_metadata.invoice_row_ids`: 自动带入的附件发票 id 列表
- `special_metadata.year`: 兼容字段，等于 `bank_year`
- `special_metadata.bank_year`: 左栏流水年份
- `special_metadata.oa_year`: 提交时右栏筛选年份
- `special_metadata.oa_years`: 实际选中 OA 的年份集合

Response:

```json
{
  "success": true,
  "relation_id": "CASE-...",
  "affected_row_ids": ["txn_imported_0001", "oa-exp-1994", "oa-att-inv-oa-exp-1994-01"],
  "affected_months": ["2026-01"],
  "message": "已关联批量账务流水与 2 项 OA。"
}
```

### POST /api/batch-accounting/{relation_id}/withdraw

撤回关联。

Request:

```json
{
  "reason": "选择错误",
  "expected_version": 2
}
```

服务端必须校验 relation 是 active 且 `special_metadata.source == "batch_accounting"`，然后调用 pair relation 的 withdraw history restore 能力。

## 前端设计

路由：`/batch-accounting`

菜单：财务业务组中放在“免OA流水批量处理”附近。

页面标题：`日常报销批量账务管理`

顶部：

- `未提交 / 已提交` ToggleButton。
- 刷新按钮。

主体：

- 左栏宽度约 30%，列表项形式展示银行流水。
- 右栏宽度约 70%，表格展示 OA。
- 左栏表头放 `流水年份` 输入；右栏表头放 `OA年份` 输入。
- 切换任一栏年份不得清空另一栏或右栏已选 OA；已选项需要保留完整行快照，用于金额合计和提交。

左栏列表项：

- 第一行固定主体：`批量账务集中处理`
- 时间 tag：`2026-01-07 15:54:00`
- 金额
- 方向 tag：`支出`
- 账户 tag：`建行 8106`

右栏表头：

- 银行流水金额。
- 已选 OA 数量。
- 已选 OA 金额总和。
- 差额。
- 未提交按钮：`关联OA项与流水`
- 已提交按钮：`撤回关联`

右栏表格：

- 第一列：申请人；第二行时间 tag。
- 第二列：项目名称，长文本省略，有展开/收起。
- 第三列：金额。
- 第四列：申请事由，长文本省略，有展开/收起。
- 未提交显示 checkbox，多选。
- 已提交只读展示，不显示 checkbox。

## 权限、审计、并发

- API mutation 必须复用 OA session 权限检查，只有可写用户可提交/撤回。
- 提交和撤回必须记录 actor、时间、note/reason。
- 提交必须重新读当前工作台状态，不能信任前端传来的金额、发票 id。
- 并发冲突返回 409 或明确 400 错误，前端提示刷新。

## 验证

后端测试：

- 列表只返回精确对方户名。
- 列表只返回支出流水。
- 未提交 OA 只返回未配对日常报销整单 OA。
- `bank_year` 与 `oa_year` 可独立过滤，支持 2026 流水搭配 2025 OA。
- 提交允许已选 OA 来自多个申请年份，并记录 `bank_year`、`oa_year`、`oa_years`。
- 提交金额不等返回 400。
- 提交成功写入 `batch_accounting` metadata。
- OA 同组发票附件被带入 relation。
- 已提交列表数量增加。
- 撤回恢复 before relation，OA + 发票附件保持同组。

前端测试：

- 菜单和路由可达。
- 页面标题、切换按钮、左右栏年份选择器、双栏布局。
- 左栏项非表格展示。
- 右栏 OA 多选实时更新数量、合计和差额。
- 切换右栏年份不丢失已选流水或已选 OA，并可提交跨年份选择。
- 金额不等时提交按钮禁用。
- 提交成功后未提交减少、已提交增加。
- 已提交撤回后回到未提交。
