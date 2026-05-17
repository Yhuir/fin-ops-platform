# Prompt 00S：当前状态、门禁和禁止重复事项

```text
/goal
你是 Codex 后端重构执行前检查代理，工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：
在执行任何 Axum + PostgreSQL 后端重构子任务前，先确认当前真实状态、已完成事项、禁止重复事项、剩余任务和门禁。你的输出用于后续子代理调度，不能修改生产数据。

必须读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/exec-plans/active/backend-refactor-progress.md
- docs/exec-plans/active/backend-refactor-prompts/README.md
- docs/operations/backend-refactor/app-mongo-backup-runbook.md
- docs/operations/backend-refactor/server-postgresql-runbook.md
- docs/dev/axum-backend.md
- rust/fin-ops-api/migrations/README.md

当前已完成事实：
1. app Mongo 数据库 `fin_ops_platform_app` 已备份。
2. app Mongo 备份已 checksum、mongorestore dryRun、恢复测试库、collection count 对账和 GridFS 抽样。
3. OA 源数据库不在备份、导出、迁移和压测范围内。
4. 服务器 PostgreSQL 16.12 已安装并启动。
5. PostgreSQL `fin_ops` 数据库已创建。
6. PostgreSQL 角色已创建：`fin_ops_migrator`、`fin_ops_api`、`fin_ops_worker`、`fin_ops_readonly`。
7. PostgreSQL schema 已创建：`app`、`read_model`、`job`、`audit`、`staging`。
8. 扩展已启用：`pgcrypto`、`pg_trgm`、`btree_gin`。
9. PostgreSQL 只监听 `localhost:5432`，不开放公网。
10. Axum API skeleton 已在 `rust/fin-ops-api/`。
11. SQLx migration `0001` 到 `0007` 已生成。
12. `0001` 到 `0007` 已在服务器 PostgreSQL 16.12 临时库空库验证通过。
13. Beekeeper 已通过 SSH Tunnel 连接 `fin_ops`，使用 readonly 账号。

禁止重复执行：
- 不要重新初始化 PostgreSQL data directory。
- 不要删除或覆盖 `/var/lib/pgsql/data`。
- 不要删除或覆盖 app Mongo 备份目录。
- 不要重新执行会覆盖已有备份的 mongodump 命令。
- 不要把旧 Mongo 全量覆盖已经写入 PostgreSQL 的事实数据。
- 不要对 OA 源数据库执行 mongodump、mongorestore、mongoexport、查询、写入、压测或 schema 探测。
- 不要把密码、token、Mongo URI、PostgreSQL URI、S3 secret、NATS credential 写入 git。

当前未完成：
1. 本机或 CI 的 Rust 工具链验证：`cargo fmt`、`cargo check`、`cargo test`。
2. SQLx CLI/migration runner 接入。
3. app Mongo 规范化导出工具。
4. PostgreSQL staging 导入工具。
5. staging 到 app/read_model/job/audit 的转换工具。
6. count/hash/金额/月度/状态/文件 checksum 对账报告。
7. GridFS 到 MinIO/S3 文件迁移和抽样下载校验。
8. Outbox publisher、NATS JetStream、Python Worker 任务协议落地。
9. read model 和 search index 增量重建实现。
10. API 分批迁移到 Axum。
11. PostgreSQL PITR、MinIO 版本化、恢复演练和压测报告。
12. 影子读、双写、切读、冻结 app Mongo。

当前推荐下一步：
优先执行 `06a-mongo-export-tooling.md`、`06b-postgres-import-validation-tooling.md`、`06c-data-migration-dry-run.md`。不要直接执行生产切换。

输出要求：
- 用中文输出当前状态表。
- 标记每个模块：已完成、待验证、待实现、禁止执行。
- 给出下一轮建议使用的具体 prompt 文件。
- 如果用户要求 `/goal`，建议使用 `00-goal-master-current-state.md`。
```

