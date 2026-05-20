# 数据库迁移完整执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for parallel implementation tasks or `superpowers:executing-plans` for serial execution. Each phase below is written so it can be converted into Codex prompts. Do not skip phase gates.

**Goal:** 将 app 数据从 MongoDB 迁移到 PostgreSQL，并让 app 主读写接入 PostgreSQL，同时继续从 OA Mongo 只读读取 OA 数据。

**Architecture:** 使用 expand/backfill/dual-write/shadow-read/switch-read/contract 渐进迁移。第一版保留 Python API 和 `MongoOAAdapter`，新增 PostgreSQL schema、迁移工具、repository 层和双写/影子读能力；后续可再演进为 Axum/PostgreSQL 架构。

**Tech Stack:** Python 3 后端、pymongo、psycopg/asyncpg 或 SQLAlchemy Core、PostgreSQL 16、React/Vite 前端、MongoDB 4.2.6、unittest/Vitest。

---

## 全局执行原则

- 所有生产数据库操作先在 staging 演练。
- OA Mongo 只读，不写入、不建索引、不改集合、不跑修复脚本。
- app Mongo 正式迁移前必须完成 `mongodump`、checksum、staging restore。
- 所有 schema migration 只前进，不修改已发布 migration。
- 所有数据 backfill 先进入 `staging` schema，再转换到正式表。
- 所有写路径必须有幂等键、操作者、trace id、审计事件。
- 所有差异必须能定位到旧 id、新 id、对象类型、字段和样本 payload。
- 每一阶段都必须更新本文档或同目录阶段记录。

## 阶段 0：完整代码阅读和证据索引

目标：为后续 prompt 建立准确代码地图，避免凭记忆改迁移边界。

可并行任务：

- 任务 0.1：后端入口阅读
  - 读：`backend/src/fin_ops_platform/app/server.py`
  - 输出：所有 API route、调用的 service、持久化调用点、后台任务入口。
  - 验收：文档列出每个 API 组对应的 service 和 state store 方法。

- 任务 0.2：state store 阅读
  - 读：`backend/src/fin_ops_platform/services/state_store.py`
  - 输出：每个 `load_*`、`save_*`、`store_*`、`read_*`、`delete_*` 的数据集合、输入输出结构、写入方式。
  - 验收：文档列出 Mongo collection 到 PostgreSQL 目标表的逐项映射。

- 任务 0.3：OA adapter 阅读
  - 读：`backend/src/fin_ops_platform/services/mongo_oa_adapter.py`、`oa_adapter.py`、`oa_manual_import_service.py`、`oa_sync_service.py`
  - 输出：OA Mongo 查询集合、form_id、row_id 生成规则、附件缓存规则、状态归一化规则。
  - 验收：明确哪些字段需要进入 `app.oa_applications`，哪些只保留 JSONB。

- 任务 0.4：业务服务阅读
  - 读：`imports.py`、`import_file_service.py`、`workbench_*`、`no_oa_*`、`batch_accounting_service.py`、`turnover_*`、`tax_*`、`etc_*`、`cost_statistics_*`、`background_job_service.py`
  - 输出：每个服务的事实表、读模型、审计、缓存失效和异常路径。
  - 验收：阶段 2 schema 能覆盖所有服务的持久化需求。

- 任务 0.5：前端 API 阅读
  - 读：`web/src/features/**/api.ts`、主要页面 `web/src/pages/*.tsx`
  - 输出：前端依赖的 API path、DTO 字段、错误处理语义、长任务/进度处理。
  - 验收：迁移期间 API response 兼容清单完整。

- 任务 0.6：测试阅读
  - 读：`tests/test_state_store.py`、`tests/test_*api.py`、`tests/test_*service.py`、`web/src/test/*`
  - 输出：现有测试覆盖点、缺失迁移测试、可复用 fixture。
  - 验收：每个后续阶段都有明确测试入口。

串行 gate：

