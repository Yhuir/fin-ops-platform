# Runtime 开发入口

本文维护 PostgreSQL durable queue、worker、runtime bootstrap、API Redis 使用和对象存储的开发边界。

## Production lightweight bootstrap

- 生产运行应使用轻量 bootstrap 和明确依赖注入，不把 legacy `Application` 作为 service 或 worker 依赖。
- Repository、queue、store、settings provider 和 orchestrator 通过构造函数显式传入。
- legacy snapshot / app Mongo 旧路径只作为迁移观察期回滚、shadow-read 或审计工具，不作为新增事实源。
- `scripts/verify.sh backend` 和 `scripts/verify.sh all` 使用临时 `FIN_OPS_DATA_DIR` 做 clean app check，保护代码启动契约不受开发机 legacy app Mongo 残留影响；当前配置 runtime 状态必须用 `scripts/verify.sh runtime-check` 显式检查。

## 页面查询边界

- 页面 API 直接读取 canonical PostgreSQL facts，不通过 page projection/read model Worker。
- API 不在 GET 中 enqueue、轮询或临时 rebuild。
- Redis 仅限 API 会话或明确的有界缓存，不参与 Worker claim/complete。

## Durable queue 和 outbox

- 通用后台事件的唯一任务传输和状态事实源是 PostgreSQL durable queue。
- 标准入队入口是 owner service/repository 的已登记 durable job/event 方法或事务内 writer。
- 业务 service 不直接 SQL 写 `job.outbox_events`。
- 不增加 RabbitMQ、Redis 或进程内线程作为第二任务通道。

## Worker registry

新增 worker/event 时必须同步：

- registry 名称、scope、handler 和 health 暴露。
- manifest/systemd env 或部署脚本。
- claim/retry/idempotency/heartbeat 行为。
- 相关 service/API/worker 测试。
- `../app-architecture/runtime-and-ownership.md` 与 `../operations/runtime-worker-governance.md`。

## Global Runtime Status Plane 开发规则

- 新增页面必须在后端 domain registry 中配置 `key`、`route`、required worker、后台任务和依赖映射；不能只在 React 页面里维护局部 loading 状态。
- 新增 worker、outbox event 或后台任务类型时，必须同步更新 `RuntimeMonitoringRepository.app_status_runtime_snapshot()` 可读取的 runtime facts、domain/job registry、worker registry 和 App Status 测试。
- App 当前没有运行时 read model、readiness、dirty scope、refresh handler 或 backfill 工具；发现这些入口回流时必须删除并扩展 `tests/test_read_model_runtime_removal.py`，不能以兼容分支恢复。
- 新增 dependency 时必须更新 app status dependency registry 和 dependency provider。dependency key 缺失不能默认 available；critical dependency missing/unavailable 必须进入 red，optional unavailable 进入 yellow。
- 新增用户可见后台任务必须写入统一 background job progress contract，至少包含任务身份、状态、短标签、消息、进度字段、影响范围和可跳转 route。
- 页面 table/drawer/form loading 不进入全局状态；只有 worker、queue、dependency、background job 等 runtime facts 影响左上角全局 icon。
- `/api/app-health.app_status` 是全局 icon 和 hover 面板的事实源。有界轮询/BroadcastChannel 只是传输和缓存优化，不替代 durable runtime facts；旧 SSE/EventSource 路径不得恢复。
- `server.py` 只能通过 state store / repository 的公开方法读取 app status runtime snapshot；禁止为 app status 访问 `_connection` 或在 `AppStatusOverviewService` 中写 `job.*` SQL。
- 前端 `app_status` mapper 对 `overall`、domain 和 task 的关键字段必须 fail closed；不能把 malformed payload 默认为 green/ready。

## 对象存储开发边界

- 文件对象使用对象存储或兼容实现保存，业务记录保存 object key、checksum、大小、文件名和来源。
- 测试不能依赖真实业务文件。
- 数据重置、回滚和 backfill 必须同时考虑对象存储和数据库引用。

## 本地与服务器一致性

本地开发可以使用轻量依赖，但不能改变运行时语义：freshness、queue、worker、权限、审计和回滚边界应与服务器一致。确实无法完全一致时，必须在对应测试或文档中写明差异。

本地 PostgreSQL primary 验收应优先使用 `./scripts/check-local-runtime.sh` 和 `scripts/verify.sh runtime-check` 检查真实依赖；日常 `scripts/verify.sh all` 只证明代码和测试闭环，不证明本地 `.runtime` 或生产历史数据没有迁移残留。
