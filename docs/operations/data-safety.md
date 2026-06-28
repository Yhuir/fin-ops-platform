# 数据安全、重置、备份与对象存储

本文合并维护数据重置、备份恢复、对象存储和高风险数据操作的运维口径。

## 数据安全原则

- 生产级数据操作必须考虑权限、审计、回滚、数据一致性和验证方式。
- PostgreSQL 是 app 主读写事实源；OA MongoDB 继续只读接入。
- Redis 只缓存 direct API 短 TTL payload；RabbitMQ 只作为可选 transport/wakeup。
- 对象存储保存文件对象，数据库保存对象引用、checksum、大小、文件名和来源。

## 数据重置

数据重置必须限定范围并记录：

- 操作者、时间、原因、环境、影响模块和影响对象。
- 是否清理 direct API cache、outbox、Redis cache、对象存储引用。
- 重置前备份和重置后验证命令。
- 是否需要暂停 worker 或 drain queue。

重置后必须确保页面不会把旧缓存或旧 payload 显示为 fresh。

## 备份与恢复

备份至少覆盖：

- PostgreSQL schema/data。
- 对象存储 bucket 或兼容存储路径。
- 部署 env、systemd/manifest、Nginx 配置和可恢复的 runtime 配置。

恢复必须验证：

- app check 可通过。
- 关键 API 返回 JSON 而不是 HTML。
- direct API status/latency 正常。
- worker/queue 可观测且没有大量 orphan outbox。

## 对象存储

- MinIO/S3 只保存文件对象，不作为业务状态事实源。
- 文件上传需要 checksum、大小、MIME/扩展名校验和来源记录。
- GridFS 或 legacy 文件路径只作为迁移观察期回滚/审计来源，不作为新增写入目标。
- backfill 需要 dry-run、checksum 校验、失败重试和短期回滚路径。

## 高风险操作清单

| 操作 | 必要检查 |
| --- | --- |
| 清库/重置 | 备份、权限、审计、worker 暂停、cache/direct API 清理 |
| 对象存储迁移 | checksum、引用完整性、dry-run、回滚路径 |
| legacy projection backfill | scope、source version、outbox、后台任务收敛、direct API 验证 |
| 批量撤回/repair | affected objects、审计、跨页刷新、回滚说明 |

## 相关文档

- PostgreSQL runtime：`postgresql-runtime.md`
- Worker/read model：`runtime-worker-governance.md`
- 部署：`deployment.md`
- 监控：`monitoring.md`
