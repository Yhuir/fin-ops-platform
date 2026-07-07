# 发票生命周期、待找发票与 OA 待付款

本文维护进项/销项发票、待找发票、发票使用状态、OA 待付款核对和发票关系的当前业务口径。

## 发票生命周期原则

发票状态应由统一 lifecycle policy 判定，页面不各自定义状态：

- 导入/识别状态：是否存在、是否完整、是否可参与候选匹配。
- 认证/抵扣状态：是否认证、是否进入税金抵扣链路。
- 使用/收款状态：是否已和支出流水、OA 付款或销项收款建立关系。
- 异常状态：重复、冲突、缺少来源、金额/税额不一致、关系撤回。

当前架构采用 `InvoiceLifecyclePolicy` + `invoice_lifecycle` read boundary：

- `InvoiceLifecyclePolicy` 是唯一规则入口，负责待找发票获取状态、进项付款状态、OA 付款状态、销项收款状态和税局认证状态。
- `read_model.invoice_lifecycle_rows` 是跨页面分发边界，按月分片预计算 subject lifecycle。HTTP 热路径只批量读取 read model，不同步扫描发票、银行流水、OA 和关联台事实。
- 现有页面 API shape 保持兼容：待找发票继续返回 `invoice_acquisition_status`，进项使用继续返回 `paymentStatus`，OA 待付款继续返回 `paymentStatus`，销项收款继续返回 `collectionStatus`，税金抵扣继续返回认证字段。
- 页面自己的 read model 仍保留筛选、分页、导出和页面 DTO；生命周期 read model 只分发生命周期结果，不替代业务页面 read model。

需要接入生命周期的页面：

| 页面 | subject | lifecycle 字段 |
| --- | --- | --- |
| 待找发票 | `bank_transaction` | `acquisition_status` |
| 进项发票使用情况 | `input_invoice` | `payment_status`、后续 `certification_status` |
| OA 待付款核对 | `oa_application` | `payment_status` |
| 销项发票收款情况 | `output_invoice` | `collection_status` |
| 税金抵扣 | `input_invoice` | `certification_status` |

进项发票使用情况和销项发票收款情况的页面表头发票数量用于核对发票拉取完整性，必须读取 rows summary 中按唯一发票 ID 统计的 `invoiceCount`；`pagination.total` 仍表示表格行数或配对组行数。同一 linked relation 折叠多张发票到一行时，表头发票数必须计入所有成员发票，不能用行数替代。

## 待找发票

待找发票页面关注支出/收入流水的发票获取状态：

- 列表读取支出/收入流水、候选发票、规则建议、选择已有发票关系和收入状态覆盖。
- 筛选覆盖月份、项目、付款对象、状态、异常和规则命中。
- 筛选状态必须以最终 `invoice_acquisition_status.code` 闭环。`requires_invoice` 作为列表 filter 表达“需要开票”状态桶：支出包含 `paid_pending_invoice`、`paid_invoiced`、`paid_pending_future_invoice`、`invoice_not_fully_paid`；收入包含 `income_pending_invoice`、`income_invoiced`。`filter_group` / `matched_rule` 只解释命中的规则，不作为父筛选可见性的事实源。
- `bank_statement_as_invoice`、`no_invoice_required`、`cash_income` 也按最终状态筛选。特别是 `bank_statement_as_invoice` 只展示最终仍为“流水代替发票”的流水；如果同一流水已关联发票并变成 `paid_invoiced`，不能继续出现在“流水代替发票”筛选结果里。
- 支出侧选择多条流水后从选中工具栏进入“选择发票”，只允许选择已有进项发票并写入统一 Workbench relation command。
- 收入侧支持多选后批量标记“无需开票”或“现金收入”；后端必须先完成整批校验再一次写入，不允许前端逐行循环造成半成功。
- 当前页面不再提供 manual invoice preview/confirm 或“补票”新写入口；历史 manual command 只用于旧数据恢复/迁移兼容。
- 右侧工作流支持候选查看、关系明细、撤回和导出。
- OA、银行流水和发票配对展示以统一 Workbench relation / `workbench_relation` distribution 为事实源。同一 relation 下存在多笔流水时，待找发票列表仍按 relation 聚合为一行，但银行流水栏必须显示 `bank_transactions.summaries` 中的真实对方户名列表，不用 `+N` 替代户名，也不在对方户名下显示交易时间；流水详情通过该栏的详情入口展开。同一 relation 下存在多张 OA 或多张发票时，对应栏仍以 `+N` 表达该类型全部成员；包含在明细中的成员不得在同一栏再展示为单独 primary，也不得再作为 standalone relation 成员行重复出现。
- 刷新范围按动作分发：发票导入、选择已有发票关系和撤回关系进入发票生命周期链路；收入状态覆盖只刷新待找发票和搜索。

### 待找发票规则事实源

待找发票规则是独立规则集事实，不是银行标签设置的附属版本：

- `bank_transaction_tags.version` 只代表银行明细自动标签定义、自动匹配规则、归档/新增/重命名等标签事实。
- `pending_invoice_tag_groups.version` 只代表支出待找发票规则版本。
- `pending_output_invoice_tag_groups.version` 只代表收入待找发票规则版本。
- `requires_invoice` 是 active tag complement，由后端根据当前 active 标签和用户可编辑分组实时派生，不作为用户可编辑事实持久化。

