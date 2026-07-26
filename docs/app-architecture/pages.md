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
| OA 待付款核对 | `web/src/pages/OaPendingPaymentsPage.tsx` | OA pending payments routes/query/command service + page-specific PostgreSQL repository | 单次 repeatable-read/read-only snapshot 中的 completed OA、in-progress admission、payment-status、active Workbench/pending relation、银行/进项发票 canonical facts；不读页面 read model/Mongo/MySQL | route/query变化/手工刷新/本页写后 normal GET；无 freshness enqueue、worker、202/304/ETag/polling |
| 税金抵扣 | `web/src/pages/TaxOffsetPage.tsx` | tax routes/query service/canonical repository | PostgreSQL canonical 进项/销项发票、认证导入事实、最新 saved 抵扣计划；不消费正式配对关系或其它页面 read model | 页面进入/重进、月份变化、抵扣计划保存或认证导入完成后重新 GET |
| 发票使用 | invoice usage pages | invoice usage canonical query routes | canonical 发票、使用状态、销项收款、ETC 发票、active pair relations | 页面进入/重进、查询变化、当前页写后重新 GET |
| ETC 业务批次 | ETC pages/components | ETC business batch routes/service、invoice PDF bundle service | ETC 票据、人工业务批次、导入草稿、OA 提交确认、草稿后批次发票合并下载 | ETC 导入、OA 草稿创建、人工提交确认、对象存储 PDF 读取与只读下载审计 |
| 成本统计 | cost statistics page | cost routes/query service | 项目、费用、发票、核销关系 | 项目范围变化、发票/流水关系变化 |
| 设置 / 账户 / 项目 | settings pages | settings/account/project routes | 用户、角色、项目状态、规则配置 | 配置保存、权限变化、数据重置 |
| App Health | shell/status components | app health routes、runtime queue、worker registry | queue、read model freshness、worker 状态、cache 状态 | worker heartbeat、refresh job、后台任务 |

## Global Runtime Status Plane 页面域

所有页面必须通过后端 domain registry 接入全局状态平面。新增页面、read model、worker 或后台任务类型时，需要同步更新 registry、readiness projection 和测试，不能只在前端页面里显示局部状态。canonical 直读页面的 domain readiness 只能依赖 PostgreSQL/runtime 健康，不得虚构页面 read model readiness。

domain registry 是页面域入口；`AppStatusReadModelRegistry` 是仍有 read model 的页面 readiness 事实入口。表中的 read model 必须能从 `read_model.app_status_readiness` 或等价 active generation readiness 读取到 `fresh/missing/refreshing/stale/failed/unavailable` 等状态。没有 readiness 记录时，该 read model 进入 `missing`，对应 domain 不能显示 ready。

| domain key | route | read model / worker / task 来源 |
| --- | --- | --- |
| `workbench` | `/` | `workbench`、`workbench_relation`、workbench workers、workbench matching/rebuild jobs |
| `imports_bank_transactions` | `/imports/bank-transactions` | import worker、银行流水导入任务 |
| `imports_invoices` | `/imports/invoices` | import worker、发票导入任务 |
| `imports_etc_invoices` | `/imports/etc-invoices` | import worker、ETC 发票导入任务 |
| `bank_details` | `/bank-details` | 页面运行时为单次 PostgreSQL repeatable-read canonical snapshot；旧 `bank_detail` / `bank_account_balance` registry/worker 仅作为共享清理 HANDOFF，不能决定页面 readiness |
| `pending_invoices` | `/pending-invoices` | `pending_invoice`、`search`、`pending-invoice` / `search` workers，旧 `search-pending` 兼容 worker |
| `oa_pending_payments` | `/oa-pending-payments` | 页面直接读取 canonical PostgreSQL；全局 `oa_pending_payment` legacy readiness/worker 暂留给共享消费者，待统一 cleanup，不参与页面正确性 |
| `input_invoice_usage` | `/input-invoice-usage` | PostgreSQL canonical repeatable-read snapshot；active `app.workbench_pair_relations`；无页面 read model/worker |
| `output_invoice_collections` | `/output-invoice-collections` | PostgreSQL canonical repeatable-read snapshot；active `app.workbench_pair_relations` 与 canonical lifecycle facts；无页面 read model/worker |
| `tax_offset` | `/tax-offset` | 单次 PostgreSQL repeatable-read canonical snapshot；页面无 Tax Offset read model/worker 依赖 |
| `cost_statistics` | `/cost-statistics` | 单次 PostgreSQL repeatable-read canonical snapshot；无 Cost read model/worker |
| `bank_flow_rule_batches` | `/bank-flow-rule-batches` | 单次 PostgreSQL repeatable-read canonical snapshot；无页面 read model/worker |
| `batch_accounting` | `/batch-accounting` | workbench relation read model |
| `turnover_ledger` | `/turnover-ledger` | 单次 PostgreSQL repeatable-read canonical snapshot；无 Turnover read model/worker |
| `etc_tickets` | `/etc-tickets` | ETC import jobs、ETC business batch manual OA status |
| `settings` | `/settings` | OA identity/state store/settings refresh runtime dependencies |
| `app_health_operations` | `/operations/app-health` | runtime health dependencies、workers、queue、state store |