- 更新 `docs/database-migration/00-current-state-inventory.md`。
- 生成 `docs/database-migration/code-evidence-index.md`，记录文件、类、方法、迁移关注点。
- 不能进入阶段 1，除非 evidence index 覆盖全部后端服务和前端 API client。

## 阶段 1：生产只读盘点、备份和 staging 环境

目标：确认真实数据库状态可恢复，并准备 staging 演练环境。

可并行任务：

- 任务 1.1：app Mongo 全量备份
  - 在服务器执行 `mongodump --archive --gzip`。
  - 生成 SHA-256 checksum。
  - 记录 app Mongo collection count、dbStats、GridFS 文件数量和字节数。
  - 输出：`/data/backups/fin_ops/<timestamp>/...` 和备份日志。
  - 禁止：对 app Mongo 做删除、更新、索引变更。

- 任务 1.2：app Mongo staging restore
  - 将备份恢复到 staging Mongo 或同机不同库 `fin_ops_platform_app_restore_test`。
  - 比对 collection count、GridFS count、核心集合金额合计。
  - 输出：恢复演练报告。

- 任务 1.3：OA Mongo 只读快照
  - 只统计 `form_data_db.form_data`，记录 count、form_id 分布、modifiedTime 范围。
  - 如需备份，由 OA/DBA 提供或用只读账号导出；不得写 OA 库。
  - 输出：OA 只读盘点报告。

- 任务 1.4：PostgreSQL staging/prod 基础配置
  - 确认 PostgreSQL 16.12。
  - 创建或确认 `fin_ops` 数据库。
  - 建立账号：`fin_ops_migrator`、`fin_ops_api`、`fin_ops_worker`、`fin_ops_readonly`。
  - 启用扩展：`pgcrypto`、`pg_trgm`、`btree_gin`。
  - 输出：账号权限 SQL、扩展检查 SQL、连接测试结果。

- 任务 1.5：备份恢复策略
  - 配置 `pg_dump` 逻辑备份。
  - 评估 PITR：WAL 归档、base backup、恢复演练。
  - 输出：PostgreSQL 备份恢复 runbook。

串行 gate：

- app Mongo 备份可恢复。
- PostgreSQL staging migration 可运行。
- OA Mongo 只读边界确认。
- 没有这些结果，不允许执行任何 backfill 或双写。

## 阶段 2：PostgreSQL schema 和 migration 基础

目标：建立能承载 app 事实、read model、任务、审计和 staging 的 PostgreSQL 结构。

可并行任务：

- 任务 2.1：建立 migration 工具
  - 选择 Python migration 工具或 SQL migration 目录。
  - 建议路径：`backend/src/fin_ops_platform/postgres/migrations/` 或 `backend/migrations/`。
  - 新增命令：`python -m fin_ops_platform.app.main --db-migrate` 或独立 `scripts/postgres-migrate.py`。
  - 测试：空库执行到最新版本。

- 任务 2.2：schema 和基础表
  - 创建 schema：`app`、`read_model`、`job`、`audit`、`staging`。
  - 创建 `schema_migrations` 或使用工具自带迁移表。
  - 创建 `audit.events`、`job.outbox_events`。
  - 测试：重复运行不破坏已有 schema。

- 任务 2.3：导入、发票、流水表
  - 创建 `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects`。
  - 创建 `app.invoices`。
  - 创建 `app.bank_transactions`。
  - 创建唯一约束和核心索引。
  - 测试：金额 numeric 精度、旧 id 唯一、重复 source key 冲突。

- 任务 2.4：工作台和核销事实表
  - 创建 `app.workbench_pair_relations`、`app.workbench_pair_relation_history`。
  - 创建 `app.workbench_row_overrides`。
  - 创建 `app.workbench_exception_cases`、`app.workbench_exception_case_events`。
  - 创建 `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events`。
  - 测试：active relation row_ids GIN 查询、case_id 唯一、撤回历史保留。

