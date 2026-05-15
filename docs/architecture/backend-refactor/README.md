# Axum + PostgreSQL 后端重构文档索引

本目录记录后端从当前 Python/Mongo 形态演进到 Axum/PostgreSQL 生产架构的长期计划。这里的文档是执行依据，不是历史 prompt。

## 阅读顺序

1. `target-architecture.md`：目标生产架构、组件边界和技术取舍。
2. `migration-roadmap.md`：分阶段重构路线、验收标准和回滚口径。
3. `data-model-and-read-models.md`：PostgreSQL 主事实、分区、搜索表、读模型和索引设计。
4. `../../operations/backend-refactor/mongo-backup.md`：迁移前 Mongo 备份和恢复演练。
5. `../../operations/backend-refactor/postgresql-provisioning.md`：服务器上新建 PostgreSQL、基础安全、备份和连接配置。
6. `../../operations/backend-refactor/mongo-to-postgresql-migration.md`：Mongo 到 PostgreSQL 的数据迁移、校验、双写和切换步骤。

## 当前结论

目标架构采用：

- API：Axum + Tokio + Tower middleware。
- DB：PostgreSQL 16/17 + SQLx + `sqlx migrate`，手写 SQL 优先。
- Cache：Redis，只做缓存、限流和短期状态。
- Queue：NATS JetStream + PostgreSQL outbox。
- Worker：Python Worker 处理 Excel、PDF、OCR、OA 附件解析。
- Storage：MinIO/S3 保存附件和导入文件，PostgreSQL 只保存文件元数据。
- Observability：`tracing`、OpenTelemetry OTLP、Prometheus、Grafana。

## 非目标

- 不把 Mongo 继续作为核心业务事实源。
- 不把 Redis 当最终状态库。
- 不在 Axum API 请求路径中实时扫描 OA Mongo。
- 不在第一阶段引入完整微服务拆分；先完成单体边界清晰的高性能后端。

