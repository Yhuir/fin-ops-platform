# 08-SPEC：OA 待付款页增加「进行中 OA」视图

日期：2026-06-17
阶段：08-oa-pending-payments-improvements
状态：Spec 待核验

## 目标

在现有 `OA待付款` 页面上方增加 `已完成 OA / 进行中 OA` 切换。`进行中 OA` 视图用于查看 OA 系统内「支付申请」和「日常报销」中流程状态为「进行中」的 OA，与支出流水之间的配对和支付状态写回情况。

该视图回答一个明确问题：哪些进行中 OA 已经能和支出流水关联，哪些还未支付。

## 背景事实

- 现有 `OA待付款` 页面主要面向「已完成 OA」，用于找待支付或已支付情况。
- 新视图面向「进行中 OA」，业务对象相同但流程状态不同。
- OA 主数据在 MongoDB。
- OA 支付状态写回表在 MySQL：`smart_oa.t_payment_simple`。
- 2026-06-17 远端脱敏核验显示 `t_payment_simple.flow_id` 对应 OA Mongo `form_data._id`，不是 Flowable `PROC_INST_ID_`。
- 进行中 OA 的支付状态 lookup/writeback 必须使用投影中的 `Mongo文档ID`，或 `oa-pay-/oa-exp-` 行 ID 后缀解析出的 Mongo 文档 ID。
- 平台内部展示和关联仍应使用现有 OA projection/read model 的 OA id，例如 `oa-pay-{mongo_id}`、`oa-exp-{mongo_id}`。

## 范围内

1. 在现有 `OA待付款` 页面增加 `已完成 OA / 进行中 OA` 切换。
2. `进行中 OA` 视图只展示 OA 系统当前流程状态为「进行中」的支付申请和日常报销。
3. 表格主体为三栏：左侧 OA，中间支付状态，右侧流水。
4. 复用现有关联台对 OA 与支出流水的匹配/候选判断逻辑，但数据集从「已完成 OA」切换为「进行中 OA」。
5. 有已确认关联支出流水，且通过现有 OA 付款判定口径时，判定为「已支付」。
6. 只有候选流水时不自动写回，需要用户点击「确认已支付」。
7. 用户确认后，或 read model refresh 发现已存在 confirmed active relation 后，异步写回 OA MySQL `t_payment_simple`。
8. 页面展示 OA 写回状态：`未写回` / `已写回`。
9. 支付状态支持筛选：`全部`、`待支付`、`已支付`。
10. OA 系统流程状态变化后，正常 1-2 秒内反馈到页面；进行中 OA 后续变成已完成时，必须从 `进行中 OA` 视图移除。

## 范围外

- 不在本阶段重做 OA 待付款页面整体信息架构。
- 不改变已完成 OA 的既有支付判定口径，除非为复用公共服务做最小必要适配。
- 不把候选流水自动当成已支付。
- 不在页面打开时触发写回。
- 不通过 SSH 作为应用运行时写回路径。
- 不在表格行内展示「写回失败」文案；失败应由后台记录、重试，页面保持 `未写回`，必要时用非侵入式同步状态提示。

## 用户故事与验收

### US1：切换到进行中 OA

作为财务人员，我可以在 `OA待付款` 页面切换到 `进行中 OA`，看到当前 OA 系统内所有进行中的支付申请和日常报销。

验收：

- 页面上方存在 `已完成 OA / 进行中 OA` 切换控件。
- 选择 `进行中 OA` 后，列表只包含流程状态为「进行中」的 OA。
- OA 类型只包含「支付申请」和「日常报销」。
- OA 后续在 OA 系统变成「已完成」后，下一次实时同步/refresh 后从该视图移除。

### US2：表格三栏展示

作为财务人员，我可以在一行里同时看到 OA、支付状态、流水。

验收：

- 左侧 OA 区域显示：
  - 申请人
  - `支付申请` 或 `日常报销` chip
  - 流程状态 chip：`进行中`
  - 项目
  - 申请日期 chip
  - 金额
- 中间支付状态区域显示：
  - `待支付` 或 `已支付`
  - 候选流水且未确认时显示 `确认已支付` 按钮
  - OA 写回状态：`未写回` 或 `已写回`
- 右侧流水区域显示：
  - 有流水时：对方户名、交易时间 chip、金额、银行/银行后四位 chip、收支 chip、流水摘要
  - 无流水时：显示 `-`

### US3：支付状态判定

作为财务人员，我需要用统一口径判断进行中 OA 是否已支付。

验收：

