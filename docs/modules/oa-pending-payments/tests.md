# OA待付款核对测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

OA 待付款核对是 OA 申请、支出流水、进项发票、Workbench relation、invoice lifecycle 和 invoice usage collection read model 的交汇页。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 主行身份 | OA application record / OA projection | 列表以 OA 申请为主行；缺少银行或发票时不能丢掉 OA 行。 |
| 付款状态 | `InvoiceLifecyclePolicy`、`OaPendingPaymentQueryService` | `unpaid`、`paid`、`partially_paid`、`pending_review` 必须以 OA 金额、支出流水和 Workbench relation 事实判定；不得输出 `overpaid` 或 `merged_paid`。 |
| 支出流水证据 | `ImportNormalizationService`、Workbench relation read facade | 只允许支出流水作为付款证据；收入流水或缺失流水事实必须进入异常/待复核，不得算已付。 |
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
| OA 付款状态判定 | P0 | `tests/test_oa_pending_payment_service.py`、`tests/test_invoice_lifecycle_policy.py`、`tests/test_invoice_lifecycle_page_integration.py` | covered | OA 主行、decimal total、多流水合并、少付/已付/未付、支出流水大于 OA 合计进入 `pending_review`、lifecycle policy delegate。 |
| 关联台分组关系 | P0 | `tests/test_oa_pending_payment_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | covered | 多 OA/多流水/多发票 relation 只生成一条 OA 待付款行，金额显示合计和 `+N`，详情可分别展开 OA/流水/发票。 |
| 缺失或非法付款证据 | P0 | `tests/test_oa_pending_payment_service.py` | covered | 收入流水不算付款证据；缺失关联银行事实进入 `pending_review`。 |
| 服务端筛选/排序/分页 | P0 | `tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | covered | keyword、month、bank account、bank direction、payment status、native SQL columns、非法参数；`test_page_size_limit_protects_first_screen_slo` 用 250 行 synthetic 数据验证后端 `page_size=200` 上限和 `page_size>200` 的 `invalid_paging`；前端首屏 rows 请求锁定 `page=1&page_size=20`，每页选项限制为 20/50/100。 |
| API contract | P0 | `tests/test_oa_pending_payment_api.py` | covered | rows、filter-options、OA/bank/invoice/detail、`kind=oa|bank|invoice` relation detail、错误 shape、权限 403。 |
| read model freshness | P0 | `tests/test_oa_pending_payment_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | covered | repository unavailable、miss、stale/source mismatch、detail stale/missing 都返回 refreshing 并入队，不 live scan。 |
| SQL projection/repository | P0 | `tests/test_invoice_usage_collection_sql_runtime.py` | covered | rows 保存 source versions/bank total、detail lookup native columns、all scope source version 聚合、空 scope 标记。 |
| worker fan-out | P0 | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_runtime_worker_registry.py` | covered | `oa_pending_payment.read_model.refresh` all scope 扩展月份 shard，RabbitMQ/default dispatch event 覆盖。 |
| lifecycle fan-out | P0 | `tests/test_derived_data_lifecycle_service.py`、`tests/test_pending_invoice_api.py` | covered/documented-risk | OA rebuild / invoice lifecycle 计划覆盖；pending rules API 已断言会入队 `oa_pending_payment`，但 dry-run domain 名称仍通过 workbench executor 间接表达。 |
| App Status / registry | P1 | `tests/test_app_status_overview_service.py`、`tests/test_app_status_readiness_backfill.py`、`tests/test_runtime_worker_registry.py` | covered | domain registry、read model registry、worker registry、missing/failed readiness 状态。 |
| 前端页面交互 | P1 | `web/src/test/OaPendingPaymentsPage.test.tsx` | covered | sidebar route、grouped table、首屏有界 `page_size=20` 请求、column filters/sort、drawer、rules drawer、empty、refreshing detail unavailable。 |
| 表格样式/布局回归 | P1 | `web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts` | covered | compact table、银行金额/方向 chip 非重叠、空流水 dash、项目下申请时间。 |
| 真实 OA/生产 worker drain | P2 | staging / runbook | documented-risk | 需要真实 OA/Mongo、生产 Postgres、RabbitMQ/Redis/systemd worker、真实大数据和浏览器 smoke。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_oa_pending_payment_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | 覆盖付款状态、金额边界、多关系合并、缺失事实、支出/收入方向和 lifecycle policy delegate。 |
| 2. Service-layer tests | 适用 | `tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | 覆盖 query service、read model service、queue enqueue、detail lookup、projection builder、refresh service 和大页请求上限。 |
| 3. API contract tests | 适用 | `tests/test_oa_pending_payment_api.py` | 覆盖成功响应 shape、validation/not found、权限、read model refreshing、detail unavailable 和 source version stale。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` | 覆盖 SQL read model、source versions、all/month scope、worker event、registry 和 App Status。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts` | 覆盖 loading/empty/error、首屏有界分页请求、筛选/排序、drawer、规则 drawer、refreshing detail、表格 CSS 和布局。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_pending_invoice_api.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | 覆盖规则保存/关系变化 -> lifecycle/dirty scope -> OA read model refresh -> 页面刷新语义；真实 worker drain 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部测试 + `tests/test_app_status_readiness_backfill.py` | 每次变更都要保护旧 API shape、旧筛选/排序/分页、旧 detail payload、权限、App Status 和页面布局。 |

## 历史 bug 回归库

| 历史问题 | 回归入口 | 保护点 |
| --- | --- | --- |
| OA 申请时间只在 detail fields 中，页面没有展示 | `tests/test_oa_pending_payment_service.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | `oa.applicationTime` 从 `申请日期` 提取并展示在项目下方。 |
| 没有支出流水时显示 `0.00`、方向 chip 或“交易时间为空” | `web/src/test/OaPendingPaymentsPage.test.tsx` | 缺流水只显示 `-`，不显示误导金额或方向。 |
| 生产 read model miss/stale 时回退 live scan | `tests/test_oa_pending_payment_api.py` | production rows/filter/detail 非 fresh 只返回 refreshing 并入队。 |
| source version 缺失时返回旧 rows | `tests/test_oa_pending_payment_api.py` | stale rows 被清空，返回 `read_model_stale_reasons`。 |
| all scope 没有单独 scope row 被误判 missing | `tests/test_oa_pending_payment_api.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | all scope 聚合月份 rows/source versions，不要求 all scope row。 |
| 收入流水被当作付款证据 | `tests/test_oa_pending_payment_service.py` | 只有 outflow bank relation 计入付款。 |
| detail read model 正刷新时 drawer 显示崩溃或空白 | `web/src/test/OaPendingPaymentsPage.test.tsx` | 展示中性“详情暂不可用”。 |
| 多条 OA 共用同一 relation 被拆成多行并显示“支付多了” | `tests/test_oa_pending_payment_service.py`、`tests/test_invoice_lifecycle_policy.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | relation group 合并为一条行；状态不输出 `overpaid`/`merged_paid`；前端以合计金额和 `+N` 展示。 |
| 大页请求导致首屏退化为全量读取 | `tests/test_oa_pending_payment_service.py::OaPendingPaymentQueryServiceTests::test_page_size_limit_protects_first_screen_slo`、`web/src/test/OaPendingPaymentsPage.test.tsx` | 后端 `page_size=200` 返回 200 行且 total 保留，`page_size>200` 返回 `invalid_paging`；前端首屏显式发送 `page=1&page_size=20` 且页大小选项限制为 20/50/100。 |

