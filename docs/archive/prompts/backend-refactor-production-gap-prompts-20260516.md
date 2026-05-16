# 后端 Axum + PostgreSQL 生产级重构缺口与 Codex 多任务 Prompt - 2026-05-16

本文只整理后续可交给 Codex/子代理执行的任务，不代表允许生产迁移、冻结 app Mongo 或切换 API。当前正式迁移门禁仍为 `NO_GO`。

## 当前代码结论

当前仓库已经有 Axum + PostgreSQL 的基础骨架、部分迁移 DDL、部分只读 API、部分工作台写 API、App Mongo 导出/staging 导入工具、GridFS 迁移工具雏形、outbox 表和 publisher 抽象、read model 只读查询。但距离生产级完全重构还有关键缺口：

1. Rust Axum 仍只覆盖一小部分路由。旧 Python `backend/src/fin_ops_platform/app/server.py` 仍承载大量 `/api/*`、`/imports/*`、`/matching/*`、`/projects/*`、`/ledgers/*`、`/integrations/oa/*` 等业务路由。
2. Axum 路由层没有统一 OA 鉴权、RBAC、权限中间件；写 API 仍从 JSON body 接收 `actor`，不是从可信 OA session 派生。
3. `NatsClientPlaceholder`、`RedisClientPlaceholder`、`S3ClientPlaceholder` 仍是占位实现；outbox publisher 没有实际 NATS 发布进程，worker 没有真实 PostgreSQL repository/consumer。
4. App Mongo 迁移工具目前只做到 export 和 staging rows，尚未把 staging 转成 `app.*` 事实表、`staging.legacy_id_map` 和正式 dry-run reconciliation。
5. GridFS -> MinIO/S3 仍缺 staging 实际执行报告、抽样下载 checksum、Rust 对象存储读写 API 的真实客户端。
6. read model/search 当前主要是 Axum 只读查询，没有从 PostgreSQL facts 可重复重建 `read_model.workbench_rows`、`read_model.search_index_rows`、cost/tax read models 的 worker。
7. P3-09D 写 API 有事务、audit、outbox、幂等骨架，但业务语义仍不完整：核销金额、状态回写、来源事实校验、特殊动作、preview 与 Python 行为对齐都未完成。
8. PostgreSQL schema 空库迁移已有基础，但需要带数据迁移验证、分区准备、SQLx/集成测试、PITR/restore drill。
9. P4-10/P4-12 仍未通过：readiness gate 当前 `NO_GO`，缺 PostgreSQL PITR、迁移 dry-run、文件 checksum、API shadow validation、NATS/worker replay、read model rebuild、monitoring alert、load test、cutover/rollback 证据。

## 所有子任务通用硬约束

- 不迁移生产数据，不冻结 app Mongo，不切换生产 API。
- 不开放 PostgreSQL 公网，不写 secret，不把 token/cookie/签名 URL 写入日志、报告或 fixture。
- 不绕过事务边界、audit、outbox、幂等和 read model rebuild。
- 没有实际 dry-run 对账报告前，不允许把生产写路径迁移到 Axum。
- 子代理并行时必须采用互斥写入范围，不得同时写同一 route/service/repository/migration/tool。
- 每个任务完成后至少运行相关测试、`git diff --check`，并说明未运行项。

---

## Prompt A：Axum OA 鉴权、RBAC、actor 可信化和路由保护

