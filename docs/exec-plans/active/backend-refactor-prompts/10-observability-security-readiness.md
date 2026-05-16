# Prompt 10：可观测性、安全与生产就绪门禁

```text
你是 Codex 子代理：生产就绪负责人。工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
为 Axum + PostgreSQL 后端建立生产安全、可观测性、备份监控、上线门禁和运维 runbook。不要只写泛泛清单，要结合本 app 的导入、核销、OA 同步、read model 和文件迁移。

必须读取：
- AGENTS.md
- SECURITY.md
- RELIABILITY.md
- docs/operations/monitoring.md
- docs/operations/backup-and-recovery.md
- docs/operations/backend-refactor/postgresql-provisioning.md
- docs/operations/backend-refactor/mongo-backup.md
- docs/architecture/backend-refactor/target-architecture.md

安全范围：
- secret 管理。
- 数据库账号最小权限。
- Nginx TLS、body limit、上传限制。
- 文件类型、大小、checksum、病毒/OCR 风险预留。
- OA SSO/RBAC/数据范围。
- 审计日志。
- idempotency。

观测指标：
- API P50/P95/P99 latency。
- HTTP 4xx/5xx。
- PostgreSQL pool、slow query、deadlock、backup age、WAL archive lag。
- Redis hit/miss、连接错误。
- NATS queue lag、ack delay、dead letter count。
- Worker success/failure/retry。
- MinIO/S3 upload/download error。
- read model rebuild duration。
- OA sync lag。
- 业务指标：待核销金额、异常单数量、导入失败数。

任务拆分：
1. tracing/logging
   - JSON logs。
   - trace id。
   - user/session/request path/status/latency。
   - 不记录敏感字段。

2. metrics
   - Prometheus endpoint。
   - 指标命名。
   - Grafana dashboard 草案。

3. alerting
   - backup failure。
   - PostgreSQL unavailable。
   - queue backlog。
   - worker dead letters。
   - read model stale。
   - OA sync lag。

4. security checklist
   - 账号。
   - secret。
   - 网络。
   - 上传。
   - 审计。

5. production readiness gate
   - 上线前必须通过的命令和验证。
   - 阻断条件。
   - 回滚触发条件。

交付物：
- docs/operations/backend-refactor/observability-and-alerting.md。
- docs/operations/backend-refactor/production-readiness-checklist.md。

验收：
- 指标和告警都能对应实际风险。
- 有明确上线阻断条件。
- 不把 secret 放进示例。
- 覆盖 PostgreSQL、app Mongo 备份、MinIO/S3、NATS、Worker。
```

