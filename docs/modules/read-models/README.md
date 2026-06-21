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
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_scope_contract.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_model_scope_contracts.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `web/src/features/operationBarrier/api.ts`
- `scripts/check-read-model-scope-contracts.py`

## 当前边界

所有 read model 查询必须走 freshness/status/enqueue 边界。read model refresh 入队前必须走统一 scope policy/gateway 做 normalize、validate 和 dedupe；`RuntimeQueueRepository` 继续只负责 PostgreSQL durable queue 持久化，不承载具体 read model 的业务 scope 规则。

read model 查询边界必须 fail-closed。调用 `ReadModelQueryGateway` 时必须传入 `expected_source_versions` 或 `expected_schema_version`；自管 freshness 的旧 query service 必须用等价的 expected source/schema contract。缺少 expected contract 属于代码配置错误，应直接失败；存在 expected schema/source 时，SQL view 或 Redis fresh gate 缺少实际 `schema_version` / `source_versions` 证明，必须返回 refreshing/stale reason 并通过 `ReadModelRefreshGateway` 入队，不能把旧 projection 标为 fresh。

生产 PostgreSQL runtime 下，页面 read model API 缺少 SQL read repository 或 SQL view 时必须返回 `read_model_status=refreshing` 并通过 `ReadModelRefreshGateway` 入队；不能回退到旧 `QueryService` / live scan / memory snapshot 来返回 `live_query` 或伪 fresh。legacy/local 模式可以保留旧 query service 作为开发兼容路径，但该路径不得在 `_requires_sql_read_model_runtime()` 为真时执行。

`read_model_scope_policy.py` 是 refresh scope 入口契约。除 `cost_statistics` 与 `pending_invoice` 的特殊 scope 外，主要页面 read model（`bank_detail`、`bank_account_balance`、`input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment`、`invoice_lifecycle`、`search`、`tax_offset`、`turnover_ledger`、`workbench`、`workbench_relation`、`no_oa_bank_batch`）接受 month 或 `all` scope，并在 gateway 阶段拒绝 `active:*` 等非本 read model 合约 scope。新增 read model 或变更 scope 形态时必须先更新 registry、worker manifest、tests 和本模块文档。

依赖 `workbench_relation` distribution 的页面 read model 还必须把当前 `read_model.workbench_relation_scopes.source_versions` 纳入 expected source versions。进项发票使用、销项发票收款、OA 待付款等页面即使自身 schema 版本未变，只要 relation scope 版本与 payload 保存时不一致，也必须返回 refreshing/stale 并入队对应页面 read model refresh，不能把旧 OA/流水/发票配对关系展示为空并标为 fresh。待找发票通过 pending invoice source versions 按当前筛选范围读取 `workbench_relation` scope versions，必须保持等价语义。

`all` scope 必须区分两种语义：refresh command 的 `all` 可以是 fan-out 控制 scope，只负责枚举并投递 month shards；页面查询的 `all` 必须有可验证的 freshness proof。fan-out-only refresh 结果不能写假 fresh readiness；相应 API/repository 必须把无界查询解析为实际月份 shard 的 source/readiness 证明，或显式发布一个真实可查询的 parent aggregate proof。不能让页面等待一个 worker 永远不会发布为 fresh 的 parent `all` scope，也不能在 stale parent `all` 上反复补投刷新。

对依赖 `workbench_relation` 的页面 read model，month scope 继续严格比对对应月份的 relation source versions；无界 `all` 查询不能直接拿全局 `workbench_relation:all` source versions 约束当前页面聚合，因为页面实际行集和月份 shard 可能只覆盖部分月份。`all` 查询的正确证明来自子月份 rows/scopes 与 active dirty/outbox 状态；若未来新增真正的全量 aggregate row，必须同时新增 parent aggregate source/version contract、worker readiness 和 API 回归测试。

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
