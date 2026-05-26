# 关联工作台

## 目标

关联工作台是财务人员处理 OA、银行流水、发票三类对象的主入口。它负责展示已配对和待处理对象、确认关联、撤回配对、标记异常、忽略行、查看详情、搜索跳转和局部筛选。

## 三栏对象

- OA 栏：付款申请、报销单、项目或审批来源。
- 银行流水栏：收入、支出、账号、银行、对方户名、摘要、有效分类。
- 发票栏：销项、进项、ETC 附件发票、已认证发票等。
- OA 对应的发票栏只允许正式发票行，例如 `source_kind=oa_attachment_invoice`。付款凭证、未知附件、解析失败附件只能留在 OA 附件审计证据里，不进入发票栏、不进入配对关系。

收入侧原则上不走 OA；支出侧看 OA、支出流水和进项发票。

## 区域

- 未配对：`display_state=open` 的独立对象，可确认或转异常。
- 已配对：`display_state=paired` 的同组对象，来源可以是人工确认关系或自动确定性关系。
- 已忽略：用户主动忽略但可恢复的 override 视图，位于 `display_state` 之外，不是合法 `zone` 值。
- 已处理异常：结构化异常 case 处理后的异常视图，位于 `display_state` 之外，不是合法 `zone` 值。
- 区域标题显示该区域 OA、银行流水、发票三栏合计总项数，使用 `row_counts.rows` 或 `zone_counts.*.rows`，不显示 group 数；group 数只用于分页和内部组织。

## 展示状态和自动决策

- 前端和 API 当前展示状态只允许 `paired` 和 `open`，并通过 `zone=open|paired` 分页读取；`zone` 只接受 `open|paired`。
- Legacy/internal compatibility only: `needs_review` 和 `candidate` 只能出现在迁移期内部字段、调试信息或旧表兼容说明中，不能作为当前前端展示状态、zone 或筛选值。
- 自动决策使用 `display_state` 和 `decision_status` 两层字段：`display_state` 决定读模型和前端展示区，`decision_status` 表达自动决策生命周期，不直接作为前端展示状态。
- Warning 不是展示状态；带 warning 的自动关系仍可展示为 `paired`。

## 写模型

工作台写操作只改最小事实：

- `app.workbench_pair_relations`：确认关联、取消配对、免 OA 批次等手工关系事实。
- `workbench_row_overrides`：忽略、备注、非配对类覆盖。
- `workbench_exception_cases`：异常处理事实。
- 专项服务：如免 OA 批次、往来款关系、特殊规则服务。

手工关系事实继续归属 `app.workbench_pair_relations`；自动配对决策单独落入自动决策读模型，不镜像成手工关系。

## 读模型

页面加载优先读取结构化 SQL read model。服务端根据 source version、schema version、dirty scope 和 worker lag 判断当前 scope 是否需要重建；不得把是否存在整包 snapshot 作为首屏正确性的判断依据。

读模型必须按 scope 管理：

- `all`：跨月和全局工作台。
- `YYYY-MM`：月度视图，服务税金、成本、搜索跳转等场景。

首屏读取不得依赖全量页面快照：

- `GET /api/workbench/summary?month=all` 返回汇总、`read_model_status`、`generated_at`，以及轻量 `oa_status`/`invoice_inventory` 状态诊断；不得返回投影 group 或行级快照。
- `GET /api/workbench/groups?month=all&zone=open|paired&page=1&page_size=200&detail_level=summary` 返回当前页 group 摘要；支持服务端 `status`、`source_kind`、`search`、`sort=oa|bank|invoice:asc|desc`、`column_filters` 和 `time_filters`。前端首屏和分页必须使用 `summary`，避免把重 `detail_fields` 带入列表页。
- `detail_level=summary` 可以为了 payload 大小按栏裁剪 group 内预览行，但 OA 栏必须完整返回；`source_kind=oa_attachment_invoice` 的 OA 附件发票也必须完整返回，有多少显示多少，不走展开/收起。summary 响应仍必须返回未裁剪的 `row_counts`；当前端发现银行流水或非 OA 附件发票栏位 `row_counts` 大于已返回行数时，必须明确展示“当前显示/总数”，并通过 `/api/workbench/groups/detail` 读取完整 group。
- `GET /api/workbench/groups/detail?month=all&zone=open|paired&group_id=...` 返回单个 group 完整详情，用于详情抽屉、审计和需要重字段的交互。
- `GET /api/workbench/refresh-status` 返回 dirty scope、worker heartbeat/lag、failed backlog 和最近错误。
- 旧 `GET /api/workbench?month=all` 只作为兼容期接口，不再作为前端首屏依赖。

