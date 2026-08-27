# 发票生命周期、待找发票与 OA 待付款

本文维护进项/销项发票、待找发票、发票使用状态、OA 待付款核对和发票关系的当前业务口径。

## 发票生命周期原则

发票状态应由统一 lifecycle policy 判定，页面不各自定义状态：

- 导入/识别状态：是否存在、是否完整、是否可参与候选匹配。
- 认证/抵扣状态：是否认证、是否进入税金抵扣链路。
- 使用/收款状态：是否已和支出流水、OA 付款或销项收款建立关系。
- 异常状态：重复、冲突、缺少来源、金额/税额不一致、关系撤回。

当前架构按页面事实源选择生命周期边界：

- `InvoiceLifecyclePolicy` 是待找发票、进项付款、OA 付款和税局认证状态的共享规则入口。
- `read_model.invoice_lifecycle_rows` 是跨页面分发边界，按月分片预计算 subject lifecycle。HTTP 热路径只批量读取 read model，不同步扫描发票、银行流水、OA 和关联台事实。
- 销项发票收款情况是显式例外：它不读取 `invoice_lifecycle` 或页面 read model，而是在同一 canonical PostgreSQL snapshot 中根据销项发票、收入流水和 active Workbench 关系直接派生 `collectionStatus`。
- 销项红字发票原始备注中精确标记的“被红冲蓝字数电发票号码”是销项页面红蓝票关系的业务证据，同时驱动列表、详情、搜索、导出和 `collectionStatus`。号码必须唯一命中一张正数 canonical 销项发票；不按金额、税额、购销方或日期兜底猜测。
- 现有页面 API shape 保持明确：待找发票返回 `invoice_acquisition_status`，进项使用返回 `paymentStatus`，OA 待付款返回 `paymentStatus`，销项收款返回 `collectionStatus`，税金抵扣返回认证字段。
- 页面自己的 read model 仍保留筛选、分页、导出和页面 DTO；生命周期 read model 只分发生命周期结果，不替代业务页面 read model。

需要接入生命周期的页面：

| 页面 | subject | lifecycle 字段 |
| --- | --- | --- |
| 待找发票 | `bank_transaction` | `acquisition_status` |
| 进项发票使用情况 | `input_invoice` | `payment_status`、后续 `certification_status` |
| OA 待付款核对 | `oa_application` | `payment_status` |
| 销项发票收款情况 | `output_invoice` | canonical query 派生 `pending_collection`、`partial_collected`、`collected`、`reversed_by_red`、`reverses_blue`、`unmatched_red` |
| 税金抵扣 | `input_invoice` | `certification_status` |

进项发票使用情况和销项发票收款情况的页面表头发票数量用于核对发票拉取完整性，必须读取 rows summary 中按唯一发票 ID 统计的 `invoiceCount`。销项发票收款情况每个 canonical 发票 ID 固定一行，因此无筛选时 `pagination.total` 必须与 `invoiceCount` 相等；任何 Workbench relation 或红蓝票关系均不得折叠销项发票行。

## 待找发票

待找发票页面关注支出/收入流水的发票获取状态：

- 列表读取支出/收入流水、候选发票、规则建议、选择已有发票关系和收入状态覆盖。
- 筛选覆盖月份、项目、付款对象、状态、异常和规则命中。
- 筛选状态必须以最终 `invoice_acquisition_status.code` 闭环。`requires_invoice` 作为列表 filter 表达“需要开票”状态桶：支出包含 `paid_pending_invoice`、`paid_invoiced`、`paid_pending_future_invoice`、`invoice_not_fully_paid`；收入包含 `income_pending_invoice`、`income_invoiced`。`filter_group` / `matched_rule` 只解释命中的规则，不作为父筛选可见性的事实源。
- `bank_statement_as_invoice`、`no_invoice_required`、`cash_income` 也按最终状态筛选。特别是 `bank_statement_as_invoice` 只展示最终仍为“流水代替发票”的流水；如果同一流水已关联发票并变成 `paid_invoiced`，不能继续出现在“流水代替发票”筛选结果里。
- 支出侧选择多条流水后从选中工具栏进入“选择发票”，只允许选择已有进项发票并写入统一 Workbench relation command。
- 收入侧支持多选后批量标记“无需开票”或“现金收入”；后端必须先完成整批校验再一次写入，不允许前端逐行循环造成半成功。
- 待找发票页面不提供 manual invoice preview/confirm 或“补票”新写入口。单张发票只能从“发票导入 → 发票录入”进入统一 file import preview/confirm 链；旧 pending-invoice manual service 写链已删除，历史 command 表只保留既有数据和当前待找发票其它 command 类型。
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

规则保存成功后发布 `pending_invoice_rules_changed`，刷新 `invoice_lifecycle`、待找发票、关联台、进项使用、销项收款、税金抵扣、成本统计和搜索 read model。OA 待付款的 `InvoiceLifecyclePolicy.evaluate_oa_payment` 不读取待找发票规则，因此该事件不得刷新 `oa_pending_payment`；也不得刷新外部往来款台账、免 OA 批次或银行账户余额。

## OA 待付款核对

