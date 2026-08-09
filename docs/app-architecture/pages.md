# 页面架构与页面间影响关系

本文维护当前页面的路由、组件入口、API client、刷新来源和跨页面影响关系。页面自己的筛选、排序、分页、导出 shape 和 UI 状态可以留在页面 service 或组件里；业务规则、read model freshness 和跨页事实必须回到后端 policy/service/read boundary。

## 代码事实源

- 页面注册表：`web/src/app/pageRegistry.tsx`
- 路由入口：`web/src/app/router.tsx`
- 页面路由 host：`web/src/app/PageRouteHost.tsx`
- 页面运行时激活上下文：`web/src/contexts/PageRuntimeContext.tsx`
- 页面会话状态：`web/src/contexts/PageSessionStateContext.tsx`
- 表格会话：`web/src/hooks/useFinanceTableSession.ts`
- 侧边栏：`web/src/components/shell/sidebarItems.ts`（从页面注册表派生）
- 页面入口：`web/src/pages/*`
- API client：`web/src/features/*/api.ts`
- 操作闭环 API client：`web/src/features/operationBarrier/api.ts`
- 后端路由：`backend/src/fin_ops_platform/app/routes_*.py` 与仍在 `server.py` 的 legacy handler

## 页面分组

| 页面域 | 前端入口 | API / 后端 owner | 主要事实来源 | 刷新来源 |
| --- | --- | --- | --- | --- |
| 银企核销 / 关联台 | `web/src/pages/ReconciliationPage.tsx`、workbench 页面组件 | reconciliation/workbench routes、workbench service、read model service | 银行流水、OA 单据、发票、确认关系、active generation | route 进入/重进、页面查询变化、当前页写后 reconcile、手动重试 |
| 银行明细 | `web/src/pages/BankDetailsPage.tsx` | bank detail routes、`BankDetailsCanonicalQueryService` | canonical 银行流水、分类/标签、账户映射、active Workbench pair relations | route 进入/重进、查询变化、当前页写后一次 GET、用户重试 |
| 往来款管理 | `web/src/pages/TurnoverLedgerPage.tsx` | turnover ledger routes/service、workbench pair relation service | 外部往来候选、人工闭环、利息、项目归因、Workbench pair relation | 银行明细、关联台、人工闭环/撤回 |
| 待找发票 | `web/src/pages/PendingInvoicesPage.tsx` | pending invoice routes/query service | 支出/收入流水、进项发票、规则建议、选择已有发票关系、收入状态覆盖 | 进项导入、选择已有发票确认/撤回、收入状态覆盖、规则变更 |
| OA 待付款核对 | `web/src/pages/OaPendingPaymentsPage.tsx` | OA pending payments routes/query/command service + page-specific PostgreSQL repository | 单次 repeatable-read/read-only snapshot 中的 completed OA、in-progress admission、payment-status、active Workbench relation、银行/进项发票 canonical facts；不读历史 pending relation/claim、页面 read model/Mongo/MySQL | route/query变化/手工刷新/本页写后 normal GET；无 freshness enqueue、worker、202/304/ETag/polling |
| 税金抵扣 | `web/src/pages/TaxOffsetPage.tsx` | tax routes/query service/canonical repository | PostgreSQL canonical 进项/销项发票、认证导入事实、最新 saved 抵扣计划；不消费正式配对关系或其它页面 read model | 页面进入/重进、月份变化、抵扣计划保存或认证导入完成后重新 GET |
| 发票使用 | invoice usage pages | invoice usage canonical query routes | canonical 发票、使用状态、销项收款、ETC 发票、active pair relations | 页面进入/重进、查询变化、当前页写后重新 GET |
| ETC 业务批次 | ETC pages/components | ETC business batch routes/service、invoice PDF bundle service | ETC 票据、人工业务批次、导入草稿、OA 提交确认、草稿后批次发票合并下载 | ETC 导入、OA 草稿创建、人工提交确认、对象存储 PDF 读取与只读下载审计 |
| 成本统计 | cost statistics page | cost routes/query service | 项目、费用、发票、核销关系 | 项目范围变化、发票/流水关系变化 |
| 设置 / 账户 / 项目 | `web/src/pages/SettingsPage.tsx` | generic settings routes + admin-only access-control route | 普通设置、canonical Settings ACL、固定管理员、项目状态、规则配置；OA role/permission 不是 APP authority | 普通配置保存、版本化 ACL 变化、数据重置 |
| App Health | shell/status components | app health routes、runtime queue、worker registry | queue、read model freshness、worker 状态、cache 状态 | worker heartbeat、refresh job、后台任务 |

## 权限链路与跨页面影响

