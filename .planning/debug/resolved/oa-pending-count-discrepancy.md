---
status: resolved
trigger: "t payment simple这个表有315条数据 是不是意味着有315个进行中的oa， 为什么我的OA 待付款核对的进行中只有81条；使用grill me全量分析，不实现"
created: 2026-07-15
updated: 2026-07-15
---

# Debug Session: oa-pending-count-discrepancy

## Symptoms

- Expected behavior: 明确 `t_payment_simple` 的 315 行与 OA 待付款核对“进行中 OA 81 条”之间是否应当相等。
- Actual behavior: OA 源表观察到 315 行；页面显示已完成 253 条、进行中 81 条。
- Error messages: 页面截图未显示错误。
- Timeline: 用户于 2026-07-15 观察到；是否曾经相等未知。
- Reproduction: 查看 `t_payment_simple` 行数，再打开 `/oa-pending-payments` 并观察状态分段计数。

## Current Focus

- hypothesis: confirmed — `t_payment_simple` 是付款状态/准入表，不是“当前进行中 OA”集合；页面按当前 OA workflow status 从准入记录中取 in-progress 子集，并与 completed 统一投影分开计数。
- test: 已追踪 Mongo OA adapter、MySQL payment-status repository、PostgreSQL OA projection/read model、API 与前端计数，并核对生产 API/Audit 汇总。
- expecting: confirmed — 315 与 81 的计数对象和筛选谓词不同；315 的精确去重/状态分布仍需外部 MySQL 只读 SQL 才能拆分。
- next_action: resolved；如需把 315 精确分桶，执行 DBA 只读 `COUNT(*) / COUNT(DISTINCT flow_id)` 并按 OA Mongo 当前流程状态 join 对账。

## Evidence

- timestamp: 2026-07-15
  observation: `MySQLOAPaymentStatusRepository.list_payment_statuses()` 读取 `t_payment_simple` 的全部非空 `flow_id`，没有“进行中”条件，并按 `create_time desc, id desc` 后以 `flow_id` 去重保留最新记录。
- timestamp: 2026-07-15
  observation: `PaymentAdmittedOAProjectionAdapter` 只把 `t_payment_simple.flow_id` 当准入集合，再按 flow id 精确读取 OA Mongo；缺失/重复/无法解析的记录不会直接成为页面 OA。
- timestamp: 2026-07-15
  observation: `OaPendingPaymentQueryService._record_matches_view_mode()` 只有在 Mongo OA 当前 `workflow_status == in_progress` 时才进入进行中视图；completed/legacy 进入已完成视图。
- timestamp: 2026-07-15
  observation: 生产 rows GET（无筛选、all 月份）返回 read model fresh；completed 唯一 OA 253、表格行 224，in-progress 唯一 OA 81、表格行 81。生产类型分布为 completed=支付申请198+日常报销55，in-progress=支付申请69+日常报销12。
- timestamp: 2026-07-15
  observation: 生产 page Audit 的 App 内 canonical source fact count 为 334，read model row count 为 305；334=253+81，305=224+81，integrity=pass，证明计数与 relation 折叠一致。
- timestamp: 2026-07-15
  observation: page Audit 另有 `invoice_lifecycle.read_model.refresh` 2026-04 dead-letter，导致 overall issues_found/freshness not_fresh；OA pending rows 自身仍返回 fresh，且该事件不改变 workflow viewCounts 的 OA ID/status 归类，因此不是本差额原因。
- timestamp: 2026-07-15
  observation: 5 个针对性回归测试通过，覆盖 flow_id 最新记录去重、completed/in-progress 过滤、只有 in-progress 使用 payment admission、复用 payment status admission，以及 SQL projection 分源构建。

## Eliminated

- hypothesis: 页面把 `t_payment_simple` 315 行全部当作进行中，但前端分页只显示 81。
  reason: 前端直接展示后端 `summary.viewCounts`；生产 API 的 in-progress `pagination.total` 与唯一 OA 计数都为 81。
- hypothesis: 253+81 的差额来自单纯把支付申请和日常报销分开。
  reason: 两个视图都同时包含支付申请与日常报销；类型合计分别为 completed 253、in-progress 81。
- hypothesis: relation 折叠导致 315 变成 81。
  reason: 折叠只解释 completed 253 个 OA 渲染为 224 行；in-progress 81 个 OA就是 81 行，viewCounts 按唯一 OA ID 统计。
- hypothesis: 当前 page Audit dead-letter 导致进行中数量从 315 降为 81。
  reason: OA pending rows read model 自身 fresh，App 内 canonical/read-model integrity pass；死信属于 invoice lifecycle 依赖的独立完整性风险。

## Resolution

- root_cause: 将 MySQL 付款状态/准入表的物理行数误当成当前进行中 OA 数。真实进行中口径是“非空 flow_id 最新记录去重后，能匹配 OA Mongo 文档，且 Mongo 当前 workflow status 为 in_progress，并通过当前搜索/月/筛选条件”的唯一 OA ID 数。
- fix: 不实现。
- verification: 生产 rows GET、生产 page Audit、5 个针对性 unittest。
- files_changed: 仅本诊断记录。
