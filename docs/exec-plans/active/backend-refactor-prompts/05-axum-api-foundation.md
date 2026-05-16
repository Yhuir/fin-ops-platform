# Prompt 05：Axum API 低耦合骨架

```text
你是 Codex 子代理：Axum API 骨架负责人。工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
新增一个低耦合、生产导向的 Axum API 骨架，不删除、不破坏现有 Python 后端。第一阶段只实现基础设施和健康检查，不迁移复杂业务 API。

必须读取：
- AGENTS.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/migration-roadmap.md
- docs/dev/backend.md
- backend/README.md
- docs/exec-plans/active/backend-refactor-inventory.md，如果存在

架构边界：
- routes：HTTP 入参、鉴权上下文、响应映射。
- services：业务用例和事务边界。
- repositories：SQLx 查询和事务内读写。
- jobs：任务发布、outbox、worker 协议。
- infra：PostgreSQL、Redis、NATS、S3 client。
- observability：tracing、metrics、OpenTelemetry。
- config：环境变量和配置校验。

禁止：
- 不删除 Python 后端。
- 不把所有 handler 写在 main.rs。
- 不在 routes 中写复杂业务规则。
- 不引入 ORM 替代 SQLx。
- 不硬编码 secret。

任务拆分：
1. 项目结构
   - 建立 Rust workspace 或 api crate。
   - 选择清晰目录：config、error、state、routes、middleware、infra、services、repositories、jobs、observability。

2. 配置
   - DATABASE_URL、REDIS_URL、NATS_URL、S3_ENDPOINT、S3_BUCKET 等从环境读取。
   - 本地示例只放占位，不放真实 secret。
   - 缺失必需配置时 fail fast。

3. AppState
   - SQLx pool。
   - Redis client 占位。
   - NATS client 占位。
   - S3 client 占位。
   - clock/id generator 可测试抽象。

4. Middleware
   - trace id。
   - request logging。
   - timeout。
   - body limit。
   - CORS。
   - error mapping。

5. Health
   - /healthz 只检查进程存活。
   - /readyz 检查 PostgreSQL，其他依赖可分项返回。
   - /metrics 暴露 Prometheus metrics。

6. 文档和验证
   - 新建 docs/dev/axum-backend.md。
   - 写本地启动、环境变量、测试命令、健康检查示例。

验收：
- cargo fmt 通过。
- cargo check 通过。
- healthz/readyz 可本地启动验证，或明确缺少依赖原因。
- Python 后端仍可按原 README 启动检查。
- 目录结构能支持后续模块分离，不需要大规模重写。
```

