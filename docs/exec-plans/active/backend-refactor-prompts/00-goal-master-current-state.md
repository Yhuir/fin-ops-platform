# Prompt 00G：/goal 总入口，基于当前状态继续执行完整后端重构

```text
你是 Codex 总协调器，工作目录是 /Users/yu/Desktop/fin-ops-platform。你必须使用多子代理完成 Axum + PostgreSQL 生产级后端重构，但要基于当前已完成状态继续执行，禁止从零重复操作。

总目标：
把当前 Python HTTP + app Mongo/GridFS 后端，逐步演进为生产级 Axum + PostgreSQL 后端：
- API：Axum + Tokio + Tower
- DB：PostgreSQL 16/17 + SQLx + 手写 SQL
- Cache：Redis 仅用于缓存、限流、短期状态
- Queue：NATS JetStream + PostgreSQL outbox
- Worker：Python Worker 处理 Excel/PDF/OCR/OA 附件解析
- Storage：MinIO/S3 保存附件和导入文件，PostgreSQL 保存元数据
- Observability：tracing JSON logs + OpenTelemetry OTLP + Prometheus + Grafana
- Deploy：Nginx 反代，Docker Compose 起步，后续可 Kubernetes/ECS/VM + systemd

必须先读：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/exec-plans/active/backend-refactor-progress.md
- docs/exec-plans/active/backend-refactor-prompts/README.md
- docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/migration-roadmap.md
- docs/architecture/backend-refactor/postgresql-schema-notes.md
- docs/architecture/backend-refactor/outbox-and-jobs.md
- docs/architecture/backend-refactor/read-models-and-search.md
- docs/operations/backend-refactor/app-mongo-backup-runbook.md
- docs/operations/backend-refactor/server-postgresql-runbook.md
- docs/operations/backend-refactor/mongo-to-postgresql-migration.md
- docs/operations/backend-refactor/production-readiness-checklist.md
- docs/operations/backend-refactor/cutover-and-rollback-runbook.md
- docs/dev/axum-backend.md
- rust/fin-ops-api/migrations/README.md

当前事实：
- app Mongo 已备份并完成恢复演练。
- PostgreSQL 16.12 已在服务器安装并创建 `fin_ops`。
- PostgreSQL 只监听 `localhost:5432`，不开放公网。
- 业务角色、schema、扩展已创建。
- Axum skeleton 已生成。
- SQLx migration `0001` 到 `0007` 已生成，并已在 PostgreSQL 16.12 临时库空库验证通过。
- Beekeeper 已通过 SSH Tunnel 登录 `fin_ops`。

最高优先级红线：
1. 不操作 OA 源数据库。禁止备份、导出、恢复、修改、压测、人工查询 OA 源库。
2. 只处理 app Mongo 数据库 `fin_ops_platform_app` 和 app GridFS。
3. secret 不进 git、不进文档、不进日志摘要、不进 manifest、不进对账报告。
4. PostgreSQL 不开放公网访问。
5. 没有 dry-run 对账报告，不允许生产数据迁移。
6. 没有生产就绪清单通过，不允许切流。
7. 不允许旧 Mongo 全量覆盖已经成为事实源的 PostgreSQL。
8. 不允许吞掉 count、amount、checksum、状态、月份或权限差异。

禁止重复：
- 不要重新安装 PostgreSQL。
- 不要重新初始化 PostgreSQL data directory。
- 不要覆盖已有 app Mongo 备份。
- 不要重写已验证通过的 `0001` 到 `0007` migration，除非先说明原因并保持前向迁移原则。

执行策略：
你必须先输出任务计划，然后按模块派发子代理。每个子代理必须有明确写入范围，不得跨模块修改。并行任务必须没有共享写文件冲突。

当前优先阶段：

阶段 A：迁移工具和 dry-run
- 执行 `06a-mongo-export-tooling.md`。
- 执行 `06b-postgres-import-validation-tooling.md`。
- 执行 `06c-data-migration-dry-run.md`。
- 执行 `06d-gridfs-minio-migration.md`。

阶段 B：任务队列和读模型
- 执行 `07-outbox-queue-worker.md`。
- 执行 `08-read-models-and-search.md`。

阶段 C：API 分批迁移
- 执行 `09a-low-risk-read-apis.md`。
- 执行 `09b-import-file-apis.md`。
- 执行 `09c-workbench-read-apis.md`。
- 只有前面验证通过后执行 `09d-reconciliation-write-apis.md`。

阶段 D：生产准备
- 执行 `10-observability-security-readiness.md`。
- 执行 `12-formal-migration-and-cutover-gates.md`。
- 最后执行 `11-cutover-and-rollback.md`。

子代理拆分规则：
- 数据导出、staging 导入、GridFS 文件迁移、对账报告必须分开。
- 低风险读 API、导入文件 API、工作台读 API、核销写 API 必须分开。
- outbox publisher、NATS 配置、Python Worker 协议、read model rebuild 必须分开。
- 每个子任务超过一次 prompt 安全范围时，继续拆分。

验证要求：
- 每轮都运行 `git status --short`。
- 文档/Rust/SQL 改动后运行 `git diff --check -- docs rust scripts tools backend`。
- 扫描 secret：不得出现真实密码、token、完整 URI。
- Rust 可用时运行 `cargo fmt --all --check`、`cargo check --workspace`、`cargo test --workspace`。
- SQL migration 变更必须在 PostgreSQL 16/17 临时库验证。
- 数据迁移必须生成 count/hash/amount/month/status/file checksum 报告。
- API 迁移必须有契约 fixture、旧 Python 与新 Axum 差异报告或等价验证。

最终交付：
- 更新 `docs/exec-plans/active/backend-refactor-progress.md`。
- 更新相关 runbook 和执行报告。
- 列出已完成、未完成、阻塞项、风险和下一步 prompt。
- 不要声称未迁移的数据已经迁移完成。
```

