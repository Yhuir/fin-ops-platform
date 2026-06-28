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

页面 read model worker 是 legacy 下线对象。新增 worker 只允许用于导入、OA 同步、文件迁移、外部系统同步、受控修复等真实异步任务；不得新增页面 read model refresh worker。Direct API 目标读架构见 `docs/architecture/direct-api-read-architecture.md`。

Worker 不得依赖 Application、app.server、app.auth 或 HTTP response。Legacy read-model refresh gateway 和页面 `.read_model.refresh` parser 是下线对象；真实后台 worker 只能围绕导入、OA 同步、文件迁移、外部系统同步、受控修复或非页面派生任务，使用明确 registry 完成 event type 声明和运行治理。

legacy `*_read_model_not_fresh` 只允许让当前 event 短延迟 defer；不得补投页面 refresh、parent shard 或 `all` 聚合事件。

当前 P2/P3 closure 的性能门禁是首屏 API 或 direct refresh p95 <= 1000ms；写操作 operation-to-outbox-done 还要求 p99 <= 3000ms。历史 5 秒 SLO 记录是旧基线，不是当前验收上限。Worker 优化必须保留 PostgreSQL durable outbox、worker heartbeat 和 RabbitMQ transport 事实源；legacy dirty scope/readiness 不得恢复为页面 freshness 或健康证明。

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