- 任务 2.5：OA 投影和同步表
  - 创建 `app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`。
  - 创建 `app.oa_sync_runs`、`app.oa_sync_watermarks`。
  - 测试：`unique(oa_source_id, form_id)`、row_id 唯一、source_updated_at 查询。

- 任务 2.6：税金、ETC、往来款、设置和任务表
  - 创建 `app.tax_certified_import_*`。
  - 创建 `app.etc_*` 初版结构。
  - 创建 `app.turnover_relations`、`app.turnover_ledger_extras`。
  - 创建 `app.app_settings`。
  - 创建 `job.background_jobs`、`audit.app_health_alerts`。
  - 测试：snapshot JSONB 保留、主字段可查询。

- 任务 2.7：read model 表
  - 创建 `read_model.workbench_rows`、`read_model.workbench_snapshots`、`read_model.workbench_candidate_matches`。
  - 创建 `read_model.search_index_rows`。
  - 创建 `read_model.cost_statistics_read_models`、`read_model.tax_offset_read_models`。
  - 测试：模糊搜索索引、scope_month 查询、row_id 唯一。

串行 gate：

- migration 可在空库跑通。
- migration 可在已有库重复安全执行或明确失败原因。
- `psql` 可列出所有 schema、表、索引、扩展。
- 所有表有 owner 和最小权限 grant。

## 阶段 3：规范化导出和 staging 导入

目标：从 app Mongo 导出规范化数据，不手写解析 pickle，先落 PostgreSQL staging。

可并行任务：

- 任务 3.1：导出框架
  - 新增只读导出命令：`python -m fin_ops_platform.tools.export_app_mongo --output <dir>`。
  - 复用 `ApplicationStateStore` 加载 snapshot。
  - 输出 `manifest.json`、`*.ndjson`、`gridfs-files-manifest.ndjson`。
  - 测试：无 Mongo 配置时报清晰错误；导出目录已存在时拒绝覆盖或要求 `--force`。

- 任务 3.2：核心事实导出
  - 导出 `import_batches.ndjson`、`import_batch_rows.ndjson`、`invoices.ndjson`、`bank_transactions.ndjson`。
  - 字段必须包含旧 id、规范化金额、日期、状态、raw_payload。
  - 测试：当前生产样本导出数量等于 Mongo count。

- 任务 3.3：工作台和异常导出
  - 导出 `workbench_pair_relations.ndjson`、`workbench_pair_relation_history.ndjson`、`workbench_row_overrides.ndjson`、`workbench_exception_cases.ndjson`。
  - 导出 `no_oa_bank_batches.ndjson`、`no_oa_bank_batch_events.ndjson`。
  - 测试：active relation 数、row_ids 数、审计事件数一致。

- 任务 3.4：设置、任务、税金、ETC 导出
  - 导出 `app_settings.ndjson`、`background_jobs.ndjson`、`tax_certified_import_*.ndjson`、`etc_*.ndjson`、`turnover_*.ndjson`。
  - 测试：snapshot 中主字段存在，raw_payload 可 JSON 序列化。

- 任务 3.5：GridFS manifest
  - 导出 `gridfs-files-manifest.ndjson`。
  - 字段包含 gridfs id、filename、length、uploadDate、metadata、sha256 可选。
  - 阶段 3 不强制下载所有文件，但必须能抽样读取 checksum。

- 任务 3.6：staging 导入工具
  - 新增 `python -m fin_ops_platform.tools.import_postgres_staging --export-dir <dir>`。
  - 所有 NDJSON 先进入 `staging.mongo_*` 表。
  - 记录 export manifest、导入批次 id、校验状态。
  - 测试：重复导入同一 export 批次不会重复写 staging。

串行 gate：

- staging 表数量与 export manifest 一致。
- 任何 JSON 序列化失败、金额解析失败、日期解析失败都阻断正式转换。
- 导出命令不得写 Mongo。

## 阶段 4：staging 转正式表和对账