- React bootstrap 由 `SessionProvider` 请求 `/api/session/me`，`SessionGate` 只消费后端 normalized `allowed` / `access_tier` / capabilities 决定是否 mount 业务 router。OA roles/permissions 可保留为信息，不在前端反推 APP tier。
- 前端隐藏、禁用和 `SessionGate` 只是交互边界；backend global route policy 和模块自有 guard 才是 direct API 的权威边界。permission-bearing denied 账号直达 `/fin-ops/` 不 mount 业务页，直调受保护 API 返回 `403`。
- `/settings` 的“访问账户权限”是唯一 ACL UI，仅固定 `YNSYLP005` 加载和保存专用 API。full-access 用户仍可保存普通设置，但无法查询/写入 ACL；read-export 用户只读；denied 用户无法进入 router。
- APP tier 不写入 OA identity cache。账号从 ACL 删除后，同一 OA 身份的下一次 session/direct API 判断立即 denied。OA 菜单可见性由 canonical ACL 到三个专用角色的投影决定，以投影后的新 OA router/session 为验收边界，不承诺旧 DOM 无刷新消失。
- `finops:app:view` 只定位 OA 菜单。runtime Settings command 只验证严格三角色投影并更新其 members；历史 non-dedicated menu binding cleanup 已退休，部署只读验证 exact topology，不由页面、运行时或发布链宽删。
- 当前 18-route registry 由 `web/src/test/PageRouteHost.test.tsx`、`App.test.tsx` 和权限回归保护；App Health、操作历史、OA 申请人凭据和 data reset 的 admin-only 合同保持不变。这是本地自动化证据，不表示生产已发布。
- 该权限收敛没有新增或改变任何页面 response shape、read model、worker、dirty scope、outbox、Redis 或 cache key。

## Global Runtime Status Plane 页面域

所有页面必须通过后端 domain registry 接入全局状态平面。新增页面、read model、worker 或后台任务类型时，需要同步更新 registry、readiness projection 和测试，不能只在前端页面里显示局部状态。canonical 直读页面的 domain readiness 只能依赖 PostgreSQL/runtime 健康，不得虚构页面 read model readiness。

domain registry 是页面域入口；`AppStatusReadModelRegistry` 只登记 `workbench` 页面 read model
和共享 `workbench_relation` read model。它们从
`read_model.app_status_readiness` 和 current-effective queue 状态得到
`fresh/missing/refreshing/stale/failed/unavailable`，但不作为 canonical 页面 GET 的
freshness gate。

| domain key | route | 当前数据/任务来源 |
| --- | --- | --- |
| `workbench` | `/` | `workbench`、`workbench_relation`、workbench workers、workbench matching/rebuild jobs |
| `imports_bank_transactions` | `/imports/bank-transactions` | import worker、银行流水导入任务 |
| `imports_invoices` | `/imports/invoices` | import worker、发票导入任务 |
| `imports_etc_invoices` | `/imports/etc-invoices` | import worker、ETC 发票导入任务 |
| `bank_details` | `/bank-details` | canonical PostgreSQL snapshot；无页面 read model/worker |
| `pending_invoices` | `/pending-invoices` | canonical PostgreSQL snapshot；无页面 read model/worker |
| `oa_pending_payments` | `/oa-pending-payments` | canonical PostgreSQL snapshot；无页面 read model/worker |
| `input_invoice_usage` | `/input-invoice-usage` | PostgreSQL canonical repeatable-read snapshot；active `app.workbench_pair_relations`；无页面 read model/worker |
| `output_invoice_collections` | `/output-invoice-collections` | PostgreSQL canonical repeatable-read snapshot；销项发票、收入流水与 active `app.workbench_pair_relations`；红蓝票由 `output_invoice_reversal` 正式关系驱动；无页面 read model/worker 或 lifecycle overlay |
| `tax_offset` | `/tax-offset` | 单次 PostgreSQL repeatable-read canonical snapshot；页面无 Tax Offset read model/worker 依赖 |
| `cost_statistics` | `/cost-statistics` | 单次 PostgreSQL repeatable-read canonical snapshot；无 Cost read model/worker |
| `bank_flow_rule_batches` | `/bank-flow-rule-batches` | 单次 PostgreSQL repeatable-read canonical snapshot；无页面 read model/worker |
| `batch_accounting` | `/batch-accounting` | 单次 PostgreSQL repeatable-read canonical snapshot；复用银行明细 effective-category classifier + Settings 标签选择；无 Batch read model/worker |
| `turnover_ledger` | `/turnover-ledger` | 单次 PostgreSQL repeatable-read canonical snapshot；无 Turnover read model/worker |
| `etc_tickets` | `/etc-tickets` | ETC import jobs、ETC business batch manual OA status |
| `settings` | `/settings` | OA identity + canonical Settings ACL/ordinary settings store；ACL 不使用页面 read model、worker 或 cache |
| `app_health_operations` | `/operations/app-health` | runtime health dependencies、workers、queue、state store |