```text
目标：把 Rust Axum API 从“可访问骨架”推进到生产级安全边界。实现统一 OA session 解析、RBAC/权限校验、可信 actor 注入、CORS allowlist 和受保护路由策略。

执行前读取：
- AGENTS.md、README.md、ARCHITECTURE.md、docs/dev/api-contracts.md
- backend/src/fin_ops_platform/app/auth.py
- backend/src/fin_ops_platform/app/server.py 中 _handle_api_session_me、_route_requires_oa_access、_enforce_route_access 和 mutation permission 相关方法
- rust/fin-ops-api/crates/fin-ops-api/src/routes/mod.rs、low_risk_read.rs、workbench_writes.rs
- rust/fin-ops-api/crates/fin-ops-api/src/config/mod.rs、state.rs、middleware/*

写入范围：
- rust/fin-ops-api/crates/fin-ops-api/src/config/*
- rust/fin-ops-api/crates/fin-ops-api/src/middleware/* 或新增 auth 模块
- rust/fin-ops-api/crates/fin-ops-api/src/routes/* 的鉴权接入
- rust/fin-ops-api/crates/fin-ops-api/src/services/workbench_writes.rs 的 actor 来源改造
- docs/dev/api-contracts.md 和 Rust 单元/集成测试
不要改 migrations、migration scripts、outbox worker。

实现要求：
1. 建立 Axum `AuthenticatedSession`/extractor 或 middleware，从 Authorization/OA header 解析身份；未配置 adapter 时保持现有 503 错误形状。
2. 复刻 Python 受保护路由策略：除 `/healthz`、`/readyz`、必要内部 `/metrics` 和 `/api/session/me` 外，业务路由默认需 OA session。
3. 写 API 的 `actor` 必须来自 session.identity.username/user_id；body 中 actor 只能作为兼容字段，若存在且与 session 不一致应 400/403，不得信任前端 actor。
4. 支持 `can_access_app`、`can_mutate_data`、`can_admin_access` 或等价 permission policy；为 no-OA、turnover、bank category、settings/data reset 等写路由预留 route policy。
5. 将 `/metrics` 设为内部可访问：至少支持配置 `METRICS_REQUIRE_AUTH` 或反向代理内网标识，默认不要在公网裸露。
6. 将 `CorsLayer::permissive()` 改为配置化 allowlist；本地开发可以显式允许 localhost。
7. 审计事件和 outbox payload 中记录可信 actor、actor_type、request_id/trace_id，不记录 token/cookie。

验收：
- cargo fmt
- cargo test
- 新增测试覆盖：缺 Authorization、adapter 未配置、无权限、可读但不可写、body actor mismatch、CORS allowlist。
- 更新 docs/dev/api-contracts.md 中 actor 字段说明：生产写入以 session actor 为准。
```

## Prompt B：App Mongo staging -> PostgreSQL facts dry-run 迁移和对账

```text
目标：补齐 06A/06B/06C 的核心缺口，把 app Mongo export/staging rows 转换为 PostgreSQL app/read_model/job/audit 事实数据的 dry-run 管线，并输出可阻断 P4-12 的真实对账报告。

执行前读取：
- docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md
- docs/operations/backend-refactor/data-migration-runbook.md
- docs/operations/backend-refactor/migration-validation-report-template.md
- backend/src/fin_ops_platform/services/app_mongo_exporter.py
- backend/src/fin_ops_platform/services/app_mongo_staging_importer.py
- backend/src/fin_ops_platform/services/state_store.py
- rust/fin-ops-api/migrations/0001_*.sql 到 0008_*.sql

写入范围：
- backend/src/fin_ops_platform/services/app_mongo_*migration*.py 或新增 migration mapper modules
- scripts/tools/export_app_mongo.py、import_app_mongo_staging.py 或新增 dry-run CLI
- tests/test_app_mongo_*.py、tests/fixtures/*
- docs/operations/backend-refactor/migration-dry-run-report-template.md 或实际 dry-run 报告模板
除非发现 schema 缺陷，不改 Axum routes/services。

实现要求：
1. 为每个 Mongo dataset 建立显式 mapping 到 PostgreSQL target：bank transactions、invoices、OA applications/items/attachments、reconciliation cases/rows、workbench overrides、exceptions、no-OA batches、turnover、imports/files、settings、background jobs、tax/cost/read-model 源数据。
2. 不允许 `compare_metric_snapshots(metrics, metrics)` 这种自比较通过；必须分别计算 source、staging、target metrics。
3. 写入 staging -> facts 时创建/校验所需月分区，包括 bank_transactions、invoices、oa_applications、read_model partitions。
4. 维护 `staging.legacy_id_map`，覆盖率必须可报告：每条 source legacy id 对应 target schema/table/id。
5. dry-run 默认在临时 PostgreSQL 数据库或显式 `FIN_OPS_POSTGRES_MIGRATION_URL` 上执行；没有 `--execute` 不改数据库。
6. 对账维度至少包括 count、sha256/hash、amount sum、month distribution、status distribution、legacy id coverage、failed row reason。
7. 输出 secret-free markdown/json 报告；任一 blocker 输出 `NO_GO`。

验收：
- python3 -m pytest tests/test_app_mongo_exporter.py tests/test_app_mongo_staging_importer.py 以及新增迁移 mapper 测试
- 至少一个 fixture 端到端：NDJSON -> staging -> facts -> reconciliation report
- readiness gate 的 `migration_dry_run` 只能在真实 GO marker 和报告无 blocker 时通过。
```

