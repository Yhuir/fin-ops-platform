---
phase: 08-oa-pending-payments-improvements
status: implemented
created: 2026-06-17
---

# 08-PLAN：OA 待付款页「进行中 OA」视图实施计划

## 目标

在现有 `OA待付款` 页面内增加 `进行中 OA` view mode，展示进行中支付申请/日常报销与支出流水的匹配、付款判定、OA MySQL 写回状态，并支持候选流水人工确认后异步写回。

## 必须满足

- 不新增左侧菜单页。
- `已完成 OA` 现有行为不回归。
- `进行中 OA` 只显示 workflow status 为 `in_progress` 的支付申请和日常报销。
- 支付判定复用现有 OA 付款判定口径，不把候选直接当已支付。
- MySQL 写回使用 OA Mongo `form_data._id`，不能使用 Flowable 流程实例 ID、流程请求 ID 或 relation case id。
- 列表 GET 无写回副作用。
- 正常同步目标 1-2 秒。
- 覆盖后端、API、read model、UI 和回归测试。

## 任务分解

### 08-01 增加 OA workflow status 投影字段

修改范围：

- `backend/src/fin_ops_platform/adapters/oa_adapter.py`
- `backend/src/fin_ops_platform/adapters/repositories/postgres_oa_projection_repository.py`
- 新增 PostgreSQL migration
- 相关 adapter/repository tests

工作：

1. 在 `OAApplicationRecord` 增加 `workflow_status`。
2. 从 `MongoOAAdapter.canonical_process_status(...)` 写入 `in_progress` / `completed` 等标准值。
3. 在 `app.oa_applications` 新增 `workflow_status` column 和索引。
4. repository upsert/read/list 支持该字段。
5. 保持现有 `status` 语义不变。

验收：

- Mongo `processStatus=1` 的支付申请/日常报销 projection 为 `workflow_status=in_progress`。
- Mongo `processStatus=2` projection 为 `workflow_status=completed`。
- 现有已完成 OA 查询不因字段新增变空或变形。

### 08-02 拆分 OA 待付款查询 scope

修改范围：

