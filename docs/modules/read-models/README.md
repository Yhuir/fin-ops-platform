# Read Model 模块维护入口


- Module key: `read-models`
- 类型: 资源模块
- Route: `N/A`
- Page key: `N/A`

## 修改前必读

- `docs/architecture/persistence-and-read-models.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/operations/runtime-worker-governance.md`

## 代码入口

- `backend/src/fin_ops_platform/services/read_model_query_gateway.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_scope_contract.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_model_scope_contracts.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `web/src/features/operationBarrier/api.ts`
- `scripts/check-read-model-scope-contracts.py`

## 当前闭环状态

- 状态：当前 runtime 合同已收敛并关闭；每次生产发布仍按 App Health、worker registry 和运维 runbook 验证实际实例、backlog、freshness 与页面读链，不以历史迁移阶段文字代替当前证据。
- 当前 registry/manifest 登记 `workbench` active-generation 页面 read model，以及 `workbench_relation`、`search`、`no_oa_bank_batch` 三个共享 projection。共享 projection 只服务各自独立消费者，不能作为 canonical 直读页面的运行时依赖。
- 关联台继续通过 freshness/status/enqueue、Redis fresh cache 和 Workbench worker 读取 active generation。银行明细、待找发票、进项发票使用、销项发票收款、OA 待付款、税金抵扣和流水规则批量处理直接读取 canonical PostgreSQL snapshot；成本统计、外部往来、批量账务与 ETC 也保持各自 canonical query 边界。
- BankFlow 未提交候选由页面请求内实时推导；没有 draft event、worker、readiness、dirty scope、manifest 或 replay。`app.bank_flow_rule_batches/events` 只保留正式状态和历史。
- migration `0127_direct_canonical_page_runtime_retirement.sql` 是纯 no-op 退休标记；旧 outbox、dirty scope、readiness 与历史物理 projection 表均不改写、不删除，完整保留上一版本回滚能力。deploy preflight 先停止/disable 退休 instance 并要求退休 runtime 不存在 `processing`；门禁通过后才停止仍登记的上一版本 worker。门禁失败不会中断 import/matching/保留 read-model worker。

## 当前边界

只有登记的 read model 查询才走 freshness/status/enqueue 边界。refresh 入队前必须通过统一 scope policy/gateway 做 normalize、validate 和 dedupe；`RuntimeQueueRepository` 只负责 durable queue 持久化。

`read_model_scope_policy.py`、`read_model_manifest.py`、`APP_STATUS_READ_MODEL_REGISTRY` 和 runtime worker registry 必须具有同一组 read-model key：`workbench`、`workbench_relation`、`search`、`no_oa_bank_batch`。Manifest 声明的 primary/auxiliary worker instances 必须与 runtime registry 中同 key 的全部实例双向相等；当前 `workbench` 对应 `workbench`、`workbench-secondary`。canonical 页面不得在任何一个 registry 中重新出现，也不得读取其历史 projection、readiness 或 dirty scope。

canonical 页面 GET 以一次 `REPEATABLE READ / READ ONLY` snapshot 为读取边界，直接返回业务 payload；不返回页面 `read_model_status`，不因 GET enqueue，写后只重新执行当前页面 normal GET。缺少 canonical repository 是配置错误，必须 fail fast，不能回退到历史 projection。

共享 `workbench_relation` 可以继续服务仍需 distribution 的独立消费者，但页面是否保留它只由实际消费者决定。Search 和 no-OA 保持各自现有合同；ETC 没有独立页面 read model，Workbench matching 仍是 canonical relation 生产任务而不是页面 projection。

## 模块 IO 合同

本模块的 IO 合同覆盖当前四个 App Status read model；具体页面的业务字段、筛选、导出和 UI copy 仍由对应 `docs/modules/<page>/` 维护。

### 输入合同

| 输入 | 允许来源 | 合同 owner | 校验要求 |
| --- | --- | --- | --- |
| Query 读取 | 页面 API、service facade、SLO probe | `ReadModelQueryGateway` 或登记过的自管 freshness service | 必须声明 expected schema/source contract；缺少证明时 fail closed，不返回 fresh。 |
| Refresh request | 页面 API miss/stale、显式 import/reapply/repair、worker dependency/parent、runbook/force refresh | `ReadModelRefreshGateway` + `ReadModelScopePolicyRegistry` | normalize、validate、dedupe 后才能进入 durable queue；非法 scope 在 enqueue 前拒绝。普通 canonical write 不经过此入口。 |
| Transactional refresh | 仅显式 import/reapply/batch 或当前业务合同明确要求的 writer | 对应业务 service/repository UoW | 必须承担与 gateway 等价的 scope contract，并与 canonical write 同事务提交；不得把普通页面 mutation 重新接回 fan-out。 |
| Operation barrier target | 显式 job/import/reapply 返回的 freshness targets | `OperationFreshnessBarrierService` | 只读取 current-effective readiness、dirty scope、outbox 和 worker facts；不写 readiness、不重建投影。普通页面 mutation 的 target 必须为空。 |
| Force refresh | 运维 runbook、受控 API、SLO/smoke 工具 | gateway/runbook 边界 | 必须有权限、scope validation、dedupe/idempotency、readiness proof 和审计；页面按钮不得随意触发刷新所有。 |

### 输出合同

| 输出 | 必需字段 / 证明 | 禁止行为 |
| --- | --- | --- |
| 共享 read model API payload | `read_model_status` 或等价 freshness 语义、`read_model_scope_keys`、stale/missing reason、`refresh_enqueued`、schema/source proof | 把 missing/stale/failed payload 标为 fresh；把该合同套到 canonical 页面。 |
| Write API result | 普通 canonical mutation（含 import confirm）返回业务 receipt/version 和信息性 affected scopes/months，freshness/barrier targets 为空；显式 reapply/repair/reset/force-refresh job 可返回 owner 声明的 exact targets | 普通写后制造跨页面 target/fan-out；或前端把轻量事件当作 fresh 证明。 |
| Dirty scope / outbox | `read_model_key`、规范 `scope_type/scope_key`、reason、priority、metadata/action name、dedupe contract | 业务 service 直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。 |
| Readiness | 当前 schema/source proof、current-effective status、worker/error 诊断 | Redis/RabbitMQ 作为状态事实源；fan-out-only `all` 写假 parent fresh proof。 |
| Cache | 只缓存 fresh gate 后、且通过 payload validator 的 payload | Redis cache 命中绕过 fresh gate 或 payload contract。 |

### 事件合同

| 事件类型 | Producer | Consumer | 合同 |
| --- | --- | --- | --- |
| Domain/derived lifecycle event | 业务 writer、import/OA sync、settings/data reset | Derived lifecycle service / module refresh producer | 先由模块 producer 归一化 scope，再进入 gateway；metadata 可用于 SLO/audit，不替代权限或业务事实。 |
| Dirty scope | query miss/stale gateway、显式 job writer、worker dependency/parent | Runtime worker / App Status / operation barrier | PostgreSQL durable queue 是事实源；同 scope active refresh 可合并，`refresh_enqueued=false` 不等于 fresh。普通 canonical write不产生该事件。 |
| Outbox event | gateway、事务内等价 writer | `RuntimeWorkerRegistry` 对应 worker | event type 必须登记于 manifest、worker registry、RabbitMQ dispatch 和 scope policy。 |
| Frontend domain event | 页面 mutation success 后的刷新提示 | 同浏览器页面 | 只提示 refetch，不证明 worker done 或 read model fresh。 |

### 权限与审计合同

- route 可以读取 HTTP/session 并映射 actor、tenant、permission；service 只能接收 actor/permission 结果，不能直接读取 HTTP header/cookie 或 import `app.auth`。
- read model 查询权限由业务 API/session owner 负责，例如 `bank_details_api_session`、`pending_invoices_api_session`、`search_api_session`；本模块只要求 query path 不绕过业务 API。
- force refresh、runtime repair、scope cleanup 和 production smoke 必须通过 runbook 或受控工具执行，并记录 scope、reason、actor/approver、audit/rollback manifest；不得记录 secrets、tokens、原始敏感 payload。

### Public surface

允许其它模块调用：

- `ReadModelQueryGateway`：统一 fresh gate、cache gate 和 miss/stale enqueue。
- `ReadModelRefreshGateway`：非事务 refresh 的唯一 enqueue 边界。
- `ReadModelScopePolicyRegistry` / scope contract helpers：scope normalize/validate/dedupe 合同。
- `OperationFreshnessBarrierService`：页面访问发现 non-fresh 后，或显式 import/reapply/repair job 的精确可见性等待目标；普通写命令不使用。
- `READ_MODEL_MANIFEST`：manifest/registry/test owner 合同清单。
- 每个 read model 自己登记的 query facade、repository port、refresh producer、derived lifecycle executor 和 worker handler。

### Internal-only surface

禁止其它模块直接调用：

- `RuntimeQueueRepository.enqueue_read_model_refresh(...)`，除非该调用点已登记为 gateway-backed wrapper 或事务内等价 writer。
- `job.outbox_events`、`job.read_model_dirty_scopes`、`read_model.app_status_readiness` 的裸 SQL 写入。
- `PostgresReadModelRepository` 中未被 manifest 归属的跨模块方法。
- 旧 `Application` read/cache/rebuild helper、local snapshot/live scan fallback、legacy route helper 来决定生产 fresh 结果。
- Redis cache payload、RabbitMQ message、前端 domain event 作为 freshness 或业务事实源。

### Legacy 隔离状态

| Legacy path | 当前状态 | 保留条件 | 禁止行为 | 测试证明 |
| --- | --- | --- | --- | --- |
| 已退休页面历史 projection 代码/物理表 | `rollback-only` | 只供上一版本回滚；0127 不删表 | 在当前 registry、worker、RabbitMQ、App Status、scope policy 或页面 GET 中重新接线 | `tests/test_runtime_worker_registry.py`、`tests/test_read_model_manifest.py`、`tests/test_postgres_migrations.py` |
| Workbench/Search/no-OA/workbench relation worker lanes | `active` | 只服务各自登记消费者 | 被无关 canonical 页面用作 freshness/readiness 依赖 | `tests/test_runtime_worker_registry.py`、`tests/test_read_model_manifest.py` |
| fan-out-only `all` scope | `quarantined semantics` | 只作为 refresh command 或明确 aggregate rebuild target | 发布不可查询 parent fresh proof；页面等待永不发布的 parent | `tests/test_read_model_manifest.py`、scope/gateway/query runtime tests |
| broad shared SQL repository | `transition owner` | SQL/table knowledge 过渡期集中；公共方法必须有单一 manifest owner | 新增未登记跨模块方法或让业务 service 依赖 broad repository surface | `tests/test_read_model_manifest.py`、repository port isolation tests |

### Partitioned scoped incremental 目标

该目标适用于三个保留的共享 projection；Workbench 使用独立 active-generation scoped publish。已退休页面不再以 scoped projection 为目标，也不应因历史优化目标重新引入页面 worker。

Scoped incremental projection 可以在当前 SQL view 已 fresh 且 `source_versions` 与本次计算出的 source contract 完全一致时返回 `skipped/source_versions_unchanged`，但这只是 worker 性能优化，不是 freshness 证明替代品。缺少 fresh SQL view、dirty/outbox 仍 active、source_versions 缺失或不一致时，必须重建或返回 refreshing/stale；不能把 volatile queue event `source_version` 当成业务内容变化，也不能过滤掉真正代表内容变化的 schema/rule/signature 字段。

## Read model 合同清单

下表是当前四个 App Status read model 的合同索引，内容与 `READ_MODEL_MANIFEST` 保持一致，并由 `tests/test_read_model_manifest.py` 防漂移。

| read_model_key | scope_type | 分区 key | 增量目标 | full rebuild fallback | freshness proof | force refresh / operation barrier |
| --- | --- | --- | --- | --- | --- | --- |
| `workbench` | `workbench` | month_scope active generation; all aggregates active month shards | workbench active generation rows, groups, summaries and details for affected month scopes | gateway force refresh rebuilds requested active month generation or all aggregate from canonical facts | active generation metadata, expected relation/rule and scoped canonical object source_versions, active pending claim version, and current-effective dirty/outbox state | `gateway_force_refresh_active_generation_scope` / `app_status_registry_target` |
| `workbench_relation` | `workbench_relation` | relation month_scope; all is fan-out only | workbench relation distribution rows and groups for affected month scopes | gateway force refresh fan-out rebuilds relation month shards and marks empty scopes | workbench_relation scope source_versions plus app_status readiness and current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `search` | `search` | search source month_scope; all is fan-out only | search index rows for affected month scopes | gateway force refresh all enumerates search month shards through the search refresh producer | search index source_versions plus current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `no_oa_bank_batch` | `no_oa_bank_batch` | legacy no-OA bank batch month_scope; all is fan-out only | legacy no-OA bank batch public rows for affected month scopes | gateway force refresh all enumerates no-OA month shards through the refresh producer | no-OA source_versions plus app_status readiness and current-effective dirty/outbox state; non-critical production page SLO | `gateway_force_refresh` / `app_status_registry_target` |

以下段落只保留为 0127 之前的历史设计说明，不是当前 runtime 合同：

依赖 `workbench_relation` distribution 的页面 read model 必须声明自己的消费语义。进项发票使用和销项发票收款按请求月份先收集本方向 canonical invoice IDs，再只统计与这些 IDs 相交的 active canonical relation，形成 consumer-semantic relation proof；无关 bank-bank、另一发票方向或同月其它关系不得令本页 stale。真正需要重建时，worker 仍要求关系 distribution fresh 后才发布页面投影。OA 待付款在 projector 中直接读取 canonical relation，不等待 `workbench_relation` read model；Workbench 写事务同样不投递 OA，OA freshness 比较自己的 source snapshot、pending/canonical relation、dirty/outbox 和 event version。待找发票通过 pending invoice source versions 按当前筛选范围读取关系 proof，必须保持等价语义。

`all` scope 必须区分两种语义：refresh command 的 `all` 可以是 fan-out 控制 scope，只负责枚举并投递 month shards；页面查询的 `all` 必须有可验证的 freshness proof。fan-out-only refresh 结果不能写假 fresh readiness；相应 API/repository 必须把无界查询解析为实际月份 shard 的 source/readiness 证明，或显式发布一个真实可查询的 parent aggregate proof。不能让页面等待一个 worker 永远不会发布为 fresh 的 parent `all` scope，也不能在 stale parent `all` 上反复补投刷新。

对依赖关系事实的页面 read model，month scope 必须比对该 consumer 的 exact-month relation proof；无界 `all` 查询不能直接拿全局 `workbench_relation:all` source versions 约束当前页面聚合，因为页面实际行集和月份 shard 可能只覆盖部分月份。`all` 查询的正确证明来自子月份 rows/scopes 与 active dirty/outbox 状态；若未来新增真正的全量 aggregate row，必须同时新增 parent aggregate source/version contract、worker readiness 和 API 回归测试。

fan-out-only `all` refresh 还必须维护子 scope 集合的收敛：worker 发现当前有效 month shards 后，应清理不再属于当前事实源的旧 month rows/scopes，或用等价机制把旧 scope 从页面 `all` freshness proof 中移除。否则旧 scope 的 source versions 会继续参与无界查询聚合，导致缺失/过期版本反复触发 refreshing。

普通写操作后的用户体验闭环由当前页面 normal GET 负责：HTTP command 成功即结束写阻塞；当前页面重新执行自己的 canonical query，其他页面/tab 不自动 GET。route 进入/重进、页面查询变化、浏览器手动刷新或明确重试才启动新的页面 load；focus/visibility/BFCache/旧业务事件零业务 I/O。页面 GET 只有 loading/empty/error/result，不返回页面 read-model freshness 或 enqueue 状态。

`/api/operation-barrier/status` 只保留给显式 import/reapply/job 或 manifest 声明的 exact target；不得用于普通 canonical 页面确认、撤回或规则保存。Workbench 使用自身 freshness/write gate。

当前运行时 manifest、scope policy、App Status registry 和 worker registry 必须精确等于 `workbench`、`workbench_relation`、`search`、`no_oa_bank_batch`。自动 matching 直接写 canonical active relations；Workbench refresh 由自己的 dirty scope/worker 收敛，只有仍消费共享 relation distribution 的独立下游刷新 `workbench_relation`。

生产旧 runtime 状态通过 `scripts/check-read-model-scope-contracts.py` 检查和修复。默认只读检查 `job.read_model_dirty_scopes`、`job.outbox_events` 与 `read_model.app_status_readiness` 中不符合当前四个 registry key 的行并生成 repair manifest；`--apply` 只删除 policy 明确判定 invalid 的旧行，不补投已退役页面 refresh。当前未覆盖 failure 必须保留为真实 blocker，不能为了 App Status 变绿而删除。

## 维护触发器

- `turnover-ledger` 已迁出本模块：页面 direct canonical read，不允许把历史 `read_model.turnover_ledger_*` 表重新登记为 runtime projection。历史表后续删除必须单独走 migration，不得与页面读链并行恢复。

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