目标：把 staging 数据转换到 `app`、`read_model`、`job`、`audit` schema，并生成可审计对账报告。

可并行任务：

- 任务 4.1：旧 id 到新 UUID 映射
  - 创建 `staging.id_mappings`。
  - 对每类对象生成稳定 UUID。
  - 测试：同一旧 id 多次转换得到同一新 id。

- 任务 4.2：导入/流水/发票转换
  - 从 staging 写入 `app.import_batches`、`app.import_batch_rows`、`app.bank_transactions`、`app.invoices`。
  - 对金额、日期、状态做强校验。
  - 测试：数量、金额合计、月份分布与 Mongo 导出一致。

- 任务 4.3：工作台事实转换
  - 写入 `app.workbench_pair_relations`、history、overrides、exception cases、no OA batches。
  - 测试：active/reverted 状态数、row_ids、case_id 唯一性一致。

- 任务 4.4：设置、任务、税金、ETC 转换
  - 写入 `app.app_settings`、`job.background_jobs`、`app.tax_certified_import_*`、`app.etc_*`、`app.turnover_*`。
  - 测试：核心字段和 raw_payload 可读。

- 任务 4.5：read model 重建
  - 不依赖旧 Mongo read model 字节内容。
  - 从事实表和 OA 只读投影重建 `read_model.workbench_rows`。
  - 重建 `read_model.search_index_rows`。
  - 测试：单月工作台样本与旧 API 输出一致。

- 任务 4.6：对账报告
  - 生成 `migration_reconciliation_report.json` 和 Markdown 摘要。
  - 包含数量、金额、状态、月份、文件、样本差异。
  - 差异必须包含对象类型、旧 id、新 id、字段、旧值、新值。

串行 gate：

- 核心对象数量 100% 一致，除非有记录明确说明废弃原因。
- 金额合计差异必须为 0。
- 文件数量和抽样 checksum 通过。
- 工作台样本页面差异为 0 或有业务确认。

## 阶段 5：PostgreSQL repository 层和测试

目标：在当前 Python 后端中加入 PostgreSQL repository，而不是直接改散落业务逻辑。

可并行任务：

- 任务 5.1：数据库连接和配置
  - 新增配置读取：`DATABASE_URL`、`FIN_OPS_APP_STORAGE_BACKEND`、`FIN_OPS_APP_READ_BACKEND`。
  - 新增 PostgreSQL connection pool。
  - 测试：缺少配置时启动失败信息明确；Mongo 模式不要求 PostgreSQL。

- 任务 5.2：repository interface
  - 为 app state 定义接口，覆盖当前 `ApplicationStateStore` 的公共方法。
  - 初期可以用 Protocol 或 wrapper。
  - 测试：Mongo store 和 Postgres store 都符合接口。

- 任务 5.3：PostgresStateStore 基础读
  - 实现 `load_app_settings`、`load_background_jobs`、`load_bank_transaction_categories`、`load_*_read_models`。
  - 测试：从 PostgreSQL 读取后，现有 service 初始化结果与 Mongo snapshot 等价。

- 任务 5.4：PostgresStateStore 核心写
  - 实现设置保存、后台任务保存、工作台关系保存、覆盖保存、异常保存、候选保存、dirty scopes 保存。
  - 写操作必须事务化，并写 `audit.events` 或 outbox。
  - 测试：失败回滚、重复写幂等、并发版本冲突。

- 任务 5.5：文件读取兼容
  - 第一阶段支持 `gridfs://` 旧路径读取。
  - 新文件元数据写 PostgreSQL，但内容可继续进入 GridFS 或本地兼容路径，直到文件迁移阶段完成。
  - 测试：导入预览/确认可读取旧文件。

- 任务 5.6：测试迁移
  - 扩展 `tests/test_state_store.py`，覆盖 Postgres store。
  - 新增 integration tests 使用临时 PostgreSQL 或测试库。
  - 保持现有 Mongo fake 测试不破坏。

