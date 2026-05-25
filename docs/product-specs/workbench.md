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
- `detail_level=summary` 可以为了 payload 大小按栏裁剪 group 内预览行，但 `source_kind=oa_attachment_invoice` 的 OA 附件发票必须完整返回，有多少显示多少，不走展开/收起。summary 响应仍必须返回未裁剪的 `row_counts`；当前端发现非 OA 附件栏位 `row_counts` 大于已返回行数时，必须明确展示“当前显示/总数”，并通过 `/api/workbench/groups/detail` 读取完整 group。
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

- 自动自由匹配首版只覆盖支出方向：普通支出 OA、银行流出、进项或供应商发票。收入侧没有 OA，不进入 OA、流水、发票自由匹配。
- 自由匹配窗口为 `T-2 / T / T+2`。当业务变化发生在 T 月时，引擎可读取前后各 2 个月的 OA、流水和发票候选池。
- 唯一性判断必须覆盖完整 5 个月候选窗口，不能只看 dirty 月份内是否唯一。
- 跨月自动决策只归属一个主月份：包含银行流水时使用银行交易月份；没有银行流水的 OA+发票关系使用 OA 月份。
- OA 来源附件发票与对应 OA 强关联。若 OA 金额等于银行流水金额，但正式附件发票合计不一致，仍可保持同组 `paired`，同时输出 `invoice_amount_mismatch` warning、`payment_amount_closed=true`、`invoice_amount_closed=false`。
- 特殊匹配和自由匹配共用 row 占用、生命周期、读模型和审计机制；特殊匹配不套用自由匹配的金额加文本重复规则。

## 自动执行机制

- 生产执行机制是 DB-backed dirty scope queue。数据变化提交后只标记 dirty scope，匹配由后台 worker 领取并执行。
- 写入 dirty scope 时按自由匹配窗口扩散到 `T-2 / T / T+2`，保证跨月候选能重新裁决。
- 进程内 dirty service 只可作为迁移期或单实例 fallback，不能作为生产正确性的依赖。
- 页面读取最近一次稳定 read model；当前 scope dirty 或 stale 时只触发后台刷新，不在用户请求线程内执行重匹配。

## 搜索、筛选和排序

- 三栏局部搜索按当前栏驱动，整组联动。
- 三栏局部搜索、列筛选和时间筛选按交集组合：同一栏内必须存在同一行同时满足该栏搜索词、列筛选和时间筛选；多个栏同时有条件时，业务组必须分别满足每个栏的条件。
- 三栏局部搜索和时间排序触发 `/api/workbench/groups` 重新读取首屏页；前端只保留当前分页窗口和后续显式加载的页，不再为了筛选/排序预取全量快照。
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