## 页面职责边界

- 页面可以决定筛选、排序、分页、空状态、导出列、drawer/dialog 状态。
- canonical 直读页面的写操作只等待当前 canonical command 完成；成功后当前页执行一次 normal GET。关联台写入还必须遵守自身 freshness/write gate。
- 页面切换时 `PageRouteHost` 只挂载当前匹配 route；离开页面会卸载页面 React tree，不保留隐藏 DOM frame、mounted cache、TTL/LRU 策略或页面数据 snapshot。返回页面时页面重新 mount，并通过现有 API/read boundary 重新加载数据。
- 页面注册表不声明保活策略；`AppPageRoute` 只维护 `path`、`pageKey`、`component`、`preload()` 和 `end`。侧栏分组继续从页面注册表派生，不能在侧栏里维护第二份路由事实。
- `PageRuntimeContext` 仅为当前挂载页面提供稳定的 `pageKey/active` 上下文；它不监听浏览器生命周期，不携带业务 DTO，也不协调跨页刷新。
- 页面入口使用 lazy route chunks；`AppPageRoute.preload()` 和 `SidebarItem.preload()` 是 route chunk 预加载入口。侧边栏可以在 hover/focus/touch start 时预加载目标页，但点击导航仍由 React Router `Link` 负责。
- 页面会话状态只保存当前浏览器标签页内的轻量可恢复 UI，例如查询、筛选、分页、排序、tab、选中行、展开行和详情 drawer target；不保存滚动位置、列表 rows、read model payload、loading、一次性 toast、失败中的提交、权限事实或业务事实。
- 财务表格继续使用 `FinanceTable` 和 `useFinanceTableSession` 保存分页、排序、过滤、列和选择状态。表格滚动位置不写入页面 session，返回页面后由浏览器和组件默认布局决定。
- 页面不能重新定义发票生命周期、银行标签、对象 identity/dedup、项目成本归因、往来状态分类等业务口径。
- canonical 直读页面的 query service 只组合本页所需 canonical facts；正式关系只读
  `app.workbench_pair_relations.status='active'`，不能读取历史 page projection。
- 只有一个页面使用且规则简单的派生结果，可以留在页面 service；后续被复用时再上提。

## Canonical 页面读取合同

- 页面专属 query repository 在一个 `REPEATABLE READ / READ ONLY` snapshot 中返回 rows、
  summary、counts、facets、筛选、排序和分页。
- 页面响应不包含 `read_model_status`、`source_versions`、`refresh_enqueued`、scope、job、
  freshness target 或 operation-barrier target。
- GET 不 enqueue、不轮询、不读取 Redis/RabbitMQ；PostgreSQL repository 缺失时 fail fast，
  不回退历史 projection 或进程内 snapshot。
- 普通确认、撤回、规则保存和 import confirm 只提交 canonical facts、audit、idempotency
  和业务 CAS；其它页面在下次正常进入/查询/手动刷新时读取同一事实源。
- 大批量 import/reapply/repair 可以保留独立 durable job，但 job 不是页面 read model。

关联台不适用本节：它继续使用 active-generation read model，查询先走 freshness gate，写入遵守 stale/write gate，refresh 由 durable queue 和 Workbench worker 完成。

## 前端刷新合同

- 普通写入不发送 finance domain event、window 自定义刷新事件或业务 `BroadcastChannel`。
- 当前页面可在命令成功后用自己的 normal GET 更新；其他页面不自动读取。
- route 进入/重进、页面查询变化、浏览器手动刷新和明确的页面重试是普通业务页面 load 入口。
- App Health、后台任务、导入/reapply/repair 进度与 Workbench refresh-status 属于运维/任务状态通道，保留各自明确 owner，不得被业务页面当成跨页刷新总线。

## 共享 Read Model 与后台任务

- `workbench`、`workbench_relation` 通过 gateway、durable queue、worker 和 App Status 闭环，只服务各自登记消费者。
- Search API/index runtime 已删除；legacy no-OA 列表请求内从 canonical batch facts 推导，不读取 projection、readiness 或 queue。
- Workbench matching/rebuild、OA sync 和 import processing 是 canonical integration/domain jobs。
- `bank_flow_rule_batches` 的未提交候选由请求内 live builder 实时推导，没有 event、worker、replay 或页面 projection；正式 submitted/withdrawn/history 继续读取持久化事实。
- `/api/operation-barrier/status` 只保留给合同明确返回非空 target 的 maintenance/job；
  普通页面 mutation 不调用。

## 维护要求

新增页面或改页面事实来源时，更新本文件的页面分组和影响关系。新增 derived lifecycle 或任务进度事件时，同时检查 `runtime-and-ownership.md`、`docs/dev/api-contracts.md` 和相关产品文档是否需要更新。
