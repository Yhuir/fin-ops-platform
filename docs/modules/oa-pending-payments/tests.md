# OA待付款核对测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

OA 待付款核对是 OA 申请、支出流水、进项发票、Workbench relation、invoice lifecycle 和 invoice usage collection read model 的交汇页。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 主行身份 | completed: 普通 `app.oa_applications` / OA completed projection；in_progress: OA MySQL `t_payment_simple.flow_id` + payment-admitted OA projection / OA Mongo | completed 列表以统一 OA projection 中已完成/历史未知 OA 为主行；in_progress 列表以已进入支付状态管理准入表且能匹配 OA Mongo `_id` 的进行中 OA 为主行；缺少银行或发票时不能丢掉主行，未入表的重复/异常进行中 OA 不能进入页面。 |
| 流程视图 | OA projection `workflow_status` + rows `summary.viewCounts` | `completed` 只含统一 completed projection 中已完成/历史未知 OA，`in_progress` 只含已准入且进行中 OA；OA sync/read model refresh 后已完成 OA 必须从进行中视图移除并进入 completed 统一 projection；切换按钮数量必须按同一筛选口径统计。 |
| 付款状态 | `InvoiceLifecyclePolicy`、`OaPendingPaymentQueryService` | `unpaid`、`paid`、`partially_paid`、`pending_review` 必须以 OA 金额、支出流水和 Workbench relation 事实判定；不得输出 `overpaid` 或 `merged_paid`。 |
| OA 支付状态写回 | OA MySQL `t_payment_simple`、`OAPaymentStatusRepository` | `flow_id` 必须解析到 OA Mongo 文档 ID；`t_payment_simple.id` 不能当 OA ID；候选流水或未确认 relation 不能写回；completed/in-progress 只要有有效支出流水 active relation 且支出合计等于 OA 金额，就由自动匹配/写回命令写回同一 `flow_id` 的 `pay_status=1`；前端不再提供人工 confirm-paid。 |
| 支出流水证据 | `ImportNormalizationService`、completed Workbench relation read facade、in-progress OA pending payment relation、bank transaction relation claims | 只允许支出流水作为付款证据；收入流水或缺失流水事实必须进入异常/待复核，不得算已付。进行中 OA 抽屉关联创建 OA 待付款独立 pending relation 和 bank claim 后，若 outflow、金额和 `flow_id` 校验通过，必须自动写回 OA MySQL；该关系不能进入关联台，只有 OA completed 后通过 promotion 进入 Workbench active relation。 |
| 发票证据 | 进项发票事实、Workbench relation read facade | 发票详情使用进项发票字段；不得显示销项发票字段或把 relation case id 当发票 id。 |
| API/read model | `OaPendingPaymentReadModelService`、`PostgresReadModelRepository` | rows、filter-options、detail 都必须经过 fresh/source-version gate；非 fresh 只能 refreshing，不 live scan。 |
| SQL projection | `InvoiceUsageCollectionSqlProjectionBuilder` | 月份 scope 重建 rows 和 native filter/sort columns；all scope 聚合月份 source versions。 |
| worker | `invoice-usage-collection` worker | `oa_pending_payment.read_model.refresh` 支持 all -> month shard fan-out，month shard 才 rebuild。 |
| App Status | domain/read model/job/worker registry | `oa_pending_payments` domain 必须暴露 `oa_pending_payment` read model、`invoice-usage-collection` worker、`oa.sync` 和 `invoice_lifecycle`。 |
| 前端页面 | `OaPendingPaymentsPage`、`OaPendingPaymentsTable`、API client | 页面展示 compact grouped table、筛选/排序、empty/error/loading、详情 drawer、规则 drawer 和 refreshing detail。 |
| 跨模块 fan-out | OA rebuild、发票导入、银行导入、关系确认/撤回、待找发票规则、invoice lifecycle | 必须最终刷新 `oa_pending_payment` read model；当前 pending rules 的执行层通过 workbench invalidation 间接入队 invoice usage collection，已有 API 回归保护。 |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| completed 统一 OA projection 与 in-progress `t_payment_simple.flow_id` 准入源 | P0 | `tests/test_oa_payment_status_service.py`、`tests/test_oa_pending_payment_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | covered | completed 读取普通 completed projection，不受 `t_payment_simple` 准入限制；in-progress 由 MySQL repository 返回最新 flow_id 支付状态，`PaymentAdmittedOAProjectionAdapter` 根据 flow_id 精确读取 OA Mongo row_id 候选；SQL read model scope 枚举使用 completed projection 与 in-progress 准入 projection 月份并集；前端切换按钮展示 `已完成 OA N条 / 进行中 OA N条`。 |
| 相同业务字段的不同进行中 OA 保留 | P0 | `tests/test_oa_pending_payment_service.py` | covered | `in_progress` 只按 `t_payment_simple.flow_id` 准入和当前 workflow status 过滤，不用 completed projection 的业务指纹排除；同项目、同供应商、同金额、同事由的不同 flow id 必须作为独立 OA 展示。 |
| OA workflow status 投影和视图过滤 | P0 | `tests/test_mongo_oa_adapter.py`、`tests/test_oa_projection_sql_runtime.py`、`tests/test_oa_projection_sync_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_oa_pending_payment_service.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | covered | Mongo OA detail fields 保留流程实例/请求/Mongo id；普通 Postgres OA projection 只读取/写入 completed/legacy 并清理旧 in-progress 投影残留；OA 待付款专用 projection 保留准入 OA 的当前 workflow status；rows/filter-options 支持 `view_mode=completed|in_progress`。 |
| OA 自动匹配和自动写回 | P0 | `tests/test_oa_payment_status_service.py`、`tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_oa_pending_payment_service.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts` | covered | 页面进入后调用 `auto-reconcile-bank-transactions`；后端复用关联台 OA-bank 精确金额/精确合计规则，只自动确认无冲突的 in-progress OA 与未配对支出流水；in-progress 自动确认写入 OA 待付款独立 pending relation 和 bank claim，不写 Workbench active relation；completed 已有 Workbench active 支出流水 relation、in-progress 已有 active pending relation 且金额相等时自动写回 `t_payment_simple.pay_status=1`；应用组装层锁定显式 completed/Postgres 投影不能污染 auto-reconcile 的 payment-admitted in-progress OA source；自动确认的 OA-bank relation 必须持久化到 state store，应用重建后再次 auto-reconcile 为 no-op；精确候选在 relation confirm、`flow_id` 解析或 OA MySQL 写回阶段失败时，响应返回 `skippedAutoMatches` 诊断；前端写成功后等待 `oa_pending_payment` operation barrier fresh 再重新请求 rows；Browser 覆盖单次自动请求、成功提示、rows/read model 重新请求后 `已写回`、无人工写回按钮、409 失败可见且不半写。 |
| 进行中 OA 右侧抽屉关联支出流水 | P0 | `tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_oa_pending_payment_service.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_relation_sql_projection.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-bank-link-flow.spec.ts` | covered | 抽屉默认请求全部支出流水，可筛选已配对/未配对/已关联进行中 OA；前端只允许勾选未配对流水；后端拒绝收入流水；提交创建 OA 待付款独立 pending relation 和 bank claim，不写 `app.workbench_pair_relations`；Workbench active generation 和 Workbench relation SQL projection 都会排除 active pending bank claim，避免进行中 OA 流水进入关联台未配对/候选；outflow、金额和 `flow_id` 校验通过时自动写回 `t_payment_simple.pay_status=1`；前端写成功后必须先等待 `oa_pending_payment` operation barrier fresh，再重新请求 rows；Browser 覆盖 disabled candidate、relation_status 筛选、提交 body、rows/read model 重新请求后 `已写回`、无人工写回按钮、成功后无操作失败/同步失败/read model 失败残留、409 失败可见且不半写。 |
| 进行中 OA relation promotion | P0 | `tests/test_oa_pending_payment_relation_promotion_service.py`、`tests/test_oa_projection_sync_service.py`、`tests/test_postgres_migrations.py` | covered | OA sync 发现 active pending relation 中所有 OA row 已 completed 后，promotion service 复用 Workbench relation command 创建普通 Workbench relation，pending relation 标记 `promoted` 并释放 bank claim；多 OA 关系在全部 OA completed 前跳过；migration 0073 将历史 `origin=oa_pending_payment_in_progress` Workbench active relation 迁移到独立 pending relation 并撤回旧 Workbench active relation。 |
| OA 付款状态判定 | P0 | `tests/test_oa_pending_payment_service.py`、`tests/test_invoice_lifecycle_policy.py`、`tests/test_invoice_lifecycle_page_integration.py` | covered | OA 主行、decimal total、多流水合并、少付/已付/未付、支出流水大于 OA 合计进入 `pending_review`、lifecycle policy delegate。 |
| 关联台分组关系 | P0 | `tests/test_oa_pending_payment_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | covered | 多 OA/多流水/多发票 relation 只生成一条 OA 待付款行，金额显示合计和 `+N`，详情可分别展开 OA/流水/发票；relation 内成员即使需要通过 OA projection lookup 补齐，也不得退化成主 OA 单行或重复 standalone row。 |
| 缺失或非法付款证据 | P0 | `tests/test_oa_pending_payment_service.py` | covered | 收入流水不算付款证据；缺失关联银行事实进入 `pending_review`。 |
| 服务端筛选/排序/分页 | P0 | `tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | covered | keyword、month、bank account、bank direction、payment status、native SQL columns、非法参数；`test_page_size_limit_protects_first_screen_slo` 用 250 行 synthetic 数据验证后端 `page_size=200` 上限和 `page_size>200` 的 `invalid_paging`；前端首屏 rows 请求锁定 `page=1&page_size=20`，每页选项限制为 20/50/100。 |
| API contract | P0 | `tests/test_oa_pending_payment_api.py` | covered | rows、filter-options、OA/bank/invoice/detail、`kind=oa|bank|invoice` relation detail、错误 shape、权限 403。 |
| read model freshness | P0 | `tests/test_oa_pending_payment_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | covered | repository unavailable、miss、stale/source mismatch、detail stale/missing 都返回 refreshing 并入队，不 live scan；OA pending `all` source versions 优先从实际 rows 聚合，历史空 scope 不污染默认视图。 |
| SQL projection/repository | P0 | `tests/test_invoice_usage_collection_sql_runtime.py` | covered | rows 保存 source versions/bank total、detail lookup native columns、all scope source version 聚合、空 scope 标记。 |
| worker fan-out | P0 | `tests/test_oa_projection_sync_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_runtime_worker_registry.py` | covered | `oa.sync` 会把 OA 投影变更 fan-out 到 `oa_pending_payment` 月份和 all scope；`oa_pending_payment.read_model.refresh` all scope 扩展月份 shard，RabbitMQ/default dispatch event 覆盖；stale source_version event 在 rebuild/fan-out 前跳过，不能覆盖较新的 read model。 |
| lifecycle fan-out | P0 | `tests/test_derived_data_lifecycle_service.py`、`tests/test_pending_invoice_api.py` | covered/documented-risk | OA rebuild / invoice lifecycle 计划覆盖；pending rules API 已断言会入队 `oa_pending_payment`，但 dry-run domain 名称仍通过 workbench executor 间接表达。 |
| App Status / registry | P1 | `tests/test_app_status_overview_service.py`、`tests/test_app_status_readiness_backfill.py`、`tests/test_runtime_worker_registry.py` | covered | domain registry、read model registry、worker registry、missing/failed readiness 状态。 |
| 前端页面交互 | P1 | `web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-flow.spec.ts`、`web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts`、`web/e2e/oa-pending-payments-bank-link-flow.spec.ts`、`web/e2e/oa-pending-payments-nonfresh-flow.spec.ts`、`web/e2e/workbench-relations-oa-pending-fanout.spec.ts` | covered | sidebar route、`已完成 OA/进行中 OA` 切换、两种视图统一 OA/支付状态/流水/发票四分组表格、页面级自动匹配/写回、进行中 OA 勾选与支出流水关联抽屉、写回状态、首屏有界 `page_size=20` 请求、显式刷新入口、column filters/sort、drawer、rules drawer、empty/error、rows non-fresh 诊断、rows 临时失败错误态、refreshing detail unavailable；Vitest 锁定 auto-reconcile/link-bank/规则保存成功后等待 `oa_pending_payment` operation barrier，barrier fresh 前不得刷新 rows；Playwright 补充真实 Chromium 下首屏、rows 暂时 503 后错误态不伪空态/手动刷新恢复、搜索、筛选、排序和详情/规则抽屉闭环，进行中 OA 自动匹配/写回成功与失败闭环，进行中 OA bank-link 抽屉禁选/筛选/提交/自动写回/失败零半写闭环，rows/detail non-fresh 诊断闭环，并覆盖 Workbench confirm 后 OA 待付款行从 `支付少了` 刷新为 `已支付`。 |
| 表格样式/布局回归 | P1 | `web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts`、`web/e2e/oa-pending-payments-flow.spec.ts` | covered | compact table、OA 内部申请人/项目/申请事由/对方户名/金额五栏、流水内部对方户名/金额/摘要三栏、发票纵向展示、支付状态窄列、银行金额/方向 chip 非重叠、空流水/空发票 dash、项目下申请时间、真实 Chromium 下无横向滚动。 |
| 真实 OA/生产 worker drain | P2 | staging / runbook | documented-risk | 需要真实 OA/Mongo、生产 Postgres、RabbitMQ/Redis/systemd worker、真实大数据和浏览器 smoke。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_payment_status_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | 覆盖付款状态、金额边界、多关系合并、缺失事实、支出/收入方向、自动匹配/自动写回状态流转、`flow_id` 准入/候选解析和 lifecycle policy delegate。 |
| 2. Service-layer tests | 适用 | `tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_relation_promotion_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | 覆盖 query service、command service、pending relation promotion service、OA payment status repository 最新 flow_id 列表、read model service、queue enqueue、detail lookup、projection builder、refresh service 和大页请求上限。 |
| 3. API contract tests | 适用 | `tests/test_oa_pending_payment_api.py`、`web/src/test/apiClient.test.ts`、`web/src/test/OaPendingPaymentsPage.test.tsx` | 覆盖 rows/filter-options 的 `view_mode`、rows `summary.viewCounts` 前端使用、auto-reconcile 和 link-bank-transactions 成功响应 shape、bank-transaction-candidates、root `/api/*` 与 `/fin-ops/api/*` HTML fallback 到 canonical `/fin-ops-api/*`、validation/not found、权限、read model refreshing、detail unavailable 和 source version stale。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_oa_projection_sync_service.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_relation_sql_projection.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_oa_projection_sql_runtime.py`、`tests/test_postgres_migrations.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` | 覆盖普通 completed-only OA projection、OA sync 到 OA 待付款 read model fan-out、payment-admitted OA projection、pending relation promotion 后 affected scope refresh、Workbench active generation 和 relation projection 排除 active pending bank claim、SQL read model view counts、source versions、all/month scope、worker event stale guard、registry 和 App Status。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts`、`web/e2e/oa-pending-payments-flow.spec.ts`、`web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts`、`web/e2e/oa-pending-payments-bank-link-flow.spec.ts`、`web/e2e/oa-pending-payments-nonfresh-flow.spec.ts`、`web/e2e/workbench-relations-oa-pending-fanout.spec.ts` | 覆盖 loading/empty/error、首屏有界分页请求、显式刷新入口、`已完成 OA N条/进行中 OA N条` 切换、两种视图统一四分组表格、支付状态筛选、自动匹配/写回请求、无人工写回按钮、进行中 OA checkbox、支出流水关联抽屉默认全部/已关联禁选/提交 body、写回状态、筛选/排序、drawer、规则 drawer、rows non-fresh 不当真实空态、rows 暂时失败不伪空态、refreshing detail、写后 operation barrier、OA 内部五栏、流水内部三栏和发票纵向展示 CSS/DOM 布局；Playwright 补充真实浏览器 rows 暂时 503 后错误态不伪空态/手动刷新恢复、只读链路、auto-reconcile 成功/失败/刷新链路、bank-link 抽屉禁选/筛选/提交/自动写回/失败链路、成功写流无可见错误残留、rows/detail non-fresh 诊断链路、无横向滚动断言和 Workbench confirm 后 linked fan-out。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_oa_pending_payment_command_service.py`、`tests/test_pending_invoice_api.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-flow.spec.ts`、`web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts`、`web/e2e/oa-pending-payments-bank-link-flow.spec.ts`、`web/e2e/workbench-relations-oa-pending-fanout.spec.ts` | 覆盖自动匹配 -> Workbench relation confirm -> OA MySQL 写回 -> workbench/oa_pending_payment refresh enqueue；覆盖进行中 OA 抽屉关联 -> Workbench relation confirm -> 自动写回 OA MySQL -> OA pending/Workbench refresh enqueue；也覆盖规则保存/关系变化 -> lifecycle/dirty scope -> OA read model refresh -> 页面刷新语义；Browser e2e 覆盖 rows 暂时加载失败 -> 错误态/非普通空态 -> 手动刷新 -> fresh rows/pagination 恢复，进行中 OA auto-reconcile -> rows/read model 重新读取 -> 写回状态更新且无错误残留、失败零半写，进行中 OA link-bank -> rows/read model 重新读取 -> relation evidence 和写回状态更新且无错误残留，以及 Workbench confirm -> OA pending rows fresh 后页面刷新；真实 worker drain 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部测试 + `tests/test_app_status_readiness_backfill.py`、`web/e2e/oa-pending-payments-flow.spec.ts`、`web/e2e/workbench-relations-oa-pending-fanout.spec.ts` | 每次变更都要保护旧 API shape、旧 completed 视图筛选/排序/分页、旧 detail payload、权限、App Status、页面布局、浏览器层详情抽屉/规则抽屉入口，以及 relation confirm 后付款状态刷新。 |

## 历史 bug 回归库

| 历史问题 | 回归入口 | 保护点 |
| --- | --- | --- |
| OA 申请时间只在 detail fields 中，页面没有展示 | `tests/test_oa_pending_payment_service.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | `oa.applicationTime` 从 `申请日期` 提取并展示在项目下方。 |
| 没有支出流水时显示 `0.00`、方向 chip 或“交易时间为空” | `web/src/test/OaPendingPaymentsPage.test.tsx` | 缺流水只显示 `-`，不显示误导金额或方向。 |
| 生产 read model miss/stale 时回退 live scan | `tests/test_oa_pending_payment_api.py` | production rows/filter/detail 非 fresh 只返回 refreshing 并入队。 |
| source version 缺失时返回旧 rows | `tests/test_oa_pending_payment_api.py` | stale rows 被清空，返回 `read_model_stale_reasons`。 |
| all scope 没有单独 scope row 被误判 missing | `tests/test_oa_pending_payment_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | all scope 聚合月份 rows/source versions，不要求 all scope row。 |
| all scope 被全局 `workbench_relation:all` expected source versions 误判 stale | `tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_production_all_scope_does_not_loop_on_relation_all_versions` | 默认 all 查询不能等待 fan-out-only parent/global relation all proof；已 fresh 的月份 shard 不应反复入队刷新。 |
| 历史空 scope 的旧 source version 把默认视图误判 stale | `tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_oa_repository_all_scope_aggregates_monthly_scope_source_versions` | `all` scope 有实际 rows 时优先从 rows 聚合 source versions，旧空月份 scope 不参与。 |
| 旧 refresh event 覆盖新 read model | `tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_oa_refresh_handler_skips_stale_source_version_before_rebuild` | refresh handler 先检查 `read_model_refresh_is_current`，stale event 不 rebuild、不 fan-out、不 complete dirty scope。 |
| 收入流水被当作付款证据 | `tests/test_oa_pending_payment_service.py` | 只有 outflow bank relation 计入付款。 |
| rows read model 正刷新时显示真实空态 | `web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-nonfresh-flow.spec.ts` | 展示中性“OA 待付款核对数据正在刷新”，不显示“当前条件下暂无记录。”，也不泄露 stale reason。 |
| rows read model 正刷新时分页显示 `NaN-NaN / undefined` | `tests/test_oa_pending_payment_api.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | refreshing rows/filter-options payload 仍返回稳定 `summary.rowCount` 和 `summary.viewCounts`；前端把缺失或非有限分页 total 归零，不渲染 `NaN` 或 `undefined`。 |
| rows 首屏暂时 503 时显示普通空态或无法恢复 | `web/e2e/oa-pending-payments-flow.spec.ts::recovers rows after a transient load failure when refreshed`、`web/src/test/OaPendingPaymentsPage.test.tsx` | 展示错误 alert 和错误态空行，不显示普通空态；用户点击显式刷新后恢复 fresh rows 和分页。 |
| detail read model 正刷新时 drawer 显示崩溃或空白 | `web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-nonfresh-flow.spec.ts` | 展示中性“详情暂不可用”。 |
| 多条 OA 共用同一 relation 被拆成多行并显示“支付多了” | `tests/test_oa_pending_payment_service.py`、`tests/test_invoice_lifecycle_policy.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | relation group 合并为一条行；状态不输出 `overpaid`/`merged_paid`；前端以合计金额和 `+N` 展示。 |
| relation 里多条 OA 未进入首轮 OA 列表导致 OA 侧只显示主 OA | `tests/test_oa_pending_payment_service.py::OaPendingPaymentQueryServiceTests::test_relation_group_loads_all_oa_members_from_projection_lookup_and_suppresses_standalone_rows` | relation group 必须按 relation OA row ids 反查并补齐可权威读取的 OA records；OA 金额、`relationCount`、`summaries` 和 payment status 都基于完整 relation 成员，已聚合成员不得再单独成项。 |
| 大页请求导致首屏退化为全量读取 | `tests/test_oa_pending_payment_service.py::OaPendingPaymentQueryServiceTests::test_page_size_limit_protects_first_screen_slo`、`web/src/test/OaPendingPaymentsPage.test.tsx` | 后端 `page_size=200` 返回 200 行且 total 保留，`page_size>200` 返回 `invalid_paging`；前端首屏显式发送 `page=1&page_size=20` 且页大小选项限制为 20/50/100。 |
| 进行中 OA 候选流水被自动写回 | `tests/test_oa_pending_payment_command_service.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts` | 候选/未确认 relation 不能写回；后端必须校验 active relation 或自动确认 relation、outflow、金额和 `flow_id`；Browser 覆盖自动匹配单次 mutation、成功后刷新为 `已写回`，失败时保留 `未写回`。 |
| 进行中 OA 精确候选被静默跳过 | `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_auto_reconcile_reports_skipped_exact_match_when_flow_id_is_missing` | 规则层识别出 OA-bank 精确候选后，如果 `flow_id` 缺失、写回不可用或 relation confirm 失败，auto-reconcile 响应必须携带 `skippedAutoMatches` 诊断，不能只返回 0 条让现场无法判断原因。 |
| 全部月份自动匹配接口把 `all` 传给候选匹配服务导致 500 | `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_auto_reconcile_all_months_groups_matches_by_month` | `month=all` 时必须按 OA 自身月份分组调用候选匹配服务，只用同月未配对支出流水生成候选；不得把 `scope_month=all` 传入只接受 `YYYY-MM` 的 Workbench candidate matcher，也不得跨月自动匹配。 |
| 进行中 OA 页面 fresh 但自动匹配命令看不到 OA | `tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_auto_reconcile_uses_payment_admitted_source_after_completed_projection_cache` | 生产启动时显式 completed/Postgres 投影不能写入默认 payment-admitted projection 缓存；auto-reconcile 必须使用能读取当前 in-progress OA 的 lazy source adapter。 |
| 自动匹配成功但 relation 未落持久层 | `tests/test_oa_pending_payment_api.py::OaPendingPaymentApiTests::test_auto_reconcile_persists_relation_and_reload_is_noop` | auto-reconcile 确认 OA-bank relation 后必须保存到 state store；应用重建后 active relation 查询必须能命中同一 OA/流水，重复执行不能再次 auto-match 或重复写回。 |
| 进行中 OA 抽屉关联后未自动写回 | `tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_oa_pending_payment_service.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-bank-link-flow.spec.ts` | link-bank-transactions 创建 OA 待付款独立 pending relation 和 bank claim 后必须在校验通过时自动调用 OA MySQL 写回；已配对/已关联进行中 OA 流水在抽屉禁选；Browser 断言无人工写回按钮、刷新后为 `已写回`。 |
| 已写回的 active 支出流水 relation 反复触发自动写回和 read model refresh | `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_auto_reconcile_existing_paid_relation_is_noop_when_oa_is_already_written` | 已有 valid active relation 且同一 `flow_id` 已经 `pay_status=1` 时，页面级 auto-reconcile 必须 no-op：不再次 mark-paid、不返回写回记录、不 enqueue read model refresh。 |
| 写后立即读旧 OA 待付款投影 | `web/src/test/OaPendingPaymentsPage.test.tsx::waits for the OA pending payment barrier before reloading after auto reconcile`、`web/src/test/OaPendingPaymentsPage.test.tsx::waits for the OA pending payment barrier before reloading after bank link`、`web/src/test/OaPendingPaymentsPage.test.tsx::waits for OA pending payment barrier before reloading after rule save` | auto-reconcile、link-bank 和规则保存成功后都必须等待 `oa_pending_payment` operation barrier fresh，再重新读取 rows。 |
| rows read model 仍 refreshing 时触发自动匹配/写回 | `web/src/test/OaPendingPaymentsPage.test.tsx::does not auto reconcile while OA pending payment read model is still refreshing` | 页面必须先让 rows/filter-options 完成 fresh gate；refreshing/stale/unavailable 或加载失败时不得触发 `auto-reconcile-bank-transactions`，避免后台同步中叠加写命令和刷新队列。 |
| 自动匹配/写回暂时失败后本页不再重试 | `web/src/test/OaPendingPaymentsPage.test.tsx::retries auto reconcile after a failed attempt when the user refreshes rows` | auto-reconcile 请求失败时不得把 scope 永久标记为已完成；用户点击刷新 rows 后，应在 fresh gate 通过时重新触发自动匹配/写回。 |
| 根 `/api/*` 或 `/fin-ops/api/*` 被 SPA HTML fallback 吞掉 | `web/src/test/apiClient.test.ts::falls back to canonical fin-ops API prefix when root API returns the SPA shell under fin-ops`、`web/src/test/apiClient.test.ts::falls back to canonical fin-ops API prefix when a root API request returns HTML outside the fin-ops page path`、`web/src/test/apiClient.test.ts::falls back to canonical fin-ops API prefix when a fin-ops relative API request returns HTML` | API client 在确认同源根 `/api/*` 或 `/fin-ops/api/*` 返回 HTML 时，重试 canonical `/fin-ops-api/*`，不再依赖当前页面路径必须是 `/fin-ops/`；正常 JSON/API 错误不重试。 |
| completed OA 已有 active relation 但 relation payload 缺 row_types 时未写回 | `tests/test_oa_pending_payment_command_service.py::OaPendingPaymentCommandServiceTests::test_auto_reconcile_writes_completed_oa_from_explicit_relation_ids_when_row_types_are_missing` | 页面级 auto-reconcile 处理 completed 已关联流水时，必须能从 `oa_row_ids`/`bank_transaction_ids` 或 camelCase 字段解析 OA 和银行流水；缺失 `row_types` 不得导致静默跳过 `t_payment_simple.pay_status=1` 写回。 |
| OA 已完成后仍留在进行中视图 | `tests/test_oa_pending_payment_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | rows/filter-options 根据 `oa.workflow_status` 和 `view_mode` 过滤；下一次 OA sync/read model refresh 后已完成 OA 从 in-progress 视图移除。 |
| 同业务字段的合法二次支付被 completed 指纹误删 | `tests/test_oa_pending_payment_service.py::OaPendingPaymentQueryServiceTests::test_in_progress_view_keeps_payment_admitted_record_when_completed_projection_has_same_business_record` | in-progress 视图不得按 completed projection 的业务指纹排除 payment-admitted 记录；生产 `oa-pay-69e5...` 这类已进入 `t_payment_simple` 的不同 flow id 要保留，避免误删合法的同款/同额/同供应商二次支付。 |
| OA MySQL 支付状态使用了错误 ID | `tests/test_oa_payment_status_service.py`、`tests/test_mongo_oa_adapter.py` | `t_payment_simple.flow_id` 使用 OA Mongo 文档 ID；流程实例 ID/流程请求 ID 不直接替代 Mongo 文档 ID。 |
| 网络波动重复提交 OA 进入进行中视图 | `tests/test_oa_pending_payment_service.py::OaPendingPaymentQueryServiceTests::test_only_in_progress_view_uses_payment_status_admission_projection` | 只有 `t_payment_simple.flow_id` 中存在的进行中 OA Mongo `_id` 进入进行中视图；completed 不受该准入表限制；未入表的重复/异常进行中 OA 不展示。 |
| 普通 OA projection 混入进行中 OA | `tests/test_oa_projection_sync_service.py`、`tests/test_oa_projection_sql_runtime.py`、`tests/test_workbench_relation_sql_projection.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | `oa.sync` 只写 completed/legacy 到 `app.oa_applications`，普通 list/read SQL 带 completed filter；待付款页面 completed 读取普通 projection，in-progress 另走 payment-admitted projection。 |
| 切换按钮数量和表格当前视图不一致 | `tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | SQL read model 返回同筛选条件下的 `summary.viewCounts`，前端展示 tab 数量。 |

## 关键 Smoke Flows

| Flow | 自动化保护 | 手工/真实环境补充 |
| --- | --- | --- |
| OA rebuild -> invoice lifecycle -> OA pending payment rows | `tests/test_derived_data_lifecycle_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | staging 跑真实 OA sync，并观察 `oa_pending_payment` readiness。 |
| 银行/发票导入 -> Workbench relation -> OA 支付状态变化 | `tests/test_oa_pending_payment_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | 用真实导入样本验证 worker drain 和页面刷新。 |
| 进行中 OA -> 自动匹配未配对支出流水 -> OA 写回 | `tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_oa_pending_payment_service.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-confirm-paid-flow.spec.ts` | Browser mock 已覆盖自动匹配写回、rows/read model refresh、read model non-fresh 时不触发自动写命令和失败零半写；staging 仍需配置真实 OA MySQL env，并确认 `t_payment_simple.pay_status` 与页面 `oaPaymentWriteback` 同步。 |
| 进行中 OA 勾选 -> 支出流水抽屉关联 -> 表格刷新并写回 | `tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_oa_pending_payment_service.py`、`tests/test_workbench_relation_sql_projection.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-bank-link-flow.spec.ts` | Browser mock 已覆盖抽屉默认全部、已配对/已关联禁选、提交后 rows/read model refresh、自动写回和失败零半写；staging 仍需用真实支出流水验证 OA 待付款独立 pending relation、关联台不显示该进行中 OA、OA 待付款刷新，以及 `t_payment_simple.pay_status` 被 link 后自动写成已支付。 |
| 进行中 OA completed -> pending relation promotion -> Workbench relation | `tests/test_oa_pending_payment_relation_promotion_service.py`、`tests/test_oa_projection_sync_service.py`、`tests/test_postgres_migrations.py` | 自动化覆盖 promotion 编排、affected scope refresh、历史 relation migration；staging 仍需用真实 OA sync 验证进行中 OA 完成后从 in-progress 移除、进入 completed，并在关联台变成普通 Workbench relation。 |
| 待找发票规则保存 -> invoice lifecycle -> OA 待付款刷新 | `tests/test_pending_invoice_api.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | 前端规则保存成功后必须等待 `oa_pending_payment` operation barrier，再刷新 rows；若后续把 indirect fan-out 改成显式 domain，必须先补 lifecycle plan 单测。 |
| rows/filter-options/detail 非 fresh | `tests/test_oa_pending_payment_api.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-nonfresh-flow.spec.ts` | Browser mock 已覆盖 rows refreshing 诊断和 detail 202 unavailable；真实 worker 停止/恢复时仍需确认页面不把空 rows 当 fresh。 |
| Browser rows/filter/detail/rules | `web/e2e/oa-pending-payments-flow.spec.ts`、`web/e2e/workbench-relations-oa-pending-fanout.spec.ts` | Browser mock 已覆盖 rows 暂时 503 后手动刷新恢复；staging 仍需真实 OA/Mongo、真实 Postgres 大数据和真实 worker drain。 |

## 模块验证命令

最小模块验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_oa_pending_payment_api tests.test_invoice_lifecycle_page_integration -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_payment_status_service tests.test_oa_pending_payment_command_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_relation_promotion_service tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_excludes_bank_rows_claimed_by_in_progress_oa_relation tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_excludes_candidate_decisions_claimed_by_in_progress_oa_relation tests.test_workbench_relation_sql_projection tests.test_oa_projection_sync_service tests.test_postgres_migrations -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service.OaPendingPaymentQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v
PYTHONPATH=backend/src python3 -m unittest tests.test_mongo_oa_adapter tests.test_oa_projection_sql_runtime tests.test_invoice_usage_collection_sql_runtime tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v
cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx src/test/TableAlignmentStyles.test.ts
cd web && npm run build
cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts
cd web && npx playwright test e2e/oa-pending-payments-confirm-paid-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/oa-pending-payments-bank-link-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/oa-pending-payments-nonfresh-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/workbench-relations-oa-pending-fanout.spec.ts --project=chromium
cd web && npm run e2e:smoke
bash scripts/verify.sh docs
```

扩展验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_readiness_backfill tests.test_read_model_readiness_reporter tests.test_deploy_runtime_examples -v
cd web && npm test -- --run src/test/AppStatusIndicator.test.tsx
```

## Nightly CI 覆盖

- `scripts/verify.sh backend` 覆盖后端核心回归，但具体模块命令仍以本文件为准。
- `scripts/verify.sh frontend` 覆盖前端 test/build，但本模块变更应优先跑上方最小模块验证。
- `scripts/verify.sh e2e` / `npm run e2e:smoke` 覆盖 Playwright browser smoke，其中 `web/e2e/oa-pending-payments-flow.spec.ts` 保护 rows 首屏临时失败恢复、rows/filter/sort/detail/rules drawer，`web/e2e/workbench-relations-candidate-semantics.spec.ts` 保护 candidate OA/银行/发票 chip 不把付款状态直接推成 paid，`web/e2e/workbench-relations-oa-pending-fanout.spec.ts` 保护 Workbench confirm 后 OA 待付款刷新为 `已支付`。
- `scripts/verify.sh docs` 保护模块文档链接和格式。

## 未测风险

- 未连接真实 OA/Mongo，同步异常、OA 字段变体和真实权限菜单仍需 staging smoke。
- 本地自动化使用 fake MySQL repository；真实 OA MySQL `t_payment_simple` 写回、网络超时、账号权限和生产锁等待仍需 staging smoke。
- 未在真实生产 Postgres 上跑大数据量 filter/sort/detail lookup EXPLAIN、锁等待和长分页性能。
- deterministic Playwright 已覆盖浏览器首屏、筛选/排序、OA/流水/发票详情、规则抽屉、candidate/linked 负面语义和 Workbench confirm 后 linked fan-out；本地 synthetic page-size guard 不替代真实 PostgreSQL 大数据 EXPLAIN、浏览器滚动或真实网络中断恢复。
- 未跑真实 RabbitMQ/Redis/systemd `invoice-usage-collection` 与 `invoice-lifecycle` worker drain。
- 2026-06-17 runtime smoke 已确认服务器 `invoice-usage-collection` worker heartbeat 存在且仍可消费 `oa_pending_payment.read_model.refresh`；当前代码发布/重启该 worker 前，生产 read model 仍可能被旧部署覆盖回旧 source version。
- pending rules 对 OA 待付款的 fan-out 当前由执行层 workbench invalidation 间接入队，已有 API 回归保护；若后续需要 dry-run plan 也显式列出 `oa_pending_payment_read_model`，应作为独立生命周期重构补测试。
- Playwright smoke 已覆盖 rows 首屏暂时 503 后手动刷新恢复；仍不做真实浏览器像素级截图、虚拟滚动压力、mutation 级真实网络中断恢复和真实基础设施 worker drain。