- `backend/src/fin_ops_platform/services/oa_pending_payment_query_service.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
- `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`
- 前端 API/types

工作：

1. 为 rows/filter-options 增加 `view_mode=completed|in_progress`。
2. `completed` 保持现有默认行为。
3. `in_progress` 只读取 workflow status 为 `in_progress` 且类型为支付申请/日常报销的 OA。
4. `payment_status=all|pending|paid` 筛选只作用于付款状态。
5. 响应中返回 view mode、sync/read model status。

验收：

- 默认不带 `view_mode` 时行为兼容现有页面。
- `in_progress` 不返回 completed OA。
- 流程状态变更后 refresh 会让 row 离开 `in_progress` 视图。

### 08-03 复用付款匹配和候选确认语义

修改范围：

- `InvoiceLifecyclePolicy` 相关调用点
- Workbench relation 查询/候选读取服务
- OA pending payment row assembler

工作：

1. 复用现有候选和 confirmed relation 获取逻辑。
2. 复用 `InvoiceLifecyclePolicy.evaluate_oa_payment(...)` 判定 `pending/paid`。
3. 仅候选时返回可确认 action，不返回 paid。
4. confirmed 但金额/方向不满足现有规则时，不展示 paid，不写回。

验收：

- 无流水为 `待支付`。
- 候选为 `待支付` + `确认已支付`。
- confirmed 且通过付款判定为 `已支付`。
- confirmed 但不满足付款判定不写回。

### 08-04 增加 OA Mongo 文档 ID resolver 与 OA 支付状态 adapter

修改范围：

- 新增 backend adapter/repository
- runtime dependency/bootstrap
- runtime boundary guard tests
- 配置文档

工作：

1. 实现 platform OA row/detail -> OA Mongo 文档 ID resolver。
2. 实现 `t_payment_simple` read/write adapter。
3. 明确多记录读取策略：优先读取最新有效状态，记录重复风险。
4. 实现幂等 `mark_paid(flow_id)`，优先建议唯一约束；没有唯一约束时使用事务锁或规范化策略。
5. 使用环境变量配置 MySQL datasource，生产使用最小权限账号。

验收：

- 不把 Flowable 流程实例 ID、流程请求 ID 或 relation case id 写入 `flow_id`。
- route/service 不直接 import `pymysql`。
- 重复写回同一 OA 不产生不可控重复记录。
- MySQL 不可用时任务失败可重试，页面不显示 `写回失败`。

### 08-05 增加「确认已支付」复合 API

修改范围：

- `routes_oa_pending_payments.py`
- 新增/扩展 service
- API contract tests
- 前端 API client

工作：

1. 新增 `confirm-paid` API，输入 OA row id、候选流水 id 或 candidate id、idempotency key/version。
2. 内部调用 `WorkbenchWriteFacade.confirm_link` 或现有等价入口确认 relation。
3. 确认后重新评估付款判定。
4. 判定 paid 后 enqueue OA MySQL writeback。
5. 返回更新后的 row 或 job/status。

验收：

- 重复提交幂等。
- 候选不存在、候选不属于该 OA、金额不满足、权限不足等返回明确错误。
- API 不在未确认关系时写回 OA。

### 08-06 增加异步写回和补偿刷新

修改范围：

- writeback outbox/job table 或现有 job 边界
- worker/service
- read model refresh trigger
- docs/operations

工作：

1. 持久化 writeback 状态：pending/running/succeeded/failed/retryable。
2. 行内映射为 `未写回` / `已写回`。
3. Worker 从 outbox 读取任务并写 MySQL。
4. read model refresh 发现 confirmed paid relation 且未写回时 enqueue 补偿任务。
5. 失败只记录后台状态和重试，不在行内展示失败文案。

验收：

- 写回成功后行内 `已写回`。
- 失败后仍 `未写回`，后台可审计和重试。
- read model 补偿能覆盖从其他入口确认的 relation。

### 08-07 实现 1-2 秒同步路径

修改范围：

- OA sync polling/webhook 接入
- read model scope registry/queue
- SSE 或现有刷新状态
- tests

工作：

1. 优先接入 OA event/webhook，如不可用则配置 1 秒 fingerprint polling fallback。
2. 只刷新 affected OA/month/scope，避免全量扫描。
3. Workbench relation confirm 后触发 affected row refresh。
4. 前端收到 SSE 或状态变化后刷新当前 view mode。
5. 保留 freshness/status，不能将 stale 数据标成 fresh。

验收：

- OA 从 `in_progress` 变 `completed` 后，正常 1-2 秒从视图移除。
- 关系确认后，正常 1-2 秒内支付状态变化。
- polling 不因页面打开触发全量扫描。

### 08-08 实现前端 UI

修改范围：

- `web/src/pages/OaPendingPaymentsPage.tsx`
- `web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx`
- `web/src/features/oaPendingPayments/api.ts`
- `web/src/features/oaPendingPayments/types.ts`
- frontend tests

工作：

1. 增加 `已完成 OA / 进行中 OA` segmented control。
2. 增加 `进行中 OA` 表格布局：OA / 支付状态 / 流水。
3. 增加支付状态筛选。
4. 增加 `确认已支付` action 和提交中状态。
5. 显示 `未写回/已写回`。
6. 处理 loading/empty/error/sync 状态。
7. 保持现有已完成 OA UI 不回归。

验收：

- UI 与用户确认的表格结构一致。
- 无流水显示 `-`。
- 行内不出现 `写回失败`。
- 小屏不重叠，文本不溢出。

### 08-09 更新文档和部署说明

修改范围：

- `docs/modules/oa-pending-payments/README.md`
- `docs/modules/oa-pending-payments/state-machine.md`
- `docs/modules/oa-pending-payments/tests.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`
- `deploy/oa/README.md`

工作：

1. 更新页面 view mode、状态机、API、read model、worker 和测试矩阵。
2. 记录外部 MySQL env 和最小权限要求，不记录真实凭据。
3. 记录 1-2 秒同步策略和 fallback polling 开关。

验收：

- 长期文档可独立解释该功能。
- 运维文档包含新增 worker/env。
- 不泄露生产账号密码。

### 08-10 验证和风险关闭

至少运行：

```bash
pytest tests/test_platform_runtime_boundary_guards.py
pytest tests/test_oa_pending_payments*.py
pytest tests/test_oa_projection*.py
pytest tests/test_workbench*.py
npm --prefix web test -- --run
npm --prefix web run build
```

按仓库实际测试命名调整命令。实现完成后还需要跑最小 smoke：

1. 导入/同步 OA。
2. 打开 `OA待付款`。
3. 切换 `进行中 OA`。
4. 确认候选流水。
5. 等待写回。
6. 核验 MySQL `t_payment_simple` 与页面状态。

## 测试矩阵

必须覆盖七类测试中适用项：

- Business core：付款判定、候选不自动 paid、金额/方向不满足不写回。
- Service layer：resolver、MySQL 幂等写回、outbox/retry、read model refresh。
- API contract：列表 view mode、筛选、confirm-paid、错误和幂等。
- Read model/background job：in_progress scope、OA 完成后移除、补偿写回、freshness。
- Frontend interaction：切换、筛选、确认按钮、loading/empty/error/sync、已完成视图回归。
- E2E integration：候选确认 -> relation confirmed -> writeback -> read model refresh -> UI 更新。
- Existing regression：已完成 OA 页面、Workbench relation confirm、OA projection、权限和 API shape。

## 完成标准

- 所有 must-have 验收通过。
- 文档和测试同步更新。
- 生产配置不包含明文凭据。
- `已完成 OA` 行为没有回归。
- `进行中 OA` 正常 1-2 秒反映 OA 和 relation 变化。
