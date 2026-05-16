# Axum + PostgreSQL 重构 `/goal` Prompt 清单

本文件把当前后端重构拆成可逐条复制执行的 `/goal` prompt。不要一次性执行全部 prompt；每次只复制一个模块，完成验证后再进入下一条。

## 通用使用规则

每条 `/goal` 都默认继承这些硬性约束：

```text
硬性约束：
1. 不备份、不导出、不恢复、不修改、不压测、不人工查询 OA 源数据库。
2. 不写入真实 secret、URI、密码、token、私钥。
3. PostgreSQL 不开放公网访问。
4. 不覆盖已有 app Mongo 备份。
5. 没有 dry-run 对账报告，不迁移生产数据。
6. 没有用户明确授权，不做生产切流。
7. 不把旧 Mongo 全量覆盖已经成为事实源的 PostgreSQL。
8. 所有结果必须更新或引用当前进度文档。
```

可以使用子代理，但必须遵守：

- 每个子代理只能负责一个清晰模块。
- 子代理必须声明写入范围。
- 共享文件不能并行写。
- 生产服务器操作、真实数据迁移、切流动作不能交给多个子代理并行执行。

## P0：状态复核和门禁

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md。

本次只做 P0 阻断/门禁复核，不执行具体实现。

允许使用子代理：否。这个任务由主代理完成即可。

目标：
1. 读取当前状态文档。
2. 核对已完成事项：app Mongo 备份、PostgreSQL 安装、角色/schema/扩展、Axum skeleton、0001-0007 migration、PostgreSQL 16 空库验证、Beekeeper SSH Tunnel。
3. 标记禁止重复执行事项。
4. 标记 P1-P4 的剩余任务和前置条件。
5. 输出下一条推荐 /goal。

严格禁止：
- 不连接 Mongo。
- 不连接 OA 源库。
- 不执行 PostgreSQL 写操作。
- 不修改生产服务器。
- 不做生产切流。

交付物：
- 当前状态表。
- 阻断项清单。
- 下一条推荐 /goal prompt。
```

## P1-06A：app Mongo 规范化导出工具

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/06a-mongo-export-tooling.md。
执行前读取 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md。

本次只做 P1-06A：app Mongo 只读规范化导出工具。

允许使用子代理：可以，但最多 3 个，且写入范围必须分开：
- 子代理 A：manifest schema、输出目录结构、runbook。
- 子代理 B：ApplicationStateStore 读取路径和 collection 导出代码。
- 子代理 C：导出 count/hash 校验和测试。

目标：
1. 优先从 app Mongo 备份/恢复测试库或只读 app Mongo 读取。
2. 复用 ApplicationStateStore，不手写 pickle/binary 解析。
3. 输出 manifest.json 和 NDJSON。
4. 输出 GridFS file manifest，但不上传 MinIO/S3。
5. 支持 dry-run。

范围：
- import_batches
- bank_transactions
- invoices
- file/import sessions/files
- workbench overrides
- workbench pair relations
- workbench candidate matches
- background_jobs 中仍有效任务
- GridFS files manifest

严格禁止：
- 不访问 OA 源数据库。
- 不写真实 Mongo URI。
- 不把 secret 写入 manifest 或日志。
- 不迁移生产数据。
- 不写 PostgreSQL 正式表。

交付物：
- 导出 CLI 或可执行工具骨架。
- manifest schema。
- NDJSON 输出规范。
- docs/operations/backend-refactor/data-migration-runbook.md 的导出章节。

验收：
- dry-run 可运行。
- 导出数量可校验。
- manifest 不包含 secret。
- git diff 中无真实 URI/password。
```

## P1-06B：PostgreSQL staging 导入和对账工具

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/06b-postgres-import-validation-tooling.md。
执行前读取 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md。

本次只做 P1-06B：PostgreSQL staging 导入与对账工具。

允许使用子代理：可以，但最多 3 个，且写入范围必须分开：
- 子代理 A：staging import CLI 和 batch/migration_run_id 隔离。
- 子代理 B：staging -> app/read_model/job/audit 转换草案。
- 子代理 C：count/hash/amount/month/status/file checksum 对账报告。

目标：
1. 基于 06A 的 manifest/NDJSON 导入 PostgreSQL staging。
2. 使用 manifest_id 或 migration_run_id 隔离每次导入。
3. 失败记录必须保留，不能静默跳过。
4. 对账报告必须能阻断差异。

严格禁止：
- 不访问 OA 源数据库。
- 不把数据直接写正式事实表，除非明确是 dry-run 隔离环境。
- 不吞掉导入失败。
- 不写 secret。