## Prompt C：GridFS -> MinIO/S3 文件迁移与 Axum 文件对象 API

```text
目标：完成 06D 文件迁移和 Rust 文件对象访问能力：GridFS 文件可迁到 MinIO/S3，PostgreSQL `app.file_objects`/`import.files` 映射可信，Axum 能安全生成下载/访问结果。

执行前读取：
- backend/src/fin_ops_platform/services/app_gridfs_migration.py
- scripts/tools/migrate_gridfs_minio.py
- rust/fin-ops-api/crates/fin-ops-api/src/infra/s3.rs
- rust/fin-ops-api/crates/fin-ops-api/src/routes/import_files.rs、services/import_files.rs、repositories/import_files.rs
- rust/fin-ops-api/migrations/0002_import_files.sql
- docs/operations/backend-refactor/data-migration-runbook.md

写入范围：
- backend/src/fin_ops_platform/services/app_gridfs_migration.py、scripts/tools/migrate_gridfs_minio.py、tests/test_app_gridfs_migration.py
- rust/fin-ops-api/crates/fin-ops-api/src/infra/s3.rs
- Rust import file route/service/repository tests
- docs/operations/backend-refactor/gridfs-minio-migration-report-template.md
不要改 auth/RBAC、read model rebuild、outbox worker。

实现要求：
1. 用真实 S3/MinIO 客户端替换 `S3ClientPlaceholder`，配置不打印 secret。
2. 支持 dry-run、upload、抽样 download、sha256 验证、legacy_gridfs_id -> file_object_id/import_file_id 映射报告。
3. 失败文件要保留 reason，不得吞异常；支持断点重跑和幂等跳过已验证对象。
4. Axum 文件对象 API 不返回裸 secret；如需 presigned URL，必须短 TTL、可配置，并在日志/报告中脱敏。
5. 文件 checksum GO 报告必须覆盖 manifest checksum、样本下载 hash、缺失文件、重复文件、大小差异。

验收：
- python3 -m pytest tests/test_app_gridfs_migration.py
- cargo test -p fin-ops-api import_files
- 生成 secret-free checksum validation 报告模板，readiness gate `file_checksum` 只认 GO 报告。
```

## Prompt D：真实 NATS outbox publisher、worker consumer 和 dead-letter/replay

```text
目标：把 job.outbox_events / job.worker_tasks 从表结构和抽象推进到可运行链路：Axum 写事务提交 outbox，publisher 投递 NATS JetStream，worker 消费并更新任务状态，dead-letter 可观测可重放。

执行前读取：
- docs/architecture/backend-refactor/outbox-and-jobs.md
- rust/fin-ops-api/crates/fin-ops-api/src/jobs/outbox_publisher.rs
- rust/fin-ops-api/crates/fin-ops-api/src/infra/nats.rs、config/mod.rs、main.rs
- rust/fin-ops-api/crates/fin-ops-api/src/routes/task_status.rs、repositories/task_status.rs
- backend/src/fin_ops_platform/services/worker_task_protocol.py
- rust/fin-ops-api/migrations/0005_job_outbox.sql

写入范围：
- rust/fin-ops-api/crates/fin-ops-api/src/infra/nats.rs
- rust/fin-ops-api/crates/fin-ops-api/src/jobs/*，可新增 bin/cli
- backend/src/fin_ops_platform/services/worker_*，scripts/tools/*
- tests for outbox/worker protocol
不要改 workbench write business semantics、migration mapper、auth。

实现要求：
1. 新增真实 NATS/JetStream publisher，实现 `EventPublisher`，支持 message id/idempotency/trace id。
2. 提供 outbox publisher 可运行入口：一次发布模式、循环模式、graceful shutdown、配置 batch/backoff/max attempts。
3. claim/publish/mark published/retry/dead-letter 必须事务安全；publisher 崩溃后可重试。
4. Python 或 Rust worker consumer 必须有 concrete PostgreSQL repository，消费 task envelope，更新 `job.worker_tasks` phase/progress/error/nats sequence。
5. 支持 dead-letter 查询和人工 replay CLI；重放不得破坏幂等。
6. 输出 staging validation report 模板：pending->published->consumed、retry、dead-letter、replay 全覆盖。

验收：
- cargo test -p fin-ops-api outbox
- python3 -m pytest tests/test_worker_task_protocol.py 以及新增 concrete repo/consumer 测试
- 本地可用 fake publisher/consumer 测试；有 NATS 时可跑 staging smoke。
```

