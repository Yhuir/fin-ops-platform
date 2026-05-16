# 运维文档索引

- `deployment.md`：发布路径、环境和部署检查。
- `data-reset.md`：数据重置规则。
- `backup-and-recovery.md`：备份、恢复和回滚要求。
- `monitoring.md`：健康状态、后台任务和告警。
- `backend-refactor/mongo-backup.md`：后端重构前的 app Mongo 备份和恢复演练；不备份、不导出、不改动 OA 源库。
- `backend-refactor/postgresql-provisioning.md`：服务器上新建 PostgreSQL、账号、备份、PITR 和 migration 配置。
- `backend-refactor/mongo-to-postgresql-migration.md`：Mongo 到 PostgreSQL 与 GridFS 到 MinIO/S3 的迁移计划。
- `backend-refactor/app-mongo-backup-runbook.md`：本次服务器 app Mongo 备份、校验和恢复演练记录。
- `backend-refactor/server-postgresql-runbook.md`：本次服务器 PostgreSQL 16 安装、初始化、账号和连通性验证记录。
- `backend-refactor/observability-and-alerting.md`：Axum + PostgreSQL 生产监控、日志、指标和告警方案。
- `backend-refactor/production-readiness-checklist.md`：切换前生产就绪检查清单。
- `backend-refactor/cutover-and-rollback-runbook.md`：上线切换、观测、回滚和禁止事项。

部署资产和 OA 联调细节见 `../../deploy/oa/README.md`。