交付物：
- staging import CLI 或工具骨架。
- staging -> facts 转换设计。
- migration validation report template。
- data-migration-runbook 的导入和对账章节。

验收：
- 数量差异会失败。
- 金额差异会失败。
- checksum 抽样失败会失败。
- 报告能定位到对象类型、月份、状态、legacy id。
```

## P1-06C：数据迁移 dry-run 和对账报告

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/06c-data-migration-dry-run.md。
执行前读取 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md。

本次只做 P1-06C：数据迁移 dry-run 和报告。

允许使用子代理：谨慎允许。最多 2 个：
- 子代理 A：执行/整理 dry-run 步骤和分区准备。
- 子代理 B：整理对账报告和阻断项。

前置条件：
- 06A 导出工具已具备。
- 06B staging 导入工具已具备。
- PostgreSQL migration 0001-0007 已验证。

目标：
1. 从 app Mongo 备份/恢复测试库或只读 app Mongo 导出。
2. 写入 PostgreSQL staging。
3. 执行 staging -> 目标事实表转换 dry-run。
4. 生成 count/hash/amount/month/status/file checksum 报告。

严格禁止：
- 不切换生产 API。
- 不冻结 app Mongo。
- 不把 dry-run 结果当作正式事实源。
- 不访问 OA 源数据库。

交付物：
- migration dry-run report。
- 差异清单。
- go/no-go 初步结论。
- 下一步修复任务。

验收：
- 报告无未解释差异才允许进入正式迁移门禁。
- 有差异必须失败并列出定位信息。
```

## P1-06D：GridFS 到 MinIO/S3 文件迁移

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/06d-gridfs-minio-migration.md。
执行前读取 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md。

本次只做 P1-06D：app GridFS 到 MinIO/S3 的迁移工具和校验。

允许使用子代理：可以，但最多 3 个：
- 子代理 A：GridFS manifest 和对象命名策略。
- 子代理 B：MinIO/S3 上传工具和 dry-run。
- 子代理 C：checksum 抽样下载校验和 file_objects 元数据映射。

目标：
1. 只处理 app GridFS。
2. 设计稳定 object_key，不泄露业务敏感信息。
3. 支持 dry-run。
4. 上传后抽样下载校验 SHA-256。
5. 生成 legacy_gridfs_id -> file_object_id 映射。

严格禁止：
- 不访问 OA 源数据库。
- 不删除 GridFS 原文件。
- 不写 MinIO/S3 secret。
- 不跳过 checksum 失败。

交付物：
- 文件迁移工具或 runbook。
- file manifest 格式。
- MinIO/S3 object naming 规范。
- data-migration-runbook 文件迁移章节。
```

## P2-07A：Outbox publisher

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/07-outbox-queue-worker.md。
本次只做 P2-07A：PostgreSQL outbox publisher，不做 NATS 配置和 Worker 实现。
执行前读取 00-current-state-and-gates.md、outbox-and-jobs.md、0005_job_outbox.sql。

允许使用子代理：否，避免和 NATS/Worker 写入冲突。

目标：
1. 实现或设计 outbox publisher。
2. 从 job.outbox_events 拉取 pending/retrying。
3. 支持锁定、发布、ack 后标记 published。
4. 支持失败重试、dead_lettered。

严格禁止：
- 不解释业务 payload。
- 不直接写核心业务事实。
- 不访问 OA 源库。

交付物：
- publisher 模块或详细实现计划。
- 指标和错误处理说明。
- 测试或验证命令。
```

## P2-07B：NATS JetStream 配置

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/07-outbox-queue-worker.md。
本次只做 P2-07B：NATS JetStream stream、consumer、retry/backoff 配置方案。
执行前读取 00-current-state-and-gates.md 和 outbox-and-jobs.md。

允许使用子代理：否。

目标：
1. 定义 FINOPS_EVENTS、FINOPS_JOBS、FINOPS_DLQ。
2. 定义 import、oa-sync、file、read-model、search worker consumers。
3. 记录 ack、MaxDeliver、BackOff、DLQ 策略。
4. 输出 Docker Compose 或部署配置草案，如项目已有 deploy 约定则复用。

严格禁止：
- 不把 NATS credential 写入 git。
- 不把 NATS 当任务最终事实源。
- 不访问 OA 源库。