OA 待付款核对页用于对齐 OA 单据、付款流水和进项发票，并通过页面内切换区分已完成 OA 与进行中 OA：

- 唯一首屏 rows API 必须返回 payment、invoice、status、relation 和 filter options；未正式化的自动匹配 decision 不作为 OA 待付款业务关系状态，旧 filter endpoint 不存在。页面为 direct canonical read，不返回 ETag、read-model freshness、refresh job 或 operation barrier。
- 页面只读取 PostgreSQL canonical snapshot。OA integration sync负责将外部 OA/MySQL 完整事实提交为 completed projection、in-progress admission 和 payment-status snapshot；外部变化未进入 PG 时按 sync lag 处理，不能让页面 live scan 掩盖。
- `view_mode=completed` 展示普通 `app.oa_applications` 中已完成或历史未带workflow status的OA，不受 `t_payment_simple` 准入限制；`view_mode=in_progress` 只展示已由 `t_payment_simple.flow_id` 准入、匹配OA Mongo `form_data._id` 且当前仍进行中的snapshot。OA完成后下一次OA sync必须从admission删除并进入completed projection。
- `t_payment_simple.id` 不是 OA ID；支付状态展示和写回使用同一 `flow_id`。OA 系统中因网络波动重复提交、但未进入 `t_payment_simple` 的 OA 不展示。
- rows summary 必须提供 `viewCounts.completed/in_progress`，用于“已完成 OA N条 / 进行中 OA N条”切换按钮；该数量与当前搜索/筛选条件一致，并按唯一 OA ID 计数，不按表格配对组行数计数。同一 relation 下多条 OA 折叠成一行时，`viewCounts` 计多条 OA，`pagination.total` / `summary.rowCount` 仍计一行。
- 普通 `app.oa_applications` 投影只承载已完成/历史未知OA；`app.oa_pending_payment_admissions`只承载已进入App的in-progress准入snapshot。二者与payment-status snapshot由OA sync原子提交，OA专属worker只在PG内分流/构建。
- `filterOptions` 随同一 rows snapshot 由后端 set-based 计算，不能前端自造枚举。
- 关联关系必须来自关联台 Workbench active relation；同一 relation 下出现多条 OA、支出流水或进项发票时，OA 待付款只展示一条核对行，金额为各自合计，并通过明细展开所有 OA、流水或发票。
- completed 与 in-progress 使用同一套 OA、支付状态、流水、发票四分组表格，并只认 `app.workbench_pair_relations.status='active'`。历史 OA pending relation/claim 不参与查询、占用或 promotion；未正式化 decision 不能自动写回 OA。
- 付款状态只有“已支付/未支付”。active linked relation驱动“已支付”；金额差异、缺失银行事实或非支出边只作为reason和写回阻断，不产生“待核对/支付多了/多条OA合并支付”等第三状态。
- 用户点击逐行“写回”，或in-progress显式关联支出流水且金额匹配后，后端必须校验active relation、outflow、金额相等和flow id，再幂等写MySQL `pay_status=1`，并更新PG payment snapshot、月份watermark和精确月份outbox。MySQL已paid时仍要修复PG；PG失败返回可安全重试错误。
- 实机验证显示 `t_payment_simple.flow_id` 对应 OA Mongo `form_data._id`，平台使用投影中的 `Mongo文档ID` 或 `oa-pay-/oa-exp-` 行 ID 后缀读写支付状态；Flowable 流程实例 ID 和流程请求 ID 只作为详情/诊断信息，不作为支付状态写回 key。
- 详情 API 返回可解释的来源、匹配关系和异常原因；relation 明细必须支持 OA、支出流水和进项发票三类。
- canonical repository 不可用时返回明确错误；页面保留现有内容与重试入口，不以旧 read model、空集或轮询 fallback 伪装成功。
- 页面右上角提供 OA 事实源 XLSX 导出，可选择已完成、进行中或两者。导出读取全部 canonical OA facts，不受页面月份、搜索、筛选、排序和分页影响；只含 OA 字段，不含流水、发票、关系或 raw payload。

## 发票关系影响

| 动作 | 影响 |
| --- | --- |
| 发票导入确认 | 自动匹配 decision、正式关系相关 read model、待找发票、税金抵扣、成本统计刷新 |
| 选择已有发票关系确认 | 支出流水发票状态、OA 待付款状态、关联台关系刷新 |
| 收入状态覆盖 | 待找发票和搜索刷新；不得误刷税金、成本或银行余额 |
| 撤回发票关系 | 相关页面回到待处理或异常状态 |
| 发票认证/抵扣变化 | 税金抵扣和发票使用 read model 刷新 |

需要生命周期 read model 的事实变化必须先 dirty/enqueue
`invoice_lifecycle.read_model.refresh`，再刷新其真实下游。销项收款不属于该 fan-out：
它在每次查询时直接读取 canonical 事实与 active Workbench 关系，不得通过
`invoice_lifecycle`、页面 read model 或隐藏 fallback 获得状态。

## 相关文档

- API 契约：`../dev/api-contracts.md`
- Runtime：`../app-architecture/runtime-and-ownership.md`
- Worker：`../operations/runtime-worker-governance.md`