将“外部往来款付款”等银行标签纳入 `no_invoice_required` 是合法的待找发票规则配置。它只改变待找发票/发票生命周期口径，不改变外部往来款台账准入，也不触发免 OA 批次重建。

规则保存成功后发布 `pending_invoice_rules_changed`，刷新 `invoice_lifecycle`、待找发票、关联台、进项使用、OA 待付款、销项收款、税金抵扣、成本统计和搜索 read model。该事件不得刷新外部往来款台账、免 OA 批次或银行账户余额。

## OA 待付款核对

OA 待付款核对页用于对齐 OA 单据、付款流水和进项发票，并通过页面内切换区分已完成 OA 与进行中 OA：

- rows/read model 必须返回 payment、invoice、status、relation、refresh 状态；未正式化的自动匹配 decision 不作为 OA 待付款业务关系状态。
- OA 范围以 OA MySQL `t_payment_simple.flow_id` 为准入事实源，不直接扫 OA Mongo 全量；`flow_id` 必须匹配 OA Mongo `form_data._id`，匹配成功后才进入本页面正常表格。
- `view_mode=completed` 是原 OA 待付款核对视图，只展示已进入 `t_payment_simple` 且已完成或历史未带 workflow status 的 OA；`view_mode=in_progress` 只展示已进入 `t_payment_simple` 且 OA 系统仍为进行中的支付申请/日常报销。OA 后续完成后，下一次 OA sync/read model refresh 必须从进行中视图移除。
- `t_payment_simple.id` 不是 OA ID；支付状态展示和写回使用同一 `flow_id`。OA 系统中因网络波动重复提交、但未进入 `t_payment_simple` 的 OA 不展示。
- rows summary 必须提供 `viewCounts.completed/in_progress`，用于“已完成 OA N条 / 进行中 OA N条”切换按钮；该数量与当前搜索/筛选条件一致，并按唯一 OA ID 计数，不按表格配对组行数计数。同一 relation 下多条 OA 折叠成一行时，`viewCounts` 计多条 OA，`pagination.total` / `summary.rowCount` 仍计一行。
- 普通 `app.oa_applications` 投影只承载已完成/历史未知 OA，供关联台、待找发票等页面消费；OA 待付款核对使用专用 payment-admitted OA projection/read model：先读 `t_payment_simple.flow_id`，再按 flow_id 精确读取 OA Mongo 当前记录，并按当前 workflow status 分流到 `completed` / `in_progress`。
- filter-options 需要与列表事实一致，不能前端自造枚举。
- 关联关系必须来自关联台 Workbench active relation；同一 relation 下出现多条 OA、支出流水或进项发票时，OA 待付款只展示一条核对行，金额为各自合计，并通过明细展开所有 OA、流水或发票。
- completed 与 in-progress 使用同一套 OA、支付状态、流水、发票四分组表格；进行中 OA 视图只把 Workbench active relation、OA 待付款独立 active pending relation 或自动匹配命令刚确认的 pending relation 当作付款证据，未正式化 decision 不能自动写回 OA。
- 付款状态不展示“支付多了”或“已支付（多条OA合并支付）”；多 OA 合并付款先按 relation group 合计，支出流水合计大于 OA 合计时进入待核对。
- 用户在进行中 OA 视图点击“确认已支付”后，后端必须校验 OA 仍为进行中、支出流水为 outflow、金额相等且能解析 OA Mongo 文档 ID，再确认 Workbench relation 并写回 OA MySQL `t_payment_simple.pay_status=1`。
- 实机验证显示 `t_payment_simple.flow_id` 对应 OA Mongo `form_data._id`，平台使用投影中的 `Mongo文档ID` 或 `oa-pay-/oa-exp-` 行 ID 后缀读写支付状态；Flowable 流程实例 ID 和流程请求 ID 只作为详情/诊断信息，不作为支付状态写回 key。
- 详情 API 返回可解释的来源、匹配关系和异常原因；relation 明细必须支持 OA、支出流水和进项发票三类。
- SQL read model 刷新失败时，页面必须展示 stale/refreshing 状态。

## 发票关系影响

| 动作 | 影响 |
| --- | --- |
| 发票导入确认 | 自动匹配 decision、正式关系相关 read model、待找发票、税金抵扣、成本统计刷新 |
| 选择已有发票关系确认 | 支出流水发票状态、OA 待付款状态、关联台关系刷新 |
| 收入状态覆盖 | 待找发票和搜索刷新；不得误刷税金、成本或银行余额 |
| 撤回发票关系 | 相关页面回到待处理或异常状态 |
| 发票认证/抵扣变化 | 税金抵扣和发票使用 read model 刷新 |

生命周期变化必须先 dirty/enqueue `invoice_lifecycle.read_model.refresh`，再刷新待找发票、进项使用、OA 待付款、销项收款、税金抵扣、成本统计和搜索等下游页面 read model。

## 相关文档

- API 契约：`../dev/api-contracts.md`
- Runtime：`../app-architecture/runtime-and-ownership.md`
- Worker：`../operations/runtime-worker-governance.md`