## Prompt E：read model/search/cost/tax rebuild worker

```text
目标：实现从 PostgreSQL app facts 可重复重建 read_model.workbench_rows、read_model.search_index_rows、workbench_snapshots、cost_statistics、tax_offset 的 worker，使 Axum 只读 API 不依赖 app Mongo。

执行前读取：
- docs/architecture/backend-refactor/read-models-and-search.md
- rust/fin-ops-api/migrations/0007_read_models_search.sql
- rust/fin-ops-api/crates/fin-ops-api/src/routes/read_models.rs、services/read_models.rs、repositories/read_models.rs
- backend/src/fin_ops_platform/services/workbench_read_model_service.py
- backend/src/fin_ops_platform/services/live_workbench_service.py
- backend/src/fin_ops_platform/services/cost_statistics*.py、tax_offset*.py
- rust/fin-ops-api/crates/fin-ops-api/src/repositories/workbench_writes.rs 中 enqueue_rebuild payload

写入范围：
- backend/src/fin_ops_platform/services/read_model_* 或 Rust jobs/read_model_*，选择一种并保持一致
- scripts/tools/rebuild_read_models.py 或 Rust bin
- tests for read model rebuild
- docs/operations/backend-refactor/read-model-rebuild-validation-report-template.md
不要改 API route shapes，除非补充 status 字段且保持兼容。

实现要求：
1. Worker 接收 `read_model.rebuild_requested` payload，按 scope_month/scope_key 增量或全量重建。
2. 重建前创建 read_model partitions；重建过程使用 temp table/swap 或事务，避免读到半成品。
3. 从 facts 计算 row_type、row_id、source_entity_type/id、amount、status、relation_case_id、exception_case_id、candidate_match_id、ignored/overrides。
4. search index 支持 q/scope/month/project/status，敏感字段脱敏规则与 Axum service 保持一致。
5. cost/tax read model 至少达到现有 Python API 所需字段；无法完全迁移的字段必须列入 blocker，不得静默空值。
6. 更新 workbench_snapshots stale、generated_at、rebuild_task_id、row_count、source versions。

验收：
- fixture facts -> rebuild -> Axum `/api/workbench`、`/api/search` 返回可比对结果
- stale scope 指标和 read_model_rebuild validation 报告可生成
- 相关 Python/Rust tests 通过。
```

## Prompt F：P3-09D 工作台高风险写 API 业务语义补齐

