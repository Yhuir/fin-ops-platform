# 08-CONTEXT：进行中 OA 支付匹配视图

日期：2026-06-17
阶段：08-oa-pending-payments-improvements
来源：用户讨论、仓库文档、现有代码、远端 OA MySQL/Mongo/Flowable 路径核验

## 业务目标

在现有 `OA待付款` 页面增加 `进行中 OA` 视图，让财务能看到 OA 系统内仍处于「进行中」的支付申请和日常报销，与支出流水的匹配、支付状态、OA 支付状态写回情况。

这个视图不是一个独立左侧菜单页面。它是现有 `OA待付款` 页的第二个 view mode，和原有 `已完成 OA` 视图共享支付匹配能力，但 OA 数据集不同。

## 已锁定需求

1. 页面入口：`/oa-pending-payments` 顶部增加 `已完成 OA / 进行中 OA` 切换。
2. `进行中 OA` 只包含 OA 系统当前流程状态为「进行中」的 `支付申请` 和 `日常报销`。
3. 如果 OA 后续在 OA 系统变成「已完成」，1-2 秒同步/refresh 后必须从 `进行中 OA` 视图移除。
4. 表格三栏：左侧 OA，中间支付状态，右侧流水。
5. 没有流水或只有未确认候选时，支付状态为 `待支付`。
6. 只有 confirmed relation 且满足现有 OA 付款判定口径时，支付状态为 `已支付`。
7. 单纯候选不自动写回。候选行显示 `确认已支付` 按钮，点击后先确认关系，再异步写回 OA MySQL。
8. 行内只显示 OA 写回状态 `未写回` / `已写回`，不显示 `写回失败`。
9. 正常同步目标是 1-2 秒。优先事件驱动，小范围 refresh；OA 侧没有 webhook 时使用 1 秒级轻量增量 polling fallback。
10. 应用运行时直接通过后端 MySQL datasource 写回，不依赖 SSH。SSH 只用于运维/排障。

## 关键事实

### ID 口径

- 平台 OA 行 identity 继续使用现有 projection id，例如 `oa-pay-{mongo_id}`、`oa-exp-{mongo_id}`。
- OA 主数据事实源是 Mongo。
- OA 支付状态事实源是 MySQL `smart_oa.t_payment_simple`。
- 2026-06-17 远端脱敏核验显示 `t_payment_simple.flow_id` 是 OA Mongo `form_data._id`，不是 Flowable `PROC_INST_ID_`，也不是流程请求 ID。
- 同一核验中，现有 `t_payment_simple.flow_id` 样例为 24 位 ObjectId 形态，能匹配 Mongo `_id`，未匹配 `act_hi_procinst.PROC_INST_ID_`、`act_ru_execution.PROC_INST_ID_` 或 `act_hi_varinst.PROC_INST_ID_`。
- 平台必须有 OA row/detail -> Mongo 文档 ID resolver；Flowable 流程实例 ID 和流程请求 ID 只作为详情/诊断字段。

### 支付判定

现有 `InvoiceLifecyclePolicy.evaluate_oa_payment(...)` 已按 OA 金额、支出流水、金额差额一分钱内等规则判定付款状态。`进行中 OA` 视图应复用该口径，区别只是输入 OA 集合为流程状态 `in_progress`。

不能把「有关联候选」直接等同于「已支付」。候选需要人工确认；确认后仍要通过既有付款判定口径，才能写回 `pay_status=1`。

### 写回事实源

`t_payment_simple` 当前结构：

```sql
CREATE TABLE `t_payment_simple` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    `flow_id` VARCHAR(64) NOT NULL COMMENT '流程ID',
    `pay_status` TINYINT NOT NULL DEFAULT 0 COMMENT '支付状态：0-待支付，1-成功，2-失败',
    `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_flow_id` (`flow_id`),
    KEY `idx_pay_status` (`pay_status`),
    KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='支付记录表';
```

`idx_flow_id` 不是唯一索引。实现必须处理同一 `flow_id` 多条记录的读取和幂等写回策略。推荐后续增加唯一约束；如果暂不能改表结构，repository 层必须在事务和锁内明确选择最新记录或规范化记录。

## 现有仓库上下文

- 页面：`web/src/pages/OaPendingPaymentsPage.tsx`
- 表格：`web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx`
- 前端 API：`web/src/features/oaPendingPayments/api.ts`
- 前端类型：`web/src/features/oaPendingPayments/types.ts`
- 后端 route：`backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`
- 后端查询 service：`backend/src/fin_ops_platform/services/oa_pending_payment_query_service.py`
- 后端 read model service：`backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
- OA adapter：`backend/src/fin_ops_platform/adapters/oa_adapter.py`
- PostgreSQL OA projection：`backend/src/fin_ops_platform/adapters/repositories/postgres_oa_projection_repository.py`
- 付款判定策略：`backend/src/fin_ops_platform/services/invoice_lifecycle_policy.py`
- Workbench 确认入口：`WorkbenchWriteFacade.confirm_link`
- 外部 OA MySQL 连接现有模式：`backend/src/fin_ops_platform/services/oa_role_sync_service.py`

## 架构约束

- `server.py` 只做路由、依赖组装和 HTTP 映射；业务逻辑放 `services/`。
- SQL 和外部 MySQL 细节放 repository/adapter，不散落在 service 或 route。
- Worker 不依赖 `Application`、HTTP response、cookie/header。
- Read model refresh 走现有 freshness/status/enqueue 边界，不绕过 registry/queue。
- 新增外部 MySQL adapter 时，需要更新运行时边界测试 allowlist，避免 route/service 直接 import `pymysql`。
- 生产环境必须使用最小权限账号和环境变量配置，不把远端连接信息写进仓库文档或代码。

## 待实现时落地的设计点

1. 在 OA projection 增加一等字段 `workflow_status`，不要复用 `app.oa_applications.status`。现有 `status` 存的是 section/source scope。
2. Query service 支持 `view_mode=completed|in_progress`，在 OA projection/read model 层按 workflow status 过滤。
3. 新增 OA payment status read/write adapter：用 OA Mongo 文档 ID 读写 MySQL `t_payment_simple.flow_id`。
4. 新增 resolver：平台 OA row/detail -> OA Mongo 文档 ID。
5. 新增复合 API：确认候选并标记已支付。API 内部复用 Workbench confirm 规则，然后 enqueue 写回。
6. 写回状态建议平台本地持久化，支持幂等、重试、行内 `未写回/已写回` 展示和后台失败审计。
7. 实时路径优先 event/webhook；fallback 为 1 秒级 OA fingerprint polling + 小范围 refresh + SSE/轮询刷新前端。

## 非目标

- 不重做关联台。
- 不改变 `已完成 OA` 的既有 UI 和行为，除非公共类型/API 做兼容扩展。
- 不在列表 GET 请求中写回 OA。
- 不把候选流水自动写成已支付。
- 不在行内展示失败文案。