热路径基于结构化 SQL read model：

- `read_model.workbench_rows` 保存行级投影，用于详情定位、搜索和行级统计。
- `read_model.workbench_groups` 保存组级投影，用于首屏分页、区域分页、服务端筛选、搜索、排序和短 TTL page cache。
- `read_model.workbench_group_rows` 保存 group 内三栏行级筛选投影，用于列筛选和时间筛选；API 不得为了筛选读取 snapshot 大 JSON。
- `read_model.workbench_snapshots` 保留审计、导出、对账和兼容期用途，不作为首屏查询的数据源。

SQL 读模型只消费手工关系事实和自动决策结果，不在投影阶段重新生成或晋级配对。

## 自动配对契约

- 自动自由匹配覆盖两类确定性关系：
  - 支出方向：普通支出 OA、银行流出、进项或供应商发票，可形成 OA-银行-发票或两两关系。
  - 收入方向：收入流水与销项发票可形成银行-发票关系；收入侧没有 OA，不形成 OA-银行-发票三方关系。
- 收入流水匹配销项发票时，必须使用同方向、同购方/付款方主体证据，并通过完整候选窗口唯一性校验；不得仅凭金额自动关联。收入方向的主体证据来自银行对方户名/对方税号与销项发票购方名称/购方税号，销项发票销方不能作为收入流水的匹配主体。
- 银行摘要、备注中的购方名称、发票号、数电票号、合同号、订单号和项目号是收入 `bank_invoice` 的补强证据，可用于同主体同金额候选排序；但摘要/备注不能替代银行对方主体字段。没有银行对方户名/税号主体证据时，摘要/备注命中购方也不能自动关闭。
- 收入流水金额等于一张销项发票价税合计且候选唯一时，输出 `rule_code=bank_invoice_exact_amount`；收入流水金额等于多张同购方销项发票价税合计且组合唯一时，输出 `rule_code=bank_invoice_exact_sum`，`bank_row_ids` 包含一笔流水，`invoice_row_ids` 包含多张发票，并标记 `payment_amount_closed=true`、`invoice_amount_closed=true`。
- 一笔收入流水金额等于多张同金额销项发票各自金额时，不能把多张发票同时标记已收款。只有存在唯一最强证据候选时才自动选择一张；若最高证据并列或存在多个可行合计组合，必须输出结构化 `open` 决策和 blocker（如 `same_score_bank_invoice_candidates`、`multiple_bank_invoice_sum_candidates`），供页面和审计解释“为什么未关联”。
- 自由匹配窗口为 `T-2 / T / T+2`。当业务变化发生在 T 月时，引擎可读取前后各 2 个月的 OA、流水和发票候选池。
- 唯一性判断必须覆盖完整 5 个月候选窗口，不能只看 dirty 月份内是否唯一。
- 跨月自动决策只归属一个主月份：包含银行流水时使用银行交易月份；没有银行流水的 OA+发票关系使用 OA 月份。
- 多条已具备 OA-银行流水证据的付款项，可以自动合并匹配一张进项发票：每条 OA 金额必须等于对应银行流出金额，所有付款项合计必须等于发票价税合计，且发票与付款项之间必须有主体或文本证据；同一 5 个月窗口内存在多个可行付款组合或多张同金额可行发票时保持 `open` 冲突，不得随机自动配对。
- OA 来源附件发票与对应 OA 强关联。若 OA 金额等于银行流水金额，但正式附件发票合计不一致，仍可保持同组 `paired`，同时输出 `invoice_amount_mismatch` warning、`payment_amount_closed=true`、`invoice_amount_closed=false`。
- 特殊匹配和自由匹配共用 row 占用、生命周期、读模型和审计机制；特殊匹配不套用自由匹配的金额加文本重复规则。

