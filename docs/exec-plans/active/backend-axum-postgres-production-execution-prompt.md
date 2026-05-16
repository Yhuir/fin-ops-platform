# Codex 多子代理执行 Prompt：Axum + PostgreSQL 生产级后端重构

下面这份 prompt 用于交给 Codex 在后续执行后端重构。执行前必须先补齐服务器、账号、维护窗口和生产确认信息。该 prompt 明确授权使用多子代理，但生产服务器操作必须遵守安全门槛。

```text
你是 Codex，总协调器，工作目录是 /Users/yu/Desktop/fin-ops-platform。

目标：把当前后端从 Python HTTP + app Mongo/GridFS 演进到生产级 Axum + PostgreSQL 架构，并完成服务器上 PostgreSQL 新建、app Mongo 备份、迁移工具和第一阶段落地。你必须使用多任务子代理并行推进，但所有生产服务器变更必须先获得用户明确确认。

必须阅读的仓库文档：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/architecture/backend-refactor/README.md
- docs/architecture/backend-refactor/target-architecture.md
- docs/architecture/backend-refactor/migration-roadmap.md
- docs/architecture/backend-refactor/data-model-and-read-models.md
- docs/operations/backend-refactor/mongo-backup.md
- docs/operations/backend-refactor/postgresql-provisioning.md
- docs/operations/backend-refactor/mongo-to-postgresql-migration.md
- docs/exec-plans/active/backend-axum-postgres-refactor.md

最高优先级约束：
1. 不要备份、导出、恢复、修改、压测或直接操作 OA 源数据库。
2. OA Mongo 只允许通过现有只读同步逻辑读取业务需要的数据；不得执行 mongodump、mongorestore、collection export 或写操作。
3. 只备份 app 关联的 Mongo 数据库，即当前 FIN_OPS_STORAGE_MODE=mongo_only 使用的 app 状态库和 GridFS。
4. 任何包含密码、token、私钥、Mongo URI、PostgreSQL URI、S3 secret、NATS credential 的内容不得写入 git。
5. 生产服务器操作前必须先向用户确认：SSH 连接方式、目标服务器、操作系统、是否允许安装包、维护窗口、备份目录、PostgreSQL 版本、app Mongo URI 获取方式。
6. 不允许在没有成功备份和恢复演练前迁移生产数据。
7. 不允许用旧 Mongo 全量覆盖已经成为事实源的 PostgreSQL。
8. 不允许为了“跑通”而吞掉迁移差异、金额差异、checksum 差异或权限错误。
9. 当前 repo 可能有用户未提交改动；执行前检查 git status，不要覆盖用户改动。
10. 每个阶段结束必须留下可验证产物：命令、日志路径、校验结果、风险和下一步。

如果缺少以下信息，先问用户，不要猜：
- 生产或 staging 服务器 SSH host、user、port、是否需要跳板机。
- 服务器 OS 和版本，是否允许 sudo。
- PostgreSQL 目标版本：16 还是 17。
- app Mongo 连接信息的安全获取方式，不能要求用户把密码写进 repo。
- app Mongo 数据库名，默认可假设 fin_ops_platform_app，但必须验证。
- 备份根目录，例如 /data/backups/fin_ops。
- 是否有 staging Mongo 可做恢复演练。
- 是否已有 MinIO/S3、Redis、NATS，还是需要新建。
- 是否当前阶段只做 staging，不碰 production。
- 可接受维护窗口和回滚条件。

总体目标架构：
- API：Axum + Tokio + Tower middleware。
- DB：PostgreSQL 16/17 + SQLx + sqlx migrate，手写 SQL 优先。
- Cache：Redis，只做缓存、限流、短期状态。
- Queue：NATS JetStream + PostgreSQL outbox。
- Worker：Python Worker 处理 Excel/PDF/OCR/OA 附件解析，结果写回 PostgreSQL。
- Storage：MinIO/S3 保存附件和导入文件，PostgreSQL 只保存元数据。
- Observability：tracing + tracing-subscriber JSON logs + OpenTelemetry OTLP + Prometheus + Grafana。
- Deploy：Nginx 反代，Docker Compose 起步，后续可迁移 Kubernetes/ECS/VM + systemd。

你必须按下面的子代理分工执行。子代理之间不得写同一批文件，避免冲突。总协调器负责整合、复核和最终提交建议。

子代理 A：仓库盘点与契约梳理
职责：
- 读取后端入口、服务层、state_store、mongo_oa_adapter、routes_workbench、导入和文件相关代码。
- 盘点当前 API 路由、主要请求/响应、前端调用点。
- 盘点 app Mongo collection、GridFS、pickle/binary payload 的读取路径。
- 明确哪些数据属于 app Mongo，哪些属于 OA Mongo。
严禁：
- 不要连接 OA 源数据库。
- 不要修改业务代码。
交付物：
- docs/exec-plans/active/backend-refactor-inventory.md
- 包含当前路由清单、app Mongo 数据对象清单、GridFS 使用点、迁移风险点。

子代理 B：PostgreSQL 服务器与基础设施
职责：
- 在用户确认的服务器上检查 OS、磁盘、内存、网络、防火墙和 sudo 权限。
- 按 docs/operations/backend-refactor/postgresql-provisioning.md 新建 PostgreSQL 16/17。
- 创建 fin_ops 数据库和角色：fin_ops_migrator、fin_ops_api、fin_ops_worker、fin_ops_readonly。
- 创建 schema：app、read_model、job、audit、staging。
- 启用扩展：pgcrypto、pg_trgm、btree_gin。
- 配置最小 pg_hba 访问边界、连接限制、慢查询日志。
- 建立逻辑备份命令和 PITR 方案，至少在 staging 完成恢复演练。
严禁：
- 不要在未确认前安装生产包或改生产配置。
- 不要把数据库密码写入文件或 git。
交付物：
- docs/operations/backend-refactor/server-postgresql-runbook.md
- 服务器实际版本、配置文件路径、data directory、hba_file、备份路径、恢复演练结果。

子代理 C：app Mongo 备份与恢复演练
职责：
- 只处理 app Mongo。
- 使用 mongodump --archive --gzip 备份 app Mongo。
- 生成 SHA-256 checksum。
- 记录 collection counts、db.stats、GridFS 相关集合统计。
- 恢复到 staging Mongo 或用户指定的恢复测试库。
- 比对恢复前后集合数量，抽样验证 GridFS 文件可读取。
严禁：
- 不要访问、备份、导出、恢复、修改 OA 源数据库。
- 不要执行任何 OA_MONGO_URI、mongodump OA_DB、nsInclude OA collection 之类命令。
交付物：
- docs/operations/backend-refactor/app-mongo-backup-runbook.md
- 备份命令模板、实际执行日志路径、checksum、恢复演练结果、差异说明。

子代理 D：PostgreSQL schema 与 SQLx migration
职责：
- 建立 Rust/SQLx migration 目录。
- 设计并实现第一版 PostgreSQL schema：导入、文件、银行流水、发票、OA 归一化结果、核销关系、异常、outbox、审计、read model、search index。
- 对大表设计月份或年份分区策略。
- 建立 pg_trgm/GIN/组合索引。
- 写出最小可运行 migration，并保证空库可执行。
- 对核心查询写 EXPLAIN 验证说明。
严禁：
- 不要为了省事把核心字段全部塞进 jsonb。
- 不要把金额设计成 float。
交付物：
- migrations 或 Rust workspace 中对应 SQL migration 文件。
- docs/architecture/backend-refactor/postgresql-schema-notes.md
- 包含表设计、索引、分区、约束、迁移顺序和未决问题。

子代理 E：Axum API 骨架
职责：
- 新建 Rust workspace 或 crate，保持与现有 repo 风格兼容。
- 实现 Axum API 基础结构：config、app state、error、healthz、readyz、metrics、tracing。
- 接入 SQLx pool、Redis client、NATS client、S3 client 的配置占位和连接检查。
- 使用 Tower middleware 处理 trace id、timeout、body limit、CORS、请求日志。
- 不迁移全部业务 API，只完成生产骨架和可验证健康检查。
严禁：
- 不要破坏当前 Python 后端启动。
- 不要删除现有后端代码。
交付物：
- Rust API skeleton 代码。
- docs/dev/axum-backend.md
- 本地启动、配置、健康检查、测试命令。

子代理 F：迁移工具与数据校验
职责：
- 设计 app Mongo 到 PostgreSQL 的导出和导入工具。
- 优先复用现有 Python ApplicationStateStore 和业务 service 读取 app Mongo，不手写 pickle/binary 解析。
- 导出 NDJSON/manifest/file manifest。
- 导入 PostgreSQL staging schema。
- 实现数量、金额、月份、状态、文件 checksum 的对账报告。
- 设计 GridFS 到 MinIO/S3 的迁移流程。
严禁：
- 不要从 OA 源库导出数据。
- 不要把敏感连接串写进 manifest。
交付物：
- scripts 或 tools 下的迁移工具草案。
- docs/operations/backend-refactor/data-migration-runbook.md
- docs/operations/backend-refactor/migration-validation-report-template.md

子代理 G：任务队列、outbox 与 Worker 协议
职责：
- 设计 PostgreSQL outbox 表和 publisher。
- 设计 NATS JetStream stream、consumer、ack、retry、dead-letter 策略。
- 设计 Python Worker 任务协议：文件解析、OA 同步、read model 重建。
- 定义任务幂等键、任务状态、重试次数、错误摘要和人工重放入口。
严禁：
- 不要把 Redis 当最终任务事实源。
交付物：
- docs/architecture/backend-refactor/outbox-and-jobs.md
- 如进入实现阶段，提供最小 outbox publisher 和 worker 协议代码。

子代理 H：安全、观测、备份和上线门禁
职责：
- 审核配置、secret、账号权限、Nginx、TLS、body limit、上传限制。
- 设计 Prometheus/Grafana 指标：API latency、DB pool、slow query、queue lag、worker failure、backup age、read model rebuild duration。
- 设计上线门禁和回滚手册。
- 补充安全清单和运维 checklist。
交付物：
- docs/operations/backend-refactor/production-readiness-checklist.md
- docs/operations/backend-refactor/observability-and-alerting.md

总协调器执行流程：
1. 检查 git status，列出已有改动，避免覆盖用户内容。
2. 阅读所有指定文档和 AGENTS.md。
3. 如果缺少服务器/数据库/备份/维护窗口信息，先问用户。
4. 建立阶段计划，不要直接全量重构。
5. 并行启动子代理 A、C、D、E、F、G、H；B 只有在用户明确提供服务器和授权后才能执行。
6. 每个子代理只负责自己的文件和交付物。
7. 总协调器复核子代理结果，修正文档链接、冲突和遗漏。
8. 运行验证：
   - git diff --check
   - Markdown 链接和明显路径检查
   - Rust cargo check/test，如果 Rust skeleton 已实现
   - Python unittest 或现有后端 check，如果改动 Python 工具
   - SQL migration 在空库 staging 执行
9. 生成最终报告：已完成、未完成、阻塞项、生产风险、下一步。

生产操作分级：
- Level 0：只读 repo 和写文档，可以直接执行。
- Level 1：本地开发环境、Docker Compose、空 staging 数据库，可以执行但要记录。
- Level 2：staging 服务器安装 PostgreSQL、Redis、NATS、MinIO，需要用户确认目标服务器。
- Level 3：生产服务器安装、配置、备份、迁移，需要用户明确二次确认。
- Level 4：生产切流、停写、恢复、删除旧数据，必须单独制定变更单，不在本 prompt 首轮执行。

第一轮执行范围建议：
- 完成仓库盘点。
- 完成 app Mongo 备份 runbook 和可执行脚本模板。
- 完成 PostgreSQL provisioning runbook。
- 完成 SQLx migration 初版草案。
- 完成 Axum skeleton。
- 完成 migration/export/import 工具草案。
- 完成 outbox/jobs/observability 文档。
- 如果用户提供 staging 服务器授权，则在 staging 新建 PostgreSQL 并验证。
- 不碰生产切流。
- 不备份或操作 OA 源数据库。

最终交付格式：
- 列出所有新增/修改文件。
- 列出执行过的命令和验证结果。
- 列出服务器操作记录，包括 host 摘要、PostgreSQL 版本、data dir、backup dir，不暴露 secret。
- 列出未执行的生产操作和原因。
- 明确下一步需要用户确认的信息。
```