交付物：
- NATS 配置文档或 deploy 草案。
- 运维检查命令。
- 失败重放策略。
```

## P2-07C：Python Worker 消息协议

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/07-outbox-queue-worker.md。
本次只做 P2-07C：Python Worker 消息协议和状态更新，不实现 API 迁移。
执行前读取 00-current-state-and-gates.md、outbox-and-jobs.md、backend 现有 background job 代码。

允许使用子代理：可以，最多 2 个：
- 子代理 A：消息 envelope 和状态机。
- 子代理 B：attempt/heartbeat/dead letter 更新逻辑。

目标：
1. 统一 worker_task envelope。
2. Worker 启动时写 worker_attempts。
3. Worker 周期更新 heartbeat。
4. 成功/失败/重试/dead letter 状态落 PostgreSQL。

严格禁止：
- 不直接写高风险业务事实。
- 不跳过 attempt 记录。
- 不访问 OA 源库，除非通过现有只读同步逻辑并且任务明确授权。

交付物：
- Worker 协议实现或详细实现计划。
- 状态机测试。
- 失败重放说明。
```

## P2-07D：任务状态查询 API

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/07-outbox-queue-worker.md。
本次只做 P2-07D：任务状态查询 API，不做任务执行和生产切流。
执行前读取 00-current-state-and-gates.md、outbox-and-jobs.md、docs/dev/api-contracts.md。

允许使用子代理：否。

目标：
1. 设计或实现 Axum task status 查询 route。
2. 只读 PostgreSQL job.worker_tasks / worker_attempts。
3. 保持前端可用的状态字段。
4. 不暴露内部错误堆栈和 secret。

交付物：
- API contract。
- route/service/repository 边界。
- 测试 fixture。
```

## P2-08A：Workbench rows/snapshots rebuild

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/08-read-models-and-search.md。
本次只做 P2-08A：workbench_rows 和 workbench_snapshots 增量重建。
执行前读取 00-current-state-and-gates.md、read-models-and-search.md、0007_read_models_search.sql。

允许使用子代理：可以，最多 2 个：
- 子代理 A：workbench_rows rebuild 逻辑。
- 子代理 B：workbench_snapshots 聚合和 stale 标记。

目标：
1. 按 scope_month 增量重建。
2. 不在请求路径全量重建。
3. 支持 stale 标记和重建任务。
4. 输出可验证 SQL 或 Worker 任务设计。

严格禁止：
- 不扫描 OA 源库。
- 不实时拼 all-time 工作台。
```

## P2-08B：Search index rebuild

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/08-read-models-and-search.md。
本次只做 P2-08B：read_model.search_index_rows 增量重建。
执行前读取 00-current-state-and-gates.md、read-models-and-search.md、0007_read_models_search.sql。

允许使用子代理：否。

目标：
1. 建立 search_index_rows upsert/delete/rebuild 策略。
2. 使用 pg_trgm/GIN，不跨多事实表实时模糊查。
3. 支持 entity_type、scope_month、jump_target。
4. 输出滞后指标和 stale 策略。
```

## P2-08C：Cost/Tax read model rebuild

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/08-read-models-and-search.md。
本次只做 P2-08C：cost_statistics_read_models 和 tax_offset_read_models 重建。
执行前读取 00-current-state-and-gates.md、read-models-and-search.md、现有 cost/tax Python service。

允许使用子代理：可以，最多 2 个：
- 子代理 A：cost statistics read model。
- 子代理 B：tax offset read model。

目标：
1. 保持现有业务口径。
2. 按月份和影响范围增量重建。
3. all-time 汇总异步化。
4. 输出对账样例和测试 fixture。
```

## P2-08D：Stale 策略和重建调度

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/08-read-models-and-search.md。
本次只做 P2-08D：read model stale 策略和重建调度。
执行前读取 00-current-state-and-gates.md、read-models-and-search.md、outbox-and-jobs.md。

允许使用子代理：否。

目标：
1. 定义 stale_reason、source_versions、generated_at 口径。
2. 定义 read_model.rebuild_requested outbox payload。
3. 定义重建失败和重试策略。
4. 定义 API 遇到 stale/missing read model 的响应策略。
```

## P3-09A：低风险只读 API

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/09a-low-risk-read-apis.md。
执行前读取 00-current-state-and-gates.md、backend-refactor-inventory.md、docs/dev/api-contracts.md。

本次只做 P3-09A：health/settings/session/metadata 低风险只读 API。

允许使用子代理：否。

目标：
1. 冻结旧 Python API 契约。
2. 在 Axum 实现对应 route/service/repository。
3. 添加 contract fixture 或等价测试。
4. 不迁移导入、工作台、核销写操作。

验收：
- 前端调用契约不破坏。
- 旧 Python 与新 Axum 响应差异可解释。
```