- 没有匹配到支出流水时，支付状态为 `待支付`。
- 有已确认关联支出流水，且通过现有 OA 付款判定口径时，支付状态为 `已支付`。
- 只有候选流水时，仍不自动写成已支付；需要用户点击 `确认已支付`。
- 候选和确认逻辑复用现有关联台逻辑，区别仅在 OA 数据集为「进行中 OA」。
- 已确认关系如不满足支出方向、金额等现有付款判定条件，不得展示为 `已支付`，也不得写回 `pay_status=1`。

### US4：筛选支付状态

作为财务人员，我可以筛选 `全部`、`待支付`、`已支付`。

验收：

- `全部` 展示当前进行中 OA 全量。
- `待支付` 展示无 confirmed 支出流水关联，或虽有 confirmed 但未通过现有付款判定口径的进行中 OA。
- `已支付` 展示已有 confirmed 支出流水关联且通过现有付款判定口径的进行中 OA。
- 筛选不改变 OA 流程状态范围，仍只看「进行中」。

### US5：确认已支付并写回 OA

作为财务人员，我可以对候选流水点击 `确认已支付`，让系统确认关联并写回 OA 支付状态。

验收：

- 只有存在候选支出流水且当前未确认时，显示 `确认已支付` 按钮。
- 点击后先按现有 workbench relation 规则确认 OA 与流水关系，并通过现有付款判定口径校验支出方向和金额。
- 确认成功且付款判定为已支付后，异步写回 MySQL `t_payment_simple`，将该 OA 对应 `flow_id` 的 `pay_status` 写为已支付。
- 写回成功后，页面显示 `已写回`。
- 写回未完成或失败待重试时，页面显示 `未写回`，不在表格行内显示 `写回失败`。
- 接口重复提交必须幂等，不能重复创建冲突关系或重复插入不可控的支付状态记录。

### US6：实时同步

作为财务人员，我希望 OA 系统状态变化能快速反映到平台页面。

验收：

- 正常情况下，OA 流程状态、支付状态、关系确认变化在 1-2 秒内反映到页面。
- 首选路径为事件驱动：OA 流程/表单变更通知平台，平台做小范围 projection/read model refresh，并通过 SSE 或等价机制通知页面刷新。
- 如 OA 侧暂不能提供 webhook，则使用 1 秒级轻量增量 polling worker 作为 fallback，不做页面打开时全量扫描。
- 页面可以展示同步中/最近同步时间等状态，但表格行内只显示 `未写回` / `已写回`。

## 架构约束

### ID 口径

- 页面行 identity：使用平台内部 OA id，例如 `oa-pay-{mongo_id}`、`oa-exp-{mongo_id}`。
- OA 主数据 lookup：使用 Mongo `_id` 和现有 OA projection。
- MySQL 支付状态 lookup/writeback：使用 OA Mongo `form_data._id`，即 `t_payment_simple.flow_id`。
- 必须维护平台 OA row id / detail fields -> Mongo 文档 ID 的解析路径，不能把 Flowable 流程实例 ID、流程请求 ID 或 relation case id 写入 `t_payment_simple.flow_id`。

### 写回路径

- 应用正常运行时必须直接通过服务端 MySQL datasource 写回，不依赖 SSH 登录服务器。
- 生产应使用最小权限 MySQL 账号，只允许必要的 select/insert/update。
- 不在 frontend 直接连接 MySQL。
- 不在 GET/list 页面请求中做写回副作用。

### MySQL 表风险

- 当前 `t_payment_simple.flow_id` 只有普通索引，不是唯一索引。
- 如果业务要求每个流程只有一条支付状态记录，建议增加唯一约束或在 repository/service 层实现并发安全的幂等 upsert。
- 实现前必须明确冲突处理：同一 `flow_id` 多条记录时应如何读取和修正。

### Read Model 与事实源

- 进行中 OA 不应直接塞入现有「已完成 OA」统一事实源。
- 推荐拆成同一 payment matching domain 下的两个 scope/view：
  - `completed_oa`
  - `in_progress_oa`
- 共享匹配规则、流水读取、写回状态服务；分离 OA 流程状态过滤和 read model scope。
- Read model refresh 必须走现有 freshness/status/enqueue 边界，不能让页面读旧数据却标记 fresh。

## UI 规格

顶部：

- 在现有 `OA待付款` 页面顶部增加 segmented control：
  - `已完成 OA`
  - `进行中 OA`
- 保留现有刷新、状态提示、筛选区的整体风格。

进行中 OA 表格：

