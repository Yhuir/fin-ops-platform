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
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_scope_contract.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_model_scope_contracts.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `scripts/check-read-model-scope-contracts.py`

## 当前边界

所有 read model 查询必须走 freshness/status/enqueue 边界。read model refresh 入队前必须走统一 scope policy/gateway 做 normalize、validate 和 dedupe；`RuntimeQueueRepository` 继续只负责 PostgreSQL durable queue 持久化，不承载具体 read model 的业务 scope 规则。

生产旧 runtime 状态通过 `scripts/check-read-model-scope-contracts.py` 检查和修复。默认只读检查 `job.read_model_dirty_scopes`、`job.outbox_events` 与 `read_model.app_status_readiness` 中不符合当前 registry 的成本统计 scope；`--apply` 会删除旧非规范行，并通过 gateway 补投规范 `cost_statistics` replacement scope。

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