## P3-09B：导入历史、文件元数据、upload preflight

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/09b-import-file-apis.md。
执行前读取 00-current-state-and-gates.md、docs/dev/api-contracts.md、0002_imports_files.sql。

本次只做 P3-09B：导入历史、文件元数据、upload preflight。

允许使用子代理：可以，最多 2 个：
- 子代理 A：导入历史和文件元数据只读 API。
- 子代理 B：upload preflight 和对象存储元数据契约。

严格禁止：
- 不迁移导入确认写入。
- 不上传真实生产文件，除非用户明确授权。
- 不访问 OA 源库。
```

## P3-09C：工作台只读和搜索 API

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/09c-workbench-read-apis.md。
执行前读取 00-current-state-and-gates.md、read-models-and-search.md、docs/dev/api-contracts.md。

本次只做 P3-09C：单月 workbench read model 和 search 只读 API。

允许使用子代理：可以，最多 2 个：
- 子代理 A：workbench month read API。
- 子代理 B：search API。

严格禁止：
- 不迁移核销确认写操作。
- 不在请求路径全量重建 read model。
- 不扫描 OA 源库。
```

## P3-09D：核销和异常写 API

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/09d-reconciliation-write-apis.md。
执行前读取 00-current-state-and-gates.md、outbox-and-jobs.md、read-models-and-search.md、docs/dev/api-contracts.md。

本次只做 P3-09D：核销、异常、免 OA 批次等高风险写 API。

允许使用子代理：谨慎允许，最多 2 个，且不能并行写同一 route/service/repository：
- 子代理 A：confirm/revoke reconciliation。
- 子代理 B：exception/no-OA batch。

前置条件：
- audit 可用。
- outbox 可用。
- read model rebuild 可用。
- 幂等策略可用。
- 低风险 API 已验证。

严格禁止：
- 不跳过事务边界。
- 不跳过 audit。
- 不跳过 outbox。
- 不在没有 dry-run 对账报告时迁移生产写路径。
```

## P4-10：观测、安全、备份、告警

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/10-observability-security-readiness.md。
执行前读取 00-current-state-and-gates.md、production-readiness-checklist.md、observability-and-alerting.md。

本次只做 P4-10：监控、备份、告警、安全 readiness。

允许使用子代理：可以，最多 4 个：
- 子代理 A：metrics/logs/tracing。
- 子代理 B：PostgreSQL backup/PITR/restore drill。
- 子代理 C：权限/RBAC/audit/security checklist。
- 子代理 D：压测基线和 Grafana dashboard 草案。

严格禁止：
- 不开放 PostgreSQL 公网。
- 不写 secret。
- 不做生产切流。
```

## P4-12：正式迁移 go/no-go 门禁

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/12-formal-migration-and-cutover-gates.md。
执行前读取 00-current-state-and-gates.md、production-readiness-checklist.md、所有 dry-run 报告。

本次只做 P4-12：正式迁移 go/no-go 门禁，不执行生产切流。

允许使用子代理：否。

目标：
1. 检查备份、恢复演练、dry-run 对账、文件 checksum、API 影子验证、压测和监控。
2. 输出 go/no-go。
3. 如 no-go，列出阻断项和修复 prompt。

严格禁止：
- 不迁移生产数据。
- 不冻结 app Mongo。
- 不切换 API。
```

## P4-11：切换和回滚

```text
/goal
执行 /Users/yu/Desktop/fin-ops-platform/docs/exec-plans/active/backend-refactor-prompts/11-cutover-and-rollback.md。
执行前读取 00-current-state-and-gates.md、12-formal-migration-and-cutover-gates.md 的 go 结论、cutover-and-rollback-runbook.md。

本次只允许在用户明确授权后执行 P4-11：切换和回滚流程。

允许使用子代理：否。生产切换必须由主代理串行执行和汇报。

硬性前置：
- P4-12 输出 go。
- 用户明确授权生产切换。
- 维护窗口确认。
- 回滚路径确认。
- 最新 app Mongo 备份确认。

严格禁止：
- 没有用户明确授权不得切流。
- 不删除 app Mongo。
- PostgreSQL 成为事实源后，不允许旧 Mongo 全量覆盖 PostgreSQL。
- 不开放 PostgreSQL 公网。

交付物：
- 切换执行记录。
- 观测结果。
- 回滚状态。
- app Mongo 冻结/归档状态。
```