## 关键 Smoke Flows

| Flow | 自动化保护 | 手工/真实环境补充 |
| --- | --- | --- |
| OA rebuild -> invoice lifecycle -> OA pending payment rows | `tests/test_derived_data_lifecycle_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py` | staging 跑真实 OA sync，并观察 `oa_pending_payment` readiness。 |
| 银行/发票导入 -> Workbench relation -> OA 支付状态变化 | `tests/test_oa_pending_payment_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | 用真实导入样本验证 worker drain 和页面刷新。 |
| 待找发票规则保存 -> invoice lifecycle -> OA 待付款刷新 | `tests/test_pending_invoice_api.py` | 若后续把 indirect fan-out 改成显式 domain，必须先补 lifecycle plan 单测。 |
| rows/filter-options/detail 非 fresh | `tests/test_oa_pending_payment_api.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` | 真实 worker 停止/恢复时确认页面不把空 rows 当 fresh。 |

## 模块验证命令

最小模块验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_oa_pending_payment_api tests.test_invoice_lifecycle_page_integration -v
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service.OaPendingPaymentQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v
cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx src/test/TableAlignmentStyles.test.ts
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
- `scripts/verify.sh docs` 保护模块文档链接和格式。

## 未测风险

- 未连接真实 OA/Mongo，同步异常、OA 字段变体和真实权限菜单仍需 staging smoke。
- 未在真实生产 Postgres 上跑大数据量 filter/sort/detail lookup EXPLAIN、锁等待和长分页性能。
- 本地 synthetic page-size guard 不替代真实 PostgreSQL 大数据 EXPLAIN、浏览器滚动或真实网络中断恢复。
- 未跑真实 RabbitMQ/Redis/systemd `invoice-usage-collection` 与 `invoice-lifecycle` worker drain。
- pending rules 对 OA 待付款的 fan-out 当前由执行层 workbench invalidation 间接入队，已有 API 回归保护；若后续需要 dry-run plan 也显式列出 `oa_pending_payment_read_model`，应作为独立生命周期重构补测试。
- 前端 Vitest 不做真实浏览器像素级截图、虚拟滚动压力和网络中断恢复。
