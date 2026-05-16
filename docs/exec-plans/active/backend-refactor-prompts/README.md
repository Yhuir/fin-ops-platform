# Axum + PostgreSQL 后端重构多子代理 Prompt 包

本目录保存用于 Codex `/goal` 或普通任务执行的多子代理 prompt。当前版本已经按实际进度重排：不再默认从零开始，而是以 `docs/exec-plans/active/backend-refactor-progress.md` 记录的状态为事实源继续执行。

## 当前执行入口

优先使用：

- `00-goal-master-current-state.md`：推荐复制到 `/goal` 的完整总控 prompt。
- `00-current-state-and-gates.md`：当前已完成事项、禁止重复事项、剩余任务和上线门禁。
- `GOAL-USAGE.md`：如何用 `/goal` 执行这些 prompt。
- `GOAL-PROMPTS.md`：按 P0-P4 拆好的可复制 `/goal` prompt 清单。

除非你明确要重新做历史阶段，否则不要直接从旧版 `00-coordinator.md` 从头执行。

## 当前已完成

以 `../backend-refactor-progress.md` 为准，已完成：

- app Mongo `fin_ops_platform_app` 备份、checksum、dryRun、恢复测试库和 GridFS 抽样校验。
- 服务器 PostgreSQL 16.12 安装、初始化、`fin_ops` 数据库、业务角色、schema、扩展和最小权限验证。
- PostgreSQL 不开放公网，只监听 `localhost:5432`。
- Axum API 阶段 1 skeleton。
- PostgreSQL SQLx migration `0001` 到 `0007`，并已在服务器 PostgreSQL 16.12 临时库空库验证通过。
- Beekeeper 已通过 SSH Tunnel 连接 `fin_ops`。

## 不要重复执行

除非用户明确要求回滚、重建或复核，不要重复：

- 重新安装 PostgreSQL。
- 重新初始化 PostgreSQL data directory。
- 覆盖或删除现有 app Mongo 备份。
- 重新生成已经存在的 `0001` 到 `0007` migration。
- 对 OA 源数据库做备份、导出、恢复、写入、压测或人工查询。

## 当前推荐执行顺序

| 顺序 | Prompt | 当前用途 |
| --- | --- | --- |
| 0 | `00-goal-master-current-state.md` | `/goal` 总入口，先确认当前状态和门禁，再调度子代理。 |
| 1 | `06a-mongo-export-tooling.md` | 实现 app Mongo 只读规范化导出工具。 |
| 2 | `06b-postgres-import-validation-tooling.md` | 实现 PostgreSQL staging 导入与 count/hash/金额对账。 |
| 3 | `06c-data-migration-dry-run.md` | 在备份/恢复测试库或 staging 上执行 dry-run，生成可审计报告。 |
| 4 | `06d-gridfs-minio-migration.md` | 设计并实现 GridFS 到 MinIO/S3 的文件迁移和抽样校验。 |
| 5 | `07-outbox-queue-worker.md` | 落地 outbox、NATS JetStream、Worker 协议和任务状态。 |
| 6 | `08-read-models-and-search.md` | 落地 read model、搜索索引和增量重建。 |
| 7 | `09-api-migration-batches.md` | 按批次迁移 API；优先执行 `09a`、`09b`、`09c`，最后执行 `09d`。 |
| 8 | `10-observability-security-readiness.md` | 补齐观测、安全、备份、压测和上线门禁。 |
| 9 | `12-formal-migration-and-cutover-gates.md` | dry-run 通过后，执行正式迁移前的最终 go/no-go 门禁。 |
| 10 | `11-cutover-and-rollback.md` | 仅在用户明确授权且所有门禁通过后，制定和执行切换回滚流程。 |

## 历史/已完成阶段 Prompt

这些 prompt 仍保留，作为复核或灾备重建参考，不作为当前默认起点：

- `01-inventory-and-contracts.md`
- `02-app-mongo-backup.md`
- `03-postgresql-server-provisioning.md`
- `04-postgresql-schema-and-migrations.md`
- `04a-schema-foundation.md`
- `04b-financial-facts-schema.md`
- `04c-readmodel-job-schema.md`
- `05-axum-api-foundation.md`

如果执行这些 prompt，必须先读取 `00-current-state-and-gates.md`，并把任务改成“验证现状和补缺口”，不是重复执行。

## 完整重构闭环

完整重构计划仍包含：

1. 当前系统盘点和契约冻结。
2. app Mongo 备份和恢复演练。
3. PostgreSQL 基础设施和 SQLx migration。
4. Axum API skeleton。
5. app Mongo 到 PostgreSQL staging 的迁移工具。
6. GridFS 到 MinIO/S3。
7. staging 到正式事实表、read model、search index、job/outbox 的转换和对账。
8. Outbox + NATS JetStream + Python Worker。
9. API 按低风险到高风险迁移。
10. Observability、security、backup、PITR、压测和权限审计。
11. 影子读、双写、切读、回滚、冻结 app Mongo。

## 通用红线

- 不备份、不导出、不恢复、不修改、不压测 OA 源数据库。
- 只备份和迁移 app 关联 Mongo 数据库及 GridFS。
- 所有 secret 不得写入 git、文档、日志摘要、manifest 或迁移报告。
- 没有 dry-run 对账报告，不允许迁移生产数据。
- 没有 staging 验证，不允许生产切流。
- PostgreSQL 不开放公网访问。
- 单个 prompt 如果执行范围过大，必须继续拆成更小 prompt。
