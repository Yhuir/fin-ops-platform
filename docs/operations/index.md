# 运维文档索引

- `deployment.md`：发布路径、环境和部署检查。
- `etc-business-batches.md`：ETC 业务批次、OA 自动检测、迁移 dry-run、回滚和 Nginx/API smoke。
- `data-reset.md`：数据重置规则。
- `backup-and-recovery.md`：备份、恢复和回滚要求。
- `object-storage-minio.md`：MinIO/S3 文件对象存储、GridFS backfill、校验和短期回滚。
- `runtime-read-model-hardening.md`：SQL-native read model reconciliation、EXPLAIN 和 source-version guard 验证。
- `read-model-production-audit-2026-05-24.md`：当前生产 read model 分片、SQL-native、Redis/RabbitMQ 边界和下一步收口顺序。
- `monitoring.md`：健康状态、后台任务和告警。
- `local-vs-server-runtime-parity.md`：本地开发、服务器运行、SSH tunnel、AppHealth 指标和性能验收边界。
- `backend-refactor/mongo-backup.md`：后端重构前的 app Mongo、OA Mongo 备份和恢复演练。
- `backend-refactor/postgresql-provisioning.md`：服务器上新建 PostgreSQL、账号、备份、PITR 和 migration 配置。
- `backend-refactor/mongo-to-postgresql-migration.md`：Mongo 到 PostgreSQL 与 GridFS 到 MinIO/S3 的迁移计划。

部署资产和 OA 联调细节见 `../../deploy/oa/README.md`。