## 自动执行机制

- 生产执行机制是 DB-backed dirty scope queue。数据变化提交后只标记 dirty scope，匹配由后台 worker 领取并执行。
- 写入 dirty scope 时按自由匹配窗口扩散到 `T-2 / T / T+2`，保证跨月候选能重新裁决。
- 进程内 dirty service 只可作为迁移期或单实例 fallback，不能作为生产正确性的依赖。
- 页面读取最近一次稳定 read model；当前 scope dirty 或 stale 时只触发后台刷新，不在用户请求线程内执行重匹配。

## 搜索、筛选和排序

- 三栏搜索是联动上下文搜索：用户在 OA、银行流水或发票任一栏输入关键词时，服务端必须在 OA、银行流水、发票三栏行级读模型中查找任意栏命中项，并返回命中项所在的业务组上下文。
- 搜索结果以业务组为单位展示。同一行只能来自同一个后端 group/context；命中项和它关联的另外两栏显示在同一行。禁止把 OA、流水、发票三个独立搜索列表按关键词临时拼接成假关联结果。
- 同一个业务组内多栏同时命中同一关键词时只展示一次，三栏命中字段都高亮；多个同名或同关键词对象属于不同业务组时必须拆成多行。
- 三栏联动搜索触发 `/api/workbench/groups?search=...&search_mode=linked_context` 重新读取首屏页；前端只保留当前分页窗口和后续显式加载的页，不再为了筛选/排序预取全量快照。
- 列筛选和时间筛选仍按各自栏位生效：同一栏内必须存在同一行满足该栏列筛选和时间筛选；多个栏同时有筛选条件时，业务组必须分别满足每个栏的条件。搜索词用于命中业务组上下文，不再作为单栏 `search_by_pane` 的同一行约束。
- 列筛选和时间筛选也必须进入 `/api/workbench/groups`，未加载的 group 只要命中 SQL read model 就能进入筛选后的分页结果；前端不得用已裁剪的 summary preview 再次排除服务端返回的 group。
- 银行流水栏金额按不带千分位分隔符的固定小数文本展示，例如 `19370.00`，以便财务人员按连续数字直接搜索。
- 多选筛选按列生效，不破坏业务组上下文。
- 排序按组排序，不按单行排序。
- 全局搜索要能跳回对应月份、区域、行和详情。

## 选择和确认关联

- 未配对区和已配对区分别维护显式选中的行；三栏搜索、列筛选、时间筛选只改变可见投影，不清空选中态。
- 选择汇总必须基于未过滤的当前读模型上下文计算，并在 OA、银行流水、发票三栏同时显示已选数量和金额。
- 显式选中的行显示为选中；由同一关系上下文自动带入的行显示为关联项，并参与汇总、预览和提交。
- 确认关联必须把显式选中项及其已有关系上下文一起写入 `app.workbench_pair_relations`。例如只显式选择 OA 和银行流水时，如果该 OA 有附件发票，预览和提交都必须连同附件发票一起配对。
- 前端可以为了预览体验提交上下文行，但最终完整性以后端 `confirm-link` 扩展逻辑为准；后端必须保证 preview 与 submit 使用同一套扩展规则。

## 折叠摘要

免 OA 批次等多流水组默认折叠时，必须由后端 group 契约输出：

- 摘要行。
- `display_mode=collapsed_summary`。
- `collapsed_rows` 保留原始行。
- 搜索、导出、撤回和审计仍能访问原始行。

免 OA 批次只有 `row_count >= 2` 时折叠；单条免 OA 批次保持普通银行行展示，但必须保留 `special_metadata.source_batch_id`、批次版本、免 OA tag 和撤回批次动作。

禁止只靠前端隐藏行。

## 验收标准

- 确认和撤回不触发整页同步重建。
- 操作结果返回受影响行和局部更新数据。
- read model、搜索缓存、详情接口和导出保持一致。
- 只读导出用户不能看到或触发写操作。