- 表格列：
  - `OA`
  - `支付状态`
  - `流水`
- OA 列：
  - 第一行：申请人 + 类型 chip + `进行中` chip
  - 第二行：项目 + 申请日期 chip
  - 第三行：金额
- 支付状态列：
  - 主状态：`待支付` / `已支付`
  - 操作：`确认已支付` 按钮，仅候选可确认场景展示
  - 写回：`OA 写回状态：未写回/已写回`
- 流水列：
  - 有流水：对方户名 + 交易时间 chip；金额 + 银行/后四位 chip + 收支 chip；流水摘要
  - 无流水：`-`

## 后端接口草案

最终接口命名可以在 discuss/plan 阶段按现有代码风格调整，但必须满足以下能力：

- 查询进行中 OA 支付匹配列表：
  - 输入：支付状态筛选、分页/排序、刷新策略
  - 输出：rows、summary、read_model_status/sync_status
- 确认候选流水并标记已支付：
  - 输入：平台 OA id、候选流水 id 或 relation candidate id、expected version/idempotency key
  - 行为：确认关系 -> enqueue 写回 -> enqueue/read model refresh
  - 输出：更新后的 row 或 job/status
- 查询/刷新同步状态：
  - 输出：最近 OA sync 时间、read model freshness、writeback backlog/last error summary（不直接显示表格失败文案）

## 需要实现前再确认的技术决策

1. MySQL `t_payment_simple.flow_id` 是否可以增加唯一约束。
2. 进行中 OA 的 event webhook 是否能从 OA 系统接入；若不能，先落地 1 秒级增量 polling。
3. `确认已支付` 是否直接复用现有 relation confirm API，还是新建一个复合 API 封装 confirm + writeback enqueue。
4. 写回状态是新增平台本地 outbox/writeback table，还是复用现有 job/read model 状态表。

## Docs Impact Assessment

- 需要更新 `docs/modules/oa-pending-payments/README.md`：增加 `进行中 OA` 子视图、状态与接口入口。
- 需要更新 `docs/modules/oa-pending-payments/state-machine.md`：增加进行中 OA 支付状态、候选确认、写回状态转换。
- 需要更新 `docs/modules/oa-pending-payments/tests.md`：增加 UI、API、service、read model、writeback、实时同步测试矩阵。
- 可能需要更新 `docs/app-architecture/pages.md`：页面切换和数据流变化。
- 可能需要更新 `docs/dev/api-contracts.md`：新增/变更 API 合约。
- 如新增 worker/env/部署项，需要更新 `docs/operations/runtime-worker-governance.md` 和 `deploy/oa/README.md`。

## 测试验收范围

本阶段后续实现至少覆盖：

- Business core：支付状态判定、候选不自动写回、confirmed relation 判定已支付。
- Service layer：OA row/detail 到 Mongo 文档 ID 映射、MySQL 幂等写回、失败重试。
- API contract：列表筛选、确认已支付、同步状态。
- Read model/background job：进行中 OA scope refresh、流程状态变更移除、1-2 秒更新路径或 fallback polling。
- Frontend interaction：切换视图、筛选、无流水 `-`、确认按钮、写回状态展示。
- End-to-end：候选确认 -> relation confirmed -> MySQL 写回 -> read model refresh -> 页面变为已支付/已写回。
- Regression：已完成 OA 现有页面、筛选、支付状态、relation 行为不回退。

## 需求明确度评分

- Goal Clarity：0.94
- Boundary Clarity：0.90
- Constraint Clarity：0.82
- Acceptance Clarity：0.88
- Ambiguity Score：0.11

结论：需求核验已达到进入 discuss/plan 的门槛。剩余不确定性主要是实现层技术决策，不阻塞下一步架构方案设计。

## 决策记录

- 不新增独立左侧菜单页面，改为在现有 `OA待付款` 页面增加 `已完成 OA / 进行中 OA` 切换。
- 进行中 OA 视图只展示流程状态为「进行中」的支付申请和日常报销。
- 支付状态使用统一关联逻辑判断：confirmed 支出流水且通过现有付款判定口径为已支付；无流水为待支付；候选流水需人工确认。
- 候选流水不自动写回，必须点击 `确认已支付`。
- 写回不在页面打开时触发，应在 relation 确认或 read model refresh 发现 confirmed relation 后异步写回。
- 页面表格行不展示 `写回失败`，只展示 `未写回` / `已写回`。
- 实时目标采用更优版 1-2 秒。
- 应用运行时写回 MySQL 不需要 SSH；SSH 只用于运维排查。