```text
目标：在已有 P3-09D 事务/audit/outbox/幂等骨架基础上，补齐核销、撤销、异常、免 OA 批次和特殊动作的真实业务语义，达到可 shadow 验证。

执行前读取：
- docs/dev/api-contracts.md 中 P3-09D
- backend/src/fin_ops_platform/app/server.py 中 /api/workbench/actions/*、/api/no-oa-bank-batches/*、/api/turnover-ledger/*
- backend/src/fin_ops_platform/services/workbench_*、no_oa_bank_batch*、turnover* 相关服务
- rust/fin-ops-api/crates/fin-ops-api/src/services/workbench_writes.rs
- rust/fin-ops-api/crates/fin-ops-api/src/repositories/workbench_writes.rs
- rust/fin-ops-api/migrations/0003_*.sql、0004_*.sql、0008_*.sql

写入范围：
- rust/fin-ops-api/crates/fin-ops-api/src/routes/workbench_writes.rs
- rust/fin-ops-api/crates/fin-ops-api/src/services/workbench_writes.rs
- rust/fin-ops-api/crates/fin-ops-api/src/repositories/workbench_writes.rs
- Rust tests and docs/dev/api-contracts.md
不要改 auth middleware、migration tools、outbox publisher implementation。

实现要求：
1. confirm/revoke 不得只插入 0 金额 case；必须从 app.bank_transactions/app.invoices/app.oa_* facts 校验来源、金额、方向、状态，计算 total_amount/difference/applied_amount。
2. 核销和撤销要更新相关 facts 的 written_off_amount/status 或明确写入 reconciliation rows 后由 read model 推导，二者必须与合同文档一致。
3. 读 model rows 只能作为定位/快照，不得成为事实源；必须回查 app facts 并锁定相关行。
4. 补齐 Python 已有但 Rust 缺少的 preview/special actions：confirm-link/preview、withdraw-link/preview、mark-exception、cash pass-through、cash ticket purchase、cancel-cash-special、update-bank-exception、oa-bank-exception、personal-advance-repayment。
5. no-OA batch submit/withdraw 必须校验权限、版本、状态流、audit trail、outbox scope；列表/详情读 API 如未迁移需列入 API prompt。
6. 所有写入必须单事务、幂等、audit、outbox，冲突返回 409，版本冲突可复现。

验收：
- cargo test -p fin-ops-api workbench_writes
- 新增 repository tests 覆盖金额、状态、幂等重放、版本冲突、audit/outbox 一致性
- 生成 Python vs Axum 写 API shadow/dry-run 对比清单，不触生产写路径。
```

## Prompt G：剩余业务 API 迁移和 Python vs Axum shadow validation

```text
目标：系统性迁移旧 Python server 中尚未覆盖的业务 API，并建立契约/影子验证，避免遗漏路由和响应字段。

执行前读取：
- backend/src/fin_ops_platform/app/server.py 全部 route dispatch 和 readiness_summary
- docs/dev/api-contracts.md
- docs/architecture/backend-refactor/api-migration-batches.md
- rust/fin-ops-api/crates/fin-ops-api/src/routes/*
- web/src 或前端调用 API 的位置，用 rg 搜索 endpoint 字符串

写入范围：
- 新增/修改 Rust routes/services/repositories，按业务域分文件
- tests/api contract fixtures
- scripts/tools/api_shadow_validate.py 或等价工具
- docs/dev/api-contracts.md、api-shadow-validation-report-template.md
不要改 migration mapper、outbox worker、auth internals。

实现要求：
1. 生成 route inventory：Python route、Rust route、前端引用、迁移状态、风险级别、owner。
2. 优先迁移：bank-details、no-OA list/detail、turnover-ledger、ETC import/reconciliation/batches、settings/project sync/data-reset、tax-offset、cost-statistics、projects/ledgers/reminders/imports/matching/OA sync 状态。
3. 每个 route 明确来源：PostgreSQL facts、read_model、job/outbox、object storage；不得回读 app Mongo。
4. 对每个迁移 route 建立 contract fixture：query/body、status、error shape、分页、空结果、权限失败。
5. shadow validation 工具同时请求旧 Python 和新 Axum staging，输出字段 diff、排序 diff、金额/日期格式 diff；任一未解释 diff 为 NO_GO。
6. 不确定字段不得猜；必须从 Python 服务或 docs/product-specs 追溯事实。

验收：
- cargo test
- shadow validation 工具可对本地双服务运行
- 输出 `api-shadow-validation-report-YYYYMMDD.md/json` 模板，readiness gate 可识别 GO/NO_GO。
```

## Prompt H：PostgreSQL backup/PITR、监控告警、压测和 P4 readiness 证据

