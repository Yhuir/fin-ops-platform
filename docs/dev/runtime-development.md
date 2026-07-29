# Runtime 开发入口

本文维护 PostgreSQL durable queue、read model freshness、worker、runtime bootstrap、Redis/RabbitMQ 和对象存储的开发边界。

## Production lightweight bootstrap

- 生产运行应使用轻量 bootstrap 和明确依赖注入，不把 legacy `Application` 作为 service 或 worker 依赖。
- Repository、queue、store、settings provider 和 orchestrator 通过构造函数显式传入。
- legacy snapshot / app Mongo 旧路径只作为迁移观察期回滚、shadow-read 或审计工具，不作为新增事实源。
- `scripts/verify.sh backend` 和 `scripts/verify.sh all` 使用临时 `FIN_OPS_DATA_DIR` 做 clean app check，保护代码启动契约不受开发机 legacy app Mongo 残留影响；当前配置 runtime 状态必须用 `scripts/verify.sh runtime-check` 显式检查。

## Read model 查询边界

- 查询必须通过 freshness/status/enqueue 边界。
- stale/missing/unavailable 不应在请求线程里临时 live rebuild 后伪装 fresh。
- API 应返回 `read_model_status`、`refreshing`、`stale`、`job`、`source_version` 等页面可解释字段。
- Redis 只能缓存 fresh gate 后的 payload。

## Durable queue 和 outbox

- read model refresh 的事实源是 PostgreSQL durable queue。
- 标准入队入口是 `RuntimeQueueRepository.enqueue_read_model_refresh(...)` 或事务内 writer。
- 业务 service 不直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。
- RabbitMQ 只能作为可选 transport/wakeup，不能成为状态事实源。

## Worker registry

新增 worker/read model refresh 时必须同步：

- registry 名称、scope、handler 和 health 暴露。
- manifest/systemd env 或部署脚本。
- freshness/status/enqueue 行为。
- 相关 service/API/worker 测试。
- `../app-architecture/runtime-and-ownership.md` 与 `../operations/runtime-worker-governance.md`。

## Global Runtime Status Plane 开发规则

- 新增页面必须在后端 domain registry 中配置 `key`、`route`、read model、worker 和后台任务类型映射；不能只在 React 页面里维护局部 loading 状态。
- 新增 read model、worker、outbox event 或后台任务类型时，必须同步更新 `RuntimeMonitoringRepository.app_status_runtime_snapshot()` 可读取的 runtime fact 投影、domain registry、read model registry、job registry 和 app status 测试。
- 普通 read model refresh worker/service 成功、失败、schema/source mismatch 时，必须通过 repository/state store 公共方法写入 `read_model.app_status_readiness`；没有 readiness 记录不能被解释为 ready。
- 普通 runtime worker 的 read model handler 由 `ReadModelReadinessReporter` 统一包装；新增 read model refresh handler 不能绕过这个 wrapper。fan-out-only 事件只表示已拆分 scope，不写 `fresh`；如果父 scope 需要等待 shard 收敛，handler 必须返回显式 `readiness_status=refreshing`，让 readiness 记录可解释等待状态；只有父 scope 已真实 rebuild 并发布成功时，handler 才能返回 `readiness_status=fresh`。
- 成本统计不属于 runtime read model：每次请求直接读取一个 PostgreSQL canonical snapshot，不注册 Cost scope、readiness、refresh event 或 worker。历史 `active:all` / `all:all` parent/shard convergence 合同已经删除，不得恢复。
- readiness backfill 只能作为真实 convergence 工具使用：`python -m fin_ops_platform.tools.app_status_readiness_backfill --dry-run` 先读取 projection/active generation 事实；`--apply` 只能写入 dry-run 判定出的真实 `fresh/missing/failed/schema_mismatch/source_mismatch/unavailable`，禁止批量伪造 `fresh`。
- 新增 dependency 时必须更新 app status dependency registry 和 dependency provider。dependency key 缺失不能默认 available；critical dependency missing/unavailable 必须进入 red，optional unavailable 进入 yellow。
- 新增用户可见后台任务必须写入统一 background job progress contract，至少包含任务身份、状态、短标签、消息、进度字段、影响范围和可跳转 route。
- 页面 table/drawer/form loading 不进入全局状态；只有 read model、worker、queue、dependency、background job 等 runtime facts 影响左上角全局 icon。
- `/api/app-health.app_status` 是全局 icon 和 hover 面板的事实源。SSE/轮询/BroadcastChannel 只是传输和缓存优化，不替代 durable runtime facts。
- `server.py` 只能通过 state store / repository 的公开方法读取 app status runtime snapshot；禁止为 app status 访问 `_connection` 或在 `AppStatusOverviewService` 中写 `job.*` SQL。
- 前端 `app_status` mapper 对 `overall`、domain 和 task 的关键字段必须 fail closed；不能把 malformed payload 默认为 green/ready。

## 对象存储开发边界

- 文件对象使用对象存储或兼容实现保存，业务记录保存 object key、checksum、大小、文件名和来源。
- 测试不能依赖真实业务文件。
- 数据重置、回滚和 backfill 必须同时考虑对象存储和数据库引用。

## 本地与服务器一致性

本地开发可以使用轻量依赖，但不能改变运行时语义：freshness、queue、worker、权限、审计和回滚边界应与服务器一致。确实无法完全一致时，必须在对应测试或文档中写明差异。

本地 PostgreSQL primary 验收应优先使用 `./scripts/check-local-runtime.sh` 和 `scripts/verify.sh runtime-check` 检查真实依赖；日常 `scripts/verify.sh all` 只证明代码和测试闭环，不证明本地 `.runtime` 或生产历史数据没有迁移残留。
