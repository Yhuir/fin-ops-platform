# Runtime Worker 模块维护入口


- Module key: `runtime-workers`
- 类型: 资源模块
- Route: `N/A`
- Page key: `N/A`

## 修改前必读

- `docs/operations/runtime-worker-governance.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/operations/postgresql-runtime.md`

## 代码入口

- `backend/src/fin_ops_platform/services/runtime_queue.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 当前边界

Worker 不得依赖 Application、app.server、app.auth 或 HTTP response。Worker lifecycle 触发 read model refresh 时必须通过统一 refresh gateway 入队，由 registry/policy 先完成 scope normalize、validate 和 dedupe，避免 worker 直接投递过期或非法 scope contract。

`settings-maintenance` 是 required、PostgreSQL-only 的非 read-model worker。它独占 `settings.data_reset.requested`，执行 destructive reset、显式 runtime recovery 和重置后的 read-model/matching enqueue；API 进程只创建 job/outbox，不运行后台 executor。重置完成后 worker 通过受控 Gunicorn PID file 请求 graceful reload，使 API 进程内 command/cache state 不继续保留 reset 前快照。

当前 registry 精确包含 6 个 required instance：`oa-sync`、`workbench-matching`、`workbench`、`workbench-relation`、`import`、`settings-maintenance`。其中只有 `workbench` 与 `workbench-relation` 带 `read_model_key`，并与 `READ_MODEL_MANIFEST` 双向一致。Search、no-OA projection 与 `workbench-secondary` 已从代码、CLI、env、dispatcher 和部署 manifest 退役。

同一 read model 的 parent/aggregate 依赖必须避免抢占真实 shard work。`*_read_model_not_fresh parent_scope_keys=...` 可以补投 same-scope parent shard；当前 event 必须使用 retry 级退避，让 `YYYY-MM` shard 或其他依赖先完成，不能用亚秒级 retry 反复重发 `all` 聚合事件。

当前 P2/P3 closure 的性能门禁是首屏 API 或 direct refresh p95 <= 1000ms；写操作 operation-to-fresh 还要求 p99 <= 3000ms。历史 5 秒 SLO 记录是旧基线，不是当前验收上限。Worker 优化必须保留 PostgreSQL durable queue、dirty scope、outbox 和 readiness 事实源，不得通过跳过 freshness 或缓存 stale payload 达标。

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
