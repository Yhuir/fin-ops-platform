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

- 状态：Read Model 模块化 PSCIP-L4 closed；full external PSCIP-L4 / 高性能全域闭环 open。
- 适用范围：当前登记 15 个 App Status read model；当前页面 critical SLO 覆盖其中 14 个，`no_oa_bank_batch` 仅作为 legacy API/read-model 回归项保留，当前流水规则批量处理页面使用 `bank_flow_rule_batch`。
- 最终证据：`.planning/refactors/modular-io-boundaries/analysis/read-model-main-final-closure-report-2026-06-28.md`。
- 生产证据：`.planning/refactors/modular-io-boundaries/analysis/read-model-main-production-evidence-2026-06-28.md`。
- 远端闭环提交：`c771b894 docs: close read model production evidence`。
- 结论：生产 scope contract、dirty/outbox/readiness、worker freshness 和 critical read model SLO 已按分层生产目标闭环；当前没有已知 stale-as-fresh 路径。
- 高性能状态：2026-07-03 release `pscip-l4-workbench-group-row-min-20260703` 后，Workbench warmed targeted 1s direct SLO `10/10` pass，`source_version 3124..3133` p95/max `890.808ms`；成本统计 `active:2026-02` targeted `5/5` pass，p95/max `938.124ms`。但 full critical grouped 1s smoke 仍未闭环，最新一轮为 `15/16` pass，`search:2026-03` handler `3087.035ms` / enqueue `3399.122ms` fail；targeted search `4/5` pass 但仍有一次 `1425.676ms` handler 长尾。因此 full external PSCIP-L4 / “所有页面耗时短”仍 open，不得描述为只剩形式化生产验证。
- 写操作测试输入：标准 scenario 路径和 standing approval ticket 已在部署 env、`write_operation_scenario_discovery.standard_inputs`、生成的 scenario JSON 和 `docs/operations/monitoring.md` 页面矩阵中固化；主控 workflow 后续不得为标准 production smoke 反复询问 scenario/ticket。
- 非阻塞风险：Search 曾出现一次 grouped-run 高延迟样本，targeted rerun 通过；Workbench groups admin smoke 的 `400` 是 probe shape 问题，不是 read model freshness 失败。

## 当前边界

所有 read model 查询必须走 freshness/status/enqueue 边界。read model refresh 入队前必须走统一 scope policy/gateway 做 normalize、validate 和 dedupe；`RuntimeQueueRepository` 继续只负责 PostgreSQL durable queue 持久化，不承载具体 read model 的业务 scope 规则。

read model 查询边界必须 fail-closed。调用 `ReadModelQueryGateway` 时必须传入 `expected_source_versions` 或 `expected_schema_version`；自管 freshness 的旧 query service 必须用等价的 expected source/schema contract。缺少 expected contract 属于代码配置错误，应直接失败；存在 expected schema/source 时，SQL view 或 Redis fresh gate 缺少实际 `schema_version` / `source_versions` 证明，必须返回 refreshing/stale reason 并通过 `ReadModelRefreshGateway` 入队，不能把旧 projection 标为 fresh。

生产 PostgreSQL runtime 下，页面 read model API 缺少 SQL read repository 或 SQL view 时必须返回 `read_model_status=refreshing` 并通过 `ReadModelRefreshGateway` 入队；不能回退到旧 `QueryService` / live scan / memory snapshot 来返回 `live_query` 或伪 fresh。legacy/local 模式可以保留旧 query service 作为开发兼容路径，但该路径不得在 `_requires_sql_read_model_runtime()` 为真时执行。

