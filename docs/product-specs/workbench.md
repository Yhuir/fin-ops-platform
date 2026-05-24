# 关联工作台

## 目标

关联工作台是财务人员处理 OA、银行流水、发票三类对象的主入口。它负责展示候选、确认关联、撤回配对、标记异常、忽略行、查看详情、搜索跳转和局部筛选。

## 三栏对象

- OA 栏：付款申请、报销单、项目或审批来源。
- 银行流水栏：收入、支出、账号、银行、对方户名、摘要、有效分类。
- 发票栏：销项、进项、ETC 附件发票、已认证发票等。

收入侧原则上不走 OA；支出侧看 OA、支出流水和进项发票。

## 区域

- 未配对：系统候选、待处理行、可确认或转异常的对象。
- 已配对：已经由 pair relation 或确定性关系表达的对象。
- 已忽略：用户主动忽略但可恢复的对象。
- 已处理异常：结构化异常 case 处理后的对象。

## 写模型

工作台写操作只改最小事实：

- `workbench_pair_relations`：确认关联、取消配对、免 OA 批次等关系事实。
- `workbench_row_overrides`：忽略、备注、非配对类覆盖。
- `workbench_exception_cases`：异常处理事实。
- 专项服务：如免 OA 批次、往来款关系、特殊规则服务。

## 读模型

页面加载优先读取 `workbench_read_models`。如果当前 scope 缺快照或版本不新鲜，才触发重建。

读模型必须按 scope 管理：

- `all`：跨月和全局工作台。
- `YYYY-MM`：月度视图，服务税金、成本、搜索跳转等场景。

首屏读取不得依赖全量页面快照：

- `GET /api/workbench/summary?month=all` 返回汇总、`read_model_status`、`generated_at`，以及轻量 `oa_status`/`invoice_inventory` 状态诊断；不得返回候选组或行级快照。
- `GET /api/workbench/groups?month=all&zone=open|paired&page=1&page_size=200&detail_level=summary` 返回当前页候选组摘要；支持服务端 `status`、`source_kind`、`search`、`sort=oa|bank|invoice:asc|desc`、`column_filters` 和 `time_filters`。前端首屏和分页必须使用 `summary`，避免把重 `detail_fields` 带入列表页。
- `GET /api/workbench/groups/detail?month=all&zone=open|paired&group_id=...` 返回单个 group 完整详情，用于详情抽屉、审计和需要重字段的交互。
- `GET /api/workbench/refresh-status` 返回 dirty scope、worker heartbeat/lag、failed backlog 和最近错误。
- 旧 `GET /api/workbench?month=all` 只作为兼容期接口，不再作为前端首屏依赖。

热路径基于结构化 SQL read model：

- `read_model.workbench_rows` 保存行级投影，用于详情定位、搜索和行级统计。
- `read_model.workbench_groups` 保存组级投影，用于首屏分页、区域分页、服务端筛选、搜索、排序和短 TTL page cache。
- `read_model.workbench_group_rows` 保存 group 内三栏行级筛选投影，用于列筛选和时间筛选；API 不得为了筛选读取 snapshot 大 JSON。
- `read_model.workbench_snapshots` 保留审计、导出、对账和兼容期用途，不作为首屏查询的数据源。

## 搜索、筛选和排序

- 三栏局部搜索按当前栏驱动，整组联动。
- 三栏局部搜索和时间排序触发 `/api/workbench/groups` 重新读取首屏页；前端只保留当前分页窗口和后续显式加载的页，不再为了筛选/排序预取全量快照。
- 列筛选和时间筛选也必须进入 `/api/workbench/groups`，未加载的 group 只要命中 SQL read model 就能进入筛选后的分页结果；前端不得用已裁剪的 summary preview 再次排除服务端返回的 group。
- 银行流水栏金额按不带千分位分隔符的固定小数文本展示，例如 `19370.00`，以便财务人员按连续数字直接搜索。
- 多选筛选按列生效，不破坏候选组上下文。
- 排序按组排序，不按单行排序。
- 全局搜索要能跳回对应月份、区域、行和详情。

## 选择和确认关联

- 未配对区和已配对区分别维护显式选中的行；三栏搜索、列筛选、时间筛选只改变可见投影，不清空选中态。
- 选择汇总必须基于未过滤的当前读模型上下文计算，并在 OA、银行流水、发票三栏同时显示已选数量和金额。
- 显式选中的行显示为选中；由同一关系上下文自动带入的行显示为关联项，并参与汇总、预览和提交。
- 确认关联必须把显式选中项及其已有关系上下文一起写入 pair relation。例如只显式选择 OA 和银行流水时，如果该 OA 有附件发票，预览和提交都必须连同附件发票一起配对。
- 前端可以为了预览体验提交上下文行，但最终完整性以后端 `confirm-link` 扩展逻辑为准；后端必须保证 preview 与 submit 使用同一套扩展规则。

## 折叠摘要

免 OA 批次等多流水组默认折叠时，必须由后端 group 契约输出：

- 摘要行。
- `display_mode=collapsed_summary`。
- `collapsed_rows` 保留原始行。
- 搜索、导出、撤回和审计仍能访问原始行。

禁止只靠前端隐藏行。

## 验收标准

- 确认和撤回不触发整页同步重建。
- 操作结果返回受影响行和局部更新数据。
- read model、搜索缓存、详情接口和导出保持一致。
- 只读导出用户不能看到或触发写操作。