`batch_accounting` 页面依赖 Workbench active payload 和 `workbench_relation` read model 判定已提交/未提交。`GET /api/batch-accounting` 必须透出 relation read model 的 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys` 和 `refresh_enqueued`；页面不能在 relation read model 非 fresh 时把空关系结果当作真实“全部未提交”。未提交 bucket 的 relation lookup 输入必须先收窄到批量账务银行候选和日常报销 OA 候选，`summary.submitted_count` 只能走年份级 count I/O；已提交 bucket 才读取完整 submitted relation DTO。

`bank_flow_rule_batches` 列表只通过 bank-flow 专属 canonical query repository 读取当前页和完整筛选范围聚合，默认 page size 50，不能先加载全部批次再由前端或 application 分页。标签规则、total、page rows 和 summary 位于同一显式 `REPEATABLE READ / READ ONLY` snapshot；正式关系只读取 `app.workbench_pair_relations.status='active'`。未提交 rail 和批次只接纳 active 且 OA/发票双 false 的标签；submitted/history rail 使用冻结历史。详情按成员 ID 一次集合读取 canonical 银行流水、当前分类、active relation aggregates 和 batch events。规则保存、submit/withdraw/reset 以 command 原子提交为前台完成边界，每次成功后当前页面执行一次 normal GET；没有 read-model status、refresh enqueue、202 reconcile 或后台 polling。

## 页面职责边界

- 页面可以决定筛选、排序、分页、空状态、导出列、drawer/dialog 状态。
- 页面写操作可以接入 `GlobalOperationOverlayProvider`，在 operation 完成前显示全屏阻塞层，防止用户在同一事实链路尚未收敛时继续操作。overlay 只包裹会改变后端事实或跨页面 read model 的操作；普通页面初始读取、筛选、分页、详情打开不使用全屏阻塞。
- 页面切换时 `PageRouteHost` 只挂载当前匹配 route；离开页面会卸载页面 React tree，不保留隐藏 DOM frame、mounted cache、TTL/LRU 策略或页面数据 snapshot。返回页面时页面重新 mount，并通过现有 API/read boundary 重新加载数据。
- 页面注册表不声明保活策略；`AppPageRoute` 只维护 `path`、`pageKey`、`component`、`preload()` 和 `end`。侧栏分组继续从页面注册表派生，不能在侧栏里维护第二份路由事实。
- `PageRuntimeContext` 仅为当前挂载页面提供稳定的 `pageKey/active` 上下文；它不监听浏览器生命周期，不携带业务 DTO，也不协调跨页刷新。
- 页面入口使用 lazy route chunks；`AppPageRoute.preload()` 和 `SidebarItem.preload()` 是 route chunk 预加载入口。侧边栏可以在 hover/focus/touch start 时预加载目标页，但点击导航仍由 React Router `Link` 负责。
- 页面会话状态只保存当前浏览器标签页内的轻量可恢复 UI，例如查询、筛选、分页、排序、tab、选中行、展开行和详情 drawer target；不保存滚动位置、列表 rows、read model payload、loading、一次性 toast、失败中的提交、权限事实或业务事实。
- 财务表格继续使用 `FinanceTable` 和 `useFinanceTableSession` 保存分页、排序、过滤、列和选择状态。表格滚动位置不写入页面 session，返回页面后由浏览器和组件默认布局决定。
- 页面不能重新定义发票生命周期、银行标签、对象 identity/dedup、项目成本归因、往来状态分类等业务口径。
- 多页面共享且需要 freshness/backfill 的结果，必须通过 policy/service + read boundary 暴露。
- 只有一个页面使用且规则简单的派生结果，可以留在页面 service；后续被复用时再上提。

### Phase 27 页面访问 freshness 迁移（本地已实施，待生产验证）

当前 route 生命周期已经提供目标方案需要的最小机制：离开页面会卸载页面 React tree，返回时重新 mount；`PageRuntimeContext` 提供当前页面 `active` 状态。Phase 27 不增加 keep-alive frame、全局页面 coordinator、第二套依赖 registry 或后台隐藏页面轮询。

| 场景 | 旧生产事实 | Phase 27 当前合同 |
| --- | --- | --- |
| 在页面 A 普通确认/撤回 | 部分链路写后 fan-out 多个 read model，并由页面 barrier 等待跨页 target | canonical commit 后只 reconcile A 当前 exact scope；页面 B 不成为 A 的同步依赖 |
| 从 A 导航到 B，再返回 A | 路由切换会卸载旧页，返回时重新 mount | route mount 触发正常 query；fresh gate 比较 source/schema/rule versions，只有 mismatch 才 enqueue/rebuild exact scope |
| 浏览器 focus、hidden→visible 或 BFCache 恢复 | 旧实现会把浏览器生命周期当成业务刷新信号 | 当前实现不发业务页面 I/O；用户手动刷新浏览器或重新进入 route 后才重新执行页面 load |
| 两个独立 browser tab 同时打开 | 两页互不共享 freshness 事实 | A 的写入不自动刷新 B；B 的下一次 route 进入/查询变化/手动刷新走后端 fresh gate |
| Drawer 规则保存 | 当前部分 Drawer 文案和实现仍是“保存并同步/刷新”并等待 projection | 保存 rule version/signature 后立即完成；当前页面按 query-time 规则或 exact scope reconcile，其他消费者访问时判断语义 mismatch |
| 导入、reapply、reset、repair | 本来就是可能大批量的 durable/background workflow | 继续作为 `explicit-batch`，3 秒约束 accept/commit，不承诺 3 秒全历史重建；进度、失败、恢复必须可见 |
| 外部往来款访问/刷新 | 历史上依赖 `turnover_ledger` projection、source version、worker 和 queue | 当前直接在一个只读 repeatable-read PostgreSQL snapshot 中组合 canonical facts；没有 Turnover read model/status/enqueue。关联台和外部往来款各自在访问时读取同一 canonical pair relation |

并非每个页面都有独立 read model，也并非每个 Drawer 保存都需要 rebuild。设置、ETC workflow、导入 session 等页面可以直接读取 canonical/config/job state；read-only Drawer 和 export/preview 不得制造 dirty scope。完整的 17 页面、110 个 API 函数、22 个业务 Drawer、15 个 read model 和旧调用点清单由 `.planning/phases/27-read-model-fan-out/27-COVERAGE-MATRIX.md` 与静态测试维护。

发布验收时要同时区分：

- 本地实现态：全部已盘点普通 `fact-write` / `rule-write` 不做跨页 fan-out；目标页面访问时 exact-scope freshness 收敛。
- 生产态：只有 Phase 27 全量门禁、部署和逐页逐操作 production smoke 通过后才能声明已生效；发布前生产仍按线上版本解释。
- 例外：`read-like-command` 永不 invalidation；`explicit-batch` 保留 durable job；Workbench 保留 active-generation 原子发布。

“重新计算页面数据”不等于每次访问无条件重建。仍保留 read model 的页面先做廉价 freshness/version check，只有不一致才重建当前 exact scope。外部往来款是明确例外：其业务组合足够有界，直接读取 canonical snapshot，彻底删除页面 projection/version/worker 链，不能把这一个页面的方案机械推广到其它页面。

## 前端刷新合同

- 普通写入不发送 finance domain event、window 自定义刷新事件或业务 `BroadcastChannel`。
- 当前页面可在命令成功后用自己的 normal GET 更新；其他页面不自动读取。
- route 进入/重进、页面查询变化、浏览器手动刷新和明确的页面重试是普通业务页面 load 入口。
- App Health、后台任务、导入/reapply/repair 进度与 Workbench refresh-status 属于运维/任务状态通道，保留各自明确 owner，不得被业务页面当成跨页刷新总线。

## 后端间接影响关系

跨页面的稳定影响必须通过后端生命周期表达：

- `DerivedDataLifecycleService` 负责把业务事件转换成 dirty scope、outbox 和 read model refresh 请求。
- `RuntimeQueueRepository.enqueue_read_model_refresh(...)` 是 read model refresh 的标准入队边界。
- `ReadModelQueryGateway` 负责 freshness/status/enqueue 判断，页面不能绕过它读取旧 projection 并显示为 fresh。
- `/api/operation-barrier/status` 只保留给显式返回非空 targets 的 maintenance/integration 操作；普通 mutation 不调用它。
- worker registry 定义哪些 read model 可被后台刷新、如何 drain、如何被 App Health 观测。

## 维护要求

新增页面或改页面事实来源时，更新本文件的页面分组和影响关系。新增 derived lifecycle 或任务进度事件时，同时检查 `runtime-and-ownership.md`、`docs/dev/api-contracts.md` 和相关产品文档是否需要更新。