```text
目标：补齐 P4-10 和 P4-12 的生产 readiness 证据，但仍不做生产切流。覆盖 PostgreSQL 备份/PITR/restore drill、Prometheus/Grafana/P0/P1 告警验证、load test baseline、readiness gate 自动化。

执行前读取：
- docs/operations/backend-refactor/production-readiness-checklist.md
- docs/operations/backend-refactor/observability-and-alerting.md
- docs/operations/backend-refactor/formal-migration-go-no-go-20260516.md
- scripts/tools/backend_refactor_readiness_gate.py
- deploy/backend-refactor/monitoring/*
- deploy/rollback-route.sh、deploy/set-feature-flag.sh

写入范围：
- docs/operations/backend-refactor/*readiness*、*pitr*、*monitoring*、*load-test*
- scripts/tools/*readiness*、load/shadow helper scripts
- deploy/backend-refactor/monitoring/*
- tests/test_backend_refactor_readiness_gate.py、tests/test_backend_refactor_ops_artifacts.py
不要改业务 API、migration mapper、worker 代码。

实现要求：
1. PostgreSQL backup/PITR runbook 必须包含 WAL archiving、base backup、restore drill、RPO/RTO、checksum、失败处理；不得包含 secret。
2. 告警验证必须实际覆盖 API 5xx/latency、PostgreSQL connectivity/replication/PITR、outbox backlog、worker failures/dead letters、read model stale、object storage errors、disk/cpu/memory。
3. Grafana dashboard JSON 和 Prometheus alert rules 要与 Rust/Python metrics 名称一致；不一致就改 metrics 或 dashboard。
4. load test baseline 记录 P50/P95/P99、error rate、DB pool、NATS/outbox、worker lag、read model stale_seconds；给出 GO/NO_GO。
5. readiness gate 增强为可机器读 JSON，所有 evidence 文件必须 secret-free 且包含 GO/NO_GO marker。
6. 明确 P4-11 仍需用户授权、维护窗口、最新 app Mongo 备份、rollback drill 通过后才能执行。

验收：
- python3 -m pytest tests/test_backend_refactor_readiness_gate.py tests/test_backend_refactor_ops_artifacts.py
- readiness gate 在缺证据时仍 NO_GO，在 fixture GO 证据下可通过
- 生成或更新对应报告模板。
```

## Prompt I：正式 go/no-go 和 cutover/rollback 串行执行准备

```text
目标：只在所有 P0/P1 阻断项完成后，串行执行 P4-12 go/no-go 复核和 P4-11 切换准备；除非用户明确授权，不执行生产切换。

执行前读取：
- docs/exec-plans/active/backend-refactor-prompts/12-formal-migration-and-cutover-gates.md
- docs/exec-plans/active/backend-refactor-prompts/11-cutover-and-rollback.md
- docs/operations/backend-refactor/cutover-and-rollback-runbook.md
- 所有 dry-run、file checksum、API shadow、NATS/worker、read model、monitoring、load test、PITR/restore drill 报告
- scripts/tools/backend_refactor_readiness_gate.py

写入范围：
- docs/operations/backend-refactor/formal-migration-go-no-go-*.md/json
- docs/operations/backend-refactor/cutover-execution-record-*.md/json
- 不改业务代码，除非 readiness gate 脚本证据解析有 bug

执行要求：
1. 先运行 readiness gate；任一阻断为 NO_GO，停止，不请求生产切换授权。
2. 复核：最新 app Mongo 备份、PostgreSQL backup/PITR、migration dry-run、file checksum、API shadow、NATS replay、read model rebuild、load test、monitoring alerts、rollback drill、维护窗口。
3. 输出 GO/NO_GO。若 NO_GO，列阻断项、证据路径、修复 prompt。
4. 只有 GO 且用户明确授权生产切换、维护窗口确认、回滚路径确认、最新 app Mongo 备份确认后，才可进入 P4-11。
5. P4-11 串行执行：切读、观察、切写、观察、冻结/归档 app Mongo；每步记录时间、操作者、指标、回滚点。
6. 禁止删除 app Mongo；PostgreSQL 成为事实源后，禁止旧 Mongo 全量覆盖 PostgreSQL。

验收：
- 生产切换前必须输出可审计 go/no-go 报告
- 没有用户明确授权时，不执行任何切流命令
- 如进入切换，输出切换执行记录、观测结果、回滚状态、app Mongo 冻结/归档状态。
```