`read_model_scope_policy.py` 是 refresh scope 入口契约。除 `cost_statistics` 与 `pending_invoice` 的特殊 scope 外，主要页面 read model（`bank_detail`、`bank_account_balance`、`bank_flow_rule_batch`、`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`invoice_lifecycle`、`search`、`tax_offset`、`turnover_ledger`、`workbench`、`workbench_relation`）接受 month 或 `all` scope，并在 gateway 阶段拒绝 `active:*` 等非本 read model 合约 scope。`no_oa_bank_batch` 仍接受 legacy month/all scope，但默认生产页面 SLO 和 critical read model smoke 不再把它当作当前页面目标。新增 read model 或变更 scope 形态时必须先更新 registry、worker manifest、tests 和本模块文档。

`read_model_manifest.py` 是 14 个 App Status read model 的共享合同清单。它不替代具体 query service、repository 或 worker 实现，但必须与 `APP_STATUS_READ_MODEL_REGISTRY`、`runtime_worker_registry.py`、RabbitMQ dispatch events 和 `ReadModelScopePolicyRegistry` 保持一致。manifest 还登记每个 read model 的 force refresh 合同和 operation barrier target 合同：受控强制刷新必须通过 gateway/runbook/smoke 入口，写后可见性必须通过 App Status runtime snapshot 目标推导，不能让页面或脚本绕过统一边界。新增 read model、变更 refresh event、变更 primary/auxiliary worker、变更 `all` scope 语义、变更 force refresh/barrier 合同或 query freshness 合同时，必须同步更新 manifest 和 `tests/test_read_model_manifest.py`。

`read_model_manifest.py` 同时登记每个 read model 当前占用的 `PostgresReadModelRepository` repository port contract。`postgres_repositories/read_models.py` 仍是过渡期共享 SQL owner，但每个公共 repository 方法必须有且只有一个 manifest owner；后续拆分只能按已登记 port 小步迁移，不能在共享 repository 中继续新增未登记的跨模块方法。

`cost_statistics` 的 manifest port 已收窄为 scoped freshness/page/view/transaction reads、Workbench source-version read 与 source-version conditional publish。它不再登记或实现全表 load、无条件 save，也不再进入 `PostgresStateStore` / 本地 broad state snapshot；该限制只作用于成本统计，不改变其他 read model 的 port 或兼容策略。

## 模块 IO 合同

本模块的 IO 合同覆盖所有 App Status read model 的共享边界；具体页面的业务字段、筛选、导出和 UI copy 仍由对应 `docs/modules/<page>/` 维护。

### 输入合同

| 输入 | 允许来源 | 合同 owner | 校验要求 |
| --- | --- | --- | --- |
| Query 读取 | 页面 API、service facade、SLO probe | `ReadModelQueryGateway` 或登记过的自管 freshness service | 必须声明 expected schema/source contract；缺少证明时 fail closed，不返回 fresh。 |
| Refresh request | API miss/stale、derived lifecycle、worker fan-out、runbook/force refresh | `ReadModelRefreshGateway` + `ReadModelScopePolicyRegistry` | normalize、validate、dedupe 后才能进入 durable queue；非法 scope 在 enqueue 前拒绝。 |
| Transactional refresh | 同事务业务 writer | 对应业务 service/repository UoW | 必须承担与 gateway 等价的 scope contract，并与 canonical write 同事务提交。 |
| Operation barrier target | 写 API 返回的 affected scopes / freshness targets | `OperationFreshnessBarrierService` | 只读取 current-effective readiness、dirty scope、outbox 和 worker facts；不写 readiness、不重建投影。 |
| Force refresh | 运维 runbook、受控 API、SLO/smoke 工具 | gateway/runbook 边界 | 必须有权限、scope validation、dedupe/idempotency、readiness proof 和审计；页面按钮不得随意触发刷新所有。 |

### 输出合同

| 输出 | 必需字段 / 证明 | 禁止行为 |
| --- | --- | --- |
| API payload | `read_model_status` 或等价 freshness 语义、`read_model_scope_keys`、stale/missing reason、`refresh_enqueued`、schema/source proof | 把 missing/stale/failed payload 标为 fresh；把 fresh 空态用于非 fresh rows。 |
| Write API result | 对跨页面一致性有影响时返回 affected scopes/months、version/job 或 operation barrier target；不适用时必须明确由业务模块说明 | 只返回成功但不给前端等待目标，导致页面自行猜测同步完成。 |
| Dirty scope / outbox | `read_model_key`、规范 `scope_type/scope_key`、reason、priority、metadata/action name、dedupe contract | 业务 service 直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。 |
| Readiness | 当前 schema/source proof、current-effective status、worker/error 诊断 | Redis/RabbitMQ 作为状态事实源；fan-out-only `all` 写假 parent fresh proof。 |
| Cache | 只缓存 fresh gate 后、且通过 payload validator 的 payload | Redis cache 命中绕过 fresh gate 或 payload contract。 |

### 事件合同

| 事件类型 | Producer | Consumer | 合同 |
| --- | --- | --- | --- |
| Domain/derived lifecycle event | 业务 writer、import/OA sync、settings/data reset | Derived lifecycle service / module refresh producer | 先由模块 producer 归一化 scope，再进入 gateway；metadata 可用于 SLO/audit，不替代权限或业务事实。 |
| Dirty scope | gateway、事务内等价 writer | Runtime worker / App Status / operation barrier | PostgreSQL durable queue 是事实源；同 scope active refresh 可合并，`refresh_enqueued=false` 不等于 fresh。 |
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
- `OperationFreshnessBarrierService`：写后可见性等待目标。
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
| legacy/local query service fallback | `compat-only` | 仅 legacy/local runtime；生产 `_requires_sql_read_model_runtime()` 为真时必须 fail closed | 生产缺 SQL repository/view 时 live scan 并返回 fresh | `tests/test_read_model_architecture_guards.py`、各页面 SQL runtime fail-closed tests |
| combined worker lanes，例如 `search-pending`、`cost-tax` | `compat-only` | 兼容旧部署/并发 lane；primary worker 已登记于 manifest | 成为新的唯一 owner 或绕过 manifest/registry | `tests/test_runtime_worker_registry.py`、`tests/test_read_model_manifest.py` |
| fan-out-only `all` scope | `quarantined semantics` | 只作为 refresh command 或明确 aggregate rebuild target | 发布不可查询 parent fresh proof；页面等待永不发布的 parent | `tests/test_read_model_manifest.py`、scope/gateway/query runtime tests |
| broad shared SQL repository | `transition owner` | SQL/table knowledge 过渡期集中；公共方法必须有单一 manifest owner | 新增未登记跨模块方法或让业务 service 依赖 broad repository surface | `tests/test_read_model_manifest.py`、repository port isolation tests |

### Partitioned scoped incremental 目标

目标态是 partitioned scoped read model + scoped incremental projection。`workbench` 例外保留 active generation 原子发布；`bank_account_balance` 当前是 all-only projection；`pending_invoice` 拒绝裸 `all`，用 page-first-screen explicit scopes；`cost_statistics` 有 active/all shard 与 parent aggregate scope。所有其它 fan-out `all` scope 都必须展开到真实 month shard 或明确 parent aggregate 后才能证明页面查询 fresh。

Scoped incremental projection 可以在当前 SQL view 已 fresh 且 `source_versions` 与本次计算出的 source contract 完全一致时返回 `skipped/source_versions_unchanged`，但这只是 worker 性能优化，不是 freshness 证明替代品。缺少 fresh SQL view、dirty/outbox 仍 active、source_versions 缺失或不一致时，必须重建或返回 refreshing/stale；不能把 volatile queue event `source_version` 当成业务内容变化，也不能过滤掉真正代表内容变化的 schema/rule/signature 字段。

## Read model 合同清单

下表是当前 15 个 App Status read model 的共享合同索引，内容与 `READ_MODEL_MANIFEST` 保持一致，并由 `tests/test_read_model_manifest.py` 防漂移。页面模块可以继续维护自己的业务状态和 UI 细节，但新增或修改 read model 时必须先在这里和 manifest 中记录 `read_model_key`、`scope_type`、分区 key、scoped incremental target、full rebuild fallback、freshness proof、force refresh 合同与 operation barrier 合同。

| read_model_key | scope_type | 分区 key | 增量目标 | full rebuild fallback | freshness proof | force refresh / operation barrier |
| --- | --- | --- | --- | --- | --- | --- |
| `workbench` | `workbench` | month_scope active generation; all aggregates active month shards | workbench active generation rows, groups, summaries and details for affected month scopes | gateway force refresh rebuilds requested active month generation or all aggregate from canonical facts | active generation metadata, expected source_versions including matching rules, and current-effective dirty/outbox state | `gateway_force_refresh_active_generation_scope` / `app_status_registry_target` |
| `workbench_relation` | `workbench_relation` | relation month_scope; all is fan-out only | workbench relation distribution rows and groups for affected month scopes | gateway force refresh fan-out rebuilds relation month shards and marks empty scopes | workbench_relation scope source_versions plus app_status readiness and current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `bank_detail` | `bank_detail` | bank transaction month_scope; all is fan-out only | bank detail transaction/tag/account rows for affected month scopes | gateway force refresh all enumerates available month shards and rebuilds each shard | month shard scope summary/source_versions plus current canonical category signature and current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `bank_account_balance` | `bank_account_balance` | global all scope only | bank account balance snapshot for all accounts | gateway force refresh rebuilds the all-only account balance projection | bank_account_balance:all scope summary plus current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `pending_invoice` | `pending_invoice` | direction:filter_group[:YYYY-MM] page scope | pending invoice rows and filter options for direction/filter/month page scopes | page-first-screen force refresh rebuilds explicit pending invoice page scopes; bare all remains rejected | pending invoice source summary plus bank_detail and workbench_relation source_versions for requested page scope | `gateway_force_refresh_with_page_first_screen_scope` / `app_status_registry_target` |
| `search` | `search` | search source month_scope; all is fan-out only | search index rows for affected month scopes | gateway force refresh all enumerates search month shards through the search refresh producer | search index source_versions plus current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `invoice_lifecycle` | `invoice_lifecycle` | invoice lifecycle month_scope; all is fan-out only | invoice lifecycle rows for affected invoice subject month scopes | gateway force refresh all enumerates invoice lifecycle month shards | invoice lifecycle scope source_versions plus current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `input_invoice_usage` | `input_invoice_usage` | input invoice usage month_scope; all is fan-out only | input invoice usage rows and relation detail rows for affected month scopes | gateway force refresh all fans out to current input invoice usage month shards and prunes obsolete shards | month shard source_versions including workbench_relation versions plus current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `output_invoice_collection` | `output_invoice_collection` | output invoice collection month_scope; all is fan-out only | output invoice collection rows, relation detail rows and lifecycle overlay data for affected month scopes | gateway force refresh all fans out to current output collection month shards and prunes obsolete shards | month shard source_versions including workbench_relation, lifecycle and receipt versions plus current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `oa_pending_payment` | `oa_pending_payment` | OA pending payment month_scope; all is fan-out only | OA pending payment rows and relation detail rows for affected month scopes | gateway force refresh all fans out to current OA pending payment month shards and prunes obsolete shards | month shard source_versions including OA source snapshot/admission/payment, pending relation, canonical relation schema and event source versions plus current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `cost_statistics` | `cost_statistics` | cost statistics active/all month scope plus queryable parent aggregate scope | cost statistics month shards and parent rollup summaries | gateway force refresh normalizes legacy all/month scopes into active/all month shards and parent rollup rebuild | ReadModelQueryGateway expected schema/source_versions plus app_status readiness for shard and parent scopes | `gateway_force_refresh` / `app_status_registry_target` |
| `tax_offset` | `tax_offset` | tax offset invoice month_scope; all is fan-out only | tax offset rows and summary payload for affected month scopes | gateway force refresh all enumerates tax offset month shards | ReadModelQueryGateway expected schema/source_versions plus current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `no_oa_bank_batch` | `no_oa_bank_batch` | legacy no-OA bank batch month_scope; all is fan-out only | legacy no-OA bank batch public rows for affected month scopes | gateway force refresh all enumerates no-OA month shards through the refresh producer | no-OA source_versions plus app_status readiness and current-effective dirty/outbox state; non-critical production page SLO | `gateway_force_refresh` / `app_status_registry_target` |
| `bank_flow_rule_batch` | `bank_flow_rule_batch` | bank-flow rule batch month_scope; all is fan-out only | bank-flow rule batch public rows for affected month scopes | gateway force refresh all enumerates bank-flow rule batch month shards through the refresh producer | bank_flow_rule_batch source_versions plus app_status readiness and current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |
| `turnover_ledger` | `turnover_ledger` | turnover ledger month_scope; all is fan-out only | turnover ledger grouped/list rows plus turnover_ledger_scopes row-count/statistics summary for affected month scopes and the all-page aggregate | gateway force refresh all enumerates turnover ledger month shards and supports explicit clear/rebuild | turnover_ledger_scopes generation/source_versions/statistics with module-global serialized CAS plus ReadModelQueryGateway expected versions, workbench_relation versions, and current-effective dirty/outbox state | `gateway_force_refresh` / `app_status_registry_target` |

依赖 `workbench_relation` distribution 的页面 read model 还必须把当前 `read_model.workbench_relation_scopes.source_versions` 纳入 expected source versions。进项发票使用、销项发票收款等实际 consumer只要 relation scope版本与 payload保存时不一致，就必须返回 refreshing/stale并入队对应页面 read model refresh。OA 待付款是明确例外：Workbench写事务直接投递 OA月份，OA projector读取 canonical relation，因此 OA freshness只比较自己的 dirty/outbox、source snapshot、pending relation和 event version，不得等待其它页面 read model。待找发票通过 pending invoice source versions按当前筛选范围读取 `workbench_relation` scope versions，必须保持等价语义。

`all` scope 必须区分两种语义：refresh command 的 `all` 可以是 fan-out 控制 scope，只负责枚举并投递 month shards；页面查询的 `all` 必须有可验证的 freshness proof。fan-out-only refresh 结果不能写假 fresh readiness；相应 API/repository 必须把无界查询解析为实际月份 shard 的 source/readiness 证明，或显式发布一个真实可查询的 parent aggregate proof。不能让页面等待一个 worker 永远不会发布为 fresh 的 parent `all` scope，也不能在 stale parent `all` 上反复补投刷新。

对依赖 `workbench_relation` 的页面 read model，month scope 继续严格比对对应月份的 relation source versions；无界 `all` 查询不能直接拿全局 `workbench_relation:all` source versions 约束当前页面聚合，因为页面实际行集和月份 shard 可能只覆盖部分月份。`all` 查询的正确证明来自子月份 rows/scopes 与 active dirty/outbox 状态；若未来新增真正的全量 aggregate row，必须同时新增 parent aggregate source/version contract、worker readiness 和 API 回归测试。

fan-out-only `all` refresh 还必须维护子 scope 集合的收敛：worker 发现当前有效 month shards 后，应清理不再属于当前事实源的旧 month rows/scopes，或用等价机制把旧 scope 从页面 `all` freshness proof 中移除。否则旧 scope 的 source versions 会继续参与无界查询聚合，导致缺失/过期版本反复触发 refreshing。

写操作后的用户体验闭环由 operation freshness barrier 负责。前端写操作成功后可以调用 `/api/operation-barrier/status` 轮询受影响 read model/scope；后端只读取 `RuntimeMonitoringRepository.app_status_runtime_snapshot()` 中的 current-effective readiness、dirty/outbox 和 worker facts，不写 readiness、不重建 read model、不把 RabbitMQ/Redis 当事实源。barrier 返回 `fresh` 才允许页面关闭全屏操作 overlay；`refreshing` 继续等待；`blocked` 必须暴露具体 read model/scope 和原因，不能伪装成已同步。

operation barrier 不替代各页面自己的 fresh gate。Workbench 仍以 active generation 原子发布为最终展示事实；但确认/撤回这类写 API 如果返回后端 `operation_projection`，该 projection 是写后真实状态，前端只需等待操作级 `workbench_relation` barrier fresh 即可释放 overlay 并应用 projection。`workbench` month shard、`workbench:all` 和跨页面下游 read model 必须继续后台追赶并最终 fresh，由 cross-page SLO/监控单独验收；没有 operation projection 的写动作仍要等待目标 read model/scope fresh 或页面 fresh reload 后释放。

Workbench SQL active generation 的 freshness 还必须覆盖自动匹配规则版本。`source_versions` 中缺少或落后 `workbench_matching_rules_version` 时，API 必须把 generation 判为 stale 并入队 `workbench` refresh；不能让旧规则产出的 open/paired 分组继续伪装 fresh。自动 reconciliation decision 的 upsert、stale expire 和 missing expire 是事务内 writer，必须同时入队 `workbench_relation` 和主 `workbench` month scope refresh，避免 relation read model 与 Workbench active generation 脱节。

生产旧 runtime 状态通过 `scripts/check-read-model-scope-contracts.py` 检查和修复。默认只读检查 `job.read_model_dirty_scopes`、`job.outbox_events` 与 `read_model.app_status_readiness` 中不符合当前 registry 的成本统计 scope，同时生成 repair manifest，区分 legacy/invalid cost statistics runtime 行、已被 later done/fresh readiness 覆盖的历史 outbox failure，以及仍然 current-effective 的未覆盖 failure。`--apply` 只会删除旧非规范 cost statistics runtime 行，并通过 gateway 补投规范 `cost_statistics` replacement scope；当前未覆盖 failure 必须保留为真实 blocker，不能为了 App Status 变绿而删除。apply 报告必须包含 cleanup、rollback 和 audit event 信息。

## 维护触发器

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