串行 gate：

- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` 在 Mongo 模式和 Postgres 模式都通过。
- `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v` 通过，或记录明确阻断。
- 所有写入 PostgreSQL 的路径有测试。

## 阶段 6：双写和影子读

目标：生产仍以 Mongo 为用户可见事实源，同时把写入复制到 PostgreSQL 并对读结果做差异报告。

串行任务：

- 任务 6.1：部署 `dual` 写配置
  - `FIN_OPS_APP_STORAGE_BACKEND=dual`
  - 用户读仍为 Mongo。
  - 所有 app 写操作先写 Mongo，PostgreSQL 写失败时记录差异和告警，不隐藏错误策略必须明确。

- 任务 6.2：写路径差异捕获
  - 每次双写生成 idempotency key。
  - 记录 Mongo 写结果、PostgreSQL 写结果、trace id、actor。
  - PostgreSQL 写失败进入 `job.dead_letters` 或 `audit.events`。

- 任务 6.3：影子读
  - `FIN_OPS_APP_READ_BACKEND=shadow`
  - 用户仍看 Mongo API 响应。
  - 后台执行 PostgreSQL 读，序列化成同 DTO 后比较。
  - 差异写入 `audit.shadow_read_diffs`。

- 任务 6.4：差异面板
  - 在 app health 或运维接口展示双写失败数、影子读差异数、最新差异样本。
  - 测试：故意制造差异，页面和 API 能显示。

可并行验证：

- 导入确认双写。
- 工作台确认/撤回双写。
- 设置更新双写。
- no OA 批次提交/撤回双写。
- 税金/ETC 导入双写。
- 后台任务状态双写。

串行 gate：

- 连续稳定窗口内无新增未解释差异。
- Mongo/PostgreSQL 数量和金额定时对账通过。
- 所有双写失败有补偿重放能力。

## 阶段 7：分模块切读到 PostgreSQL

目标：按低风险到高风险顺序让用户读 PostgreSQL。

切读顺序：

1. 健康检查、设置读取、权限展示。
2. 后台任务读取。
3. 导入历史、文件元数据。
4. 银行明细和发票基础查询。
5. 单月工作台 read model。
6. 全局搜索。
7. 成本统计和税金抵扣。
8. ETC 和历史修复。
9. 核销/工作台写操作读后确认。
10. 数据重置和运维操作。

每个模块执行步骤：

- 开启模块级 feature flag。
- 内部用户或指定账号切读。
- 收集 P95/P99、错误率、差异数。
- 扩大到全量。
- 保留回滚开关。

每个模块验收：

- API DTO 与前端期望兼容。
- 关键页面人工验收通过。
- 对应单元测试和集成测试通过。
- 查询有 `EXPLAIN ANALYZE` 记录。
- 无未解释差异。

## 阶段 8：切写到 PostgreSQL

目标：PostgreSQL 成为 app 主事实源，app Mongo 停止承载新写入。

串行任务：

- 任务 8.1：最终冻结点
  - 公告维护窗口。
  - 暂停导入确认、核销确认、数据重置、ETC 修复等写操作。
  - 等待后台任务完成或标记暂停。
  - 再做一次 app Mongo 全量备份和 PostgreSQL 备份。

- 任务 8.2：最终增量回放
  - 从双写差异表和时间窗口回放未同步事件。
  - 执行最终对账。
  - 确认差异为 0。

- 任务 8.3：配置切换
  - 设置 `FIN_OPS_APP_STORAGE_BACKEND=postgres`。
  - 设置 `FIN_OPS_APP_READ_BACKEND=postgres`。
  - 重启 fin-ops service。
  - 验证 `/health`、`/api/app-health`、核心页面。

- 任务 8.4：保留 Mongo 只读归档
  - app Mongo 不再写入。
  - 保留只读归档和备份。
  - OA Mongo 继续只读服务。

串行 gate：

- PostgreSQL 已成为唯一 app 写事实源。
- app Mongo 无新增写入。
- 核心页面和写操作通过验收。
- 回滚策略更新为补偿修复，不再允许 Mongo 覆盖 PostgreSQL。

## 阶段 9：文件存储迁移

目标：将 GridFS 文件迁出 app Mongo，避免 app Mongo 作为长期依赖。

可并行任务：

- 任务 9.1：对象存储准备
  - 准备 MinIO/S3 bucket。
  - 开启版本化、生命周期、访问账号。
  - 配置服务端凭据，不写入 git。

- 任务 9.2：GridFS 导出上传
  - 从 `import_file_blobs.files/chunks` 读取文件。
  - 计算 SHA-256。
  - 上传到 MinIO/S3。
  - 更新 `app.file_objects` 的 `storage_backend`、`object_key`、`sha256`。

- 任务 9.3：读取切换
  - 文件读取优先 S3，fallback GridFS。
  - 抽样下载 checksum 验证。
  - 稳定后移除 GridFS fallback。

串行 gate：

- 文件数量一致。
- 总字节数一致。
- 抽样和关键文件 checksum 一致。
- 导入预览、导出、ETC 附件功能通过。

## 阶段 10：收尾、监控和归档

目标：清理迁移期状态，让系统进入 PostgreSQL 长期运维。

可并行任务：

- 任务 10.1：监控
  - PostgreSQL 连接数、慢查询、deadlock、表大小、索引大小、backup age。
  - app DB query latency、双写/影子读开关应为关闭。
  - OA Mongo 只读同步滞后。

- 任务 10.2：文档
  - 更新 `README.md`、`ARCHITECTURE.md`、`backend/README.md`、`docs/dev/*`、`docs/operations/*`。
  - 标注 app Mongo 已归档，OA Mongo 只读仍有效。

- 任务 10.3：删除迁移期代码
  - 移除 dual-write 和 shadow-read 临时开关，或保留为明确运维工具。
  - 删除不再使用的 Mongo app 写路径。
  - 保留 Mongo 导出工具用于审计和回放。

- 任务 10.4：最终验收
  - 全量后端测试。
  - 前端测试和 build。
  - 生产 smoke test。
  - 备份恢复演练。
  - 压测报告。

最终完成条件：

- PostgreSQL 是 app 主业务事实源。
- app Mongo 已冻结归档。
- OA Mongo 仍只读读取，未被修改。
- 所有核心页面读写 PostgreSQL 正常。
- 文件读取不依赖 app Mongo，或有明确保留窗口和迁移计划。
- 备份、恢复、监控、告警和 runbook 完整。

## 建议后续 Codex prompt 拆分方式

串行 prompt：

1. “执行阶段 0，完整阅读代码并生成 `code-evidence-index.md`。”
2. “执行阶段 1.1-1.3，只读备份和 Mongo 盘点，不修改数据。”
3. “执行阶段 2，创建 PostgreSQL migration 和 schema 测试。”
4. “执行阶段 3，创建 Mongo 规范化导出和 staging 导入工具。”
5. “执行阶段 4，创建 staging 转正式表和对账报告。”
6. “执行阶段 5，加入 PostgreSQL repository 和测试。”
7. “执行阶段 6，加入 dual-write 和 shadow-read。”
8. “执行阶段 7，按模块切读。”
9. “执行阶段 8，生产切写。”
10. “执行阶段 9-10，文件迁移、监控、文档和清理。”

可并行 prompt：

- 阶段 2 可按表域并行：导入/流水/发票、工作台/异常、OA 投影、税金/ETC、read model。
- 阶段 3 可按导出对象并行：核心事实、工作台、税金/ETC、文件 manifest。
- 阶段 5 可按 repository 方法域并行，但必须共享同一个 interface 定义。
- 阶段 7 可按页面模块并行，但每个模块必须独立 feature flag 和回滚开关。
