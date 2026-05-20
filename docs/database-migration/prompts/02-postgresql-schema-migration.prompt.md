# 02 阶段 Codex 执行 Prompt：PostgreSQL schema 和 migration 基础

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 02：基于阶段 00 代码证据索引和阶段 01 生产备份/restore gate，通过代码和 SQL migration 建立 PostgreSQL schema/migration 基础，使 `fin_ops` 能承载 app 事实、read model、后台任务、审计和 staging 结构。阶段 02 完成后，migration 能在空库跑通，并能在已有库重复安全执行或明确失败；但本阶段不导出 Mongo 数据、不 backfill、不 dual-write、不切换应用读写路径。

你必须遵守以下硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。本阶段不需要连接 OA Mongo；不得写入、建索引、修复、清洗、备份或读取业务正文。
2. 生产 app Mongo `fin_ops_platform_app` 禁止写入。本阶段不需要连接 app Mongo；不得执行导出、backfill、修复、清洗、索引或 restore。
3. 禁止执行数据迁移：不从 Mongo 读取业务数据写入 PostgreSQL，不写 app 业务行，不执行 dual-write/shadow-read/switch-read。
4. PostgreSQL 只允许执行阶段 02 范围内的 DDL 和 migration 元数据写入：
   - 创建/确认 extension、schema、table、index、constraint、grant。
   - 写入 migration 工具自己的 `schema_migrations` 记录。
   - 测试 insert 只允许在本地/临时库或事务 rollback 中执行；不得向生产 `fin_ops` 写业务样例行。
5. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码或 prompt。
6. 不修改前端业务功能，不修改现有 API DTO，不修改生产服务配置，不重启服务器服务。
7. 所有生产 PostgreSQL DDL 必须可审计：先生成 migration 文件和 dry-run/plan，再执行；执行前必须确认目标库是 `fin_ops`，且目标 schema/table 不存在或 migration id 未应用。
8. 如果无法安全连接 PostgreSQL，或发现 `fin_ops` 中已有同名业务 schema/table 且来源不明，立即停止并记录 `BLOCKED`。
9. 如果阶段 02 发现目标表设计与阶段 00 证据冲突，先更新文档中的待决问题，不要强行创建错误 schema。

阶段 01 已通过的事实：

- app Mongo 备份完成：
  - Archive：`/data/backups/fin_ops/20260520013830/fin_ops_platform_app_20260520013830.archive.gz`
  - SHA-256：`c25d9780fded4c4407c29df16796fec2c99d63d201e24daf53ccab98e23f8b48`
- app Mongo staging restore 完成：
  - Restore DB：`fin_ops_platform_app_restore_20260520013830`
  - collections、objects、GridFS files/chunks/total length 与生产库一致。
- OA Mongo 只读统计完成，未写入。
- PostgreSQL：
  - version：PostgreSQL 16.12
  - database：`fin_ops`
  - extensions：`pgcrypto`、`pg_trgm`、`btree_gin`、`plpgsql` 已存在。
  - roles：`fin_ops_migrator`、`fin_ops_api`、`fin_ops_worker`、`fin_ops_readonly` 已存在。
  - `archive_mode=off`，PITR 未配置；不阻断阶段 02 schema migration，但正式 backfill/切库前必须处理。

服务器连接信息：

- 主机 IP：`139.155.5.132`
- 用户：`root`
- 协议：SSH
- 密码不写入 prompt 或文档；执行时由用户安全提供或使用已有 SSH 凭据。

必须先读的文档：

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `backend/README.md`
- `docs/index.md`
- `docs/database-migration/README.md`
- `docs/database-migration/00-current-state-inventory.md`
- `docs/database-migration/code-evidence-index.md`
- `docs/database-migration/01-production-backup-staging.md`
- `docs/database-migration/01-target-postgresql-design.md`
- `docs/database-migration/02-execution-plan.md`
- `docs/database-migration/prompts/00-code-evidence-inventory.prompt.md`
- `docs/database-migration/prompts/01-production-backup-staging.prompt.md`
- `docs/dev/backend.md`
- `docs/dev/testing.md`

必须先读的代码：

- `backend/src/fin_ops_platform/app/main.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/domain/models.py`
- `backend/src/fin_ops_platform/domain/enums.py`
- `backend/src/fin_ops_platform/services/imports.py`
- `backend/src/fin_ops_platform/services/import_file_service.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `backend/src/fin_ops_platform/services/workbench_exception_case_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_service.py`
- `backend/src/fin_ops_platform/services/etc_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_models.py`
- `backend/src/fin_ops_platform/services/background_job_service.py`
- `tests/test_state_store.py`

建议新增/修改路径：

- `backend/src/fin_ops_platform/postgres/`
- `backend/src/fin_ops_platform/postgres/migrations/`
- `backend/src/fin_ops_platform/postgres/migrate.py`
- `backend/src/fin_ops_platform/postgres/__main__.py`
- `tests/test_postgres_migrations.py`
- `docs/database-migration/02-postgresql-schema-migration.md`
- 必要时更新 `docs/database-migration/README.md`、`docs/index.md`

执行方式：

- 必须使用子代理并行完成可并行任务。
- 子代理可以读代码并在明确独立文件范围内写代码/SQL，但不得连接服务器、不得执行数据库命令。
- 所有服务器连接、PostgreSQL migration 执行、文档最终汇总必须由主线程串行完成。
- 多个子代理写文件时必须分配不重叠所有权，避免同一文件并发编辑。
- 主线程负责 review、合并、运行测试和最终文档。

串行步骤：

Step 0：建立工作基线

- 运行 `git status --short`。
- 读取所有参考文档和关键代码。
- 确认阶段 01 gate 是 `PASS`。
- 记录当前已有未提交变更；不得回滚用户或上一阶段改动。
- 确认本阶段允许修改 backend migration 代码、SQL migration、测试和数据库迁移文档；不修改现有业务行为。

Step 1：并行设计复核和任务拆分

可并行任务 1A：migration 工具方案复核

- 读取 `backend/README.md`、`main.py`、现有 scripts/tooling。
- 输出建议：
  - 使用独立 module 还是 CLI 参数。
  - 如何读取 `DATABASE_URL` 或安全连接参数。
  - 如何记录 migration id/checksum/applied_at。
  - 如何支持 `plan/status/apply`。
  - 如何避免在 Mongo/local_pickle 模式启动时要求 PostgreSQL。

可并行任务 1B：schema/table 设计复核

- 读取 `01-target-postgresql-design.md`、`code-evidence-index.md`、`domain/models.py`、`state_store.py`。
- 输出：
  - 需要创建的 schema。
  - 所有表分组和关键字段。
  - 必须拆列字段、JSONB 字段、约束和索引。
  - 与阶段 00 证据冲突或待决字段。

可并行任务 1C：测试策略复核

- 读取 `docs/dev/testing.md`、`tests/test_state_store.py`、现有后端测试结构。
- 输出：
  - migration runner 单元测试方案。
  - SQL migration 静态检查方案。
  - 临时 PostgreSQL 可用时的集成测试方案。
  - 无 PostgreSQL 环境时的 skip/降级方式。

主线程汇总后，确定文件所有权和 implementation plan。

Step 2：建立 migration 工具

建议实现：

- `backend/src/fin_ops_platform/postgres/__init__.py`
- `backend/src/fin_ops_platform/postgres/migrate.py`
- `backend/src/fin_ops_platform/postgres/__main__.py`
- migration SQL 目录：`backend/src/fin_ops_platform/postgres/migrations/`

工具要求：

- 支持命令：
  - `python -m fin_ops_platform.postgres.migrate status`
  - `python -m fin_ops_platform.postgres.migrate plan`
  - `python -m fin_ops_platform.postgres.migrate apply`
- 读取连接配置：
  - 优先 `DATABASE_URL`
  - 可选 `--database-url` 参数，但日志不得打印完整 URI。
- migration 文件命名：
  - `0001_extensions_and_schemas.sql`
  - `0002_core_imports_invoices_bank.sql`
  - `0003_workbench_relations_exceptions.sql`
  - `0004_oa_projection_sync.sql`
  - `0005_tax_etc_turnover_settings_jobs.sql`
  - `0006_read_models.sql`
  - `0007_grants.sql`
- 创建 migration 元数据表：
  - 建议 `public.schema_migrations` 或独立 `migration.schema_migrations`。
  - 字段至少包含 `version`、`name`、`checksum_sha256`、`applied_at`、`execution_ms`。
- apply 行为：
  - 按 version 排序。
  - 已应用且 checksum 一致则跳过。
  - 已应用但 checksum 不一致则失败。
  - 单个 migration 在事务中执行；如果 SQL 包含不能事务执行的语句，必须显式设计，不要隐式混用。
  - 默认不打印敏感连接信息。
- status/plan：
  - 列出 applied/pending、version、name、checksum。
  - 不连接时给出清晰错误。

依赖约束：

- 不新增重量级 ORM。
- 如使用 `psycopg`，先检查项目依赖是否已有；没有依赖时优先使用 `psql` subprocess 或标准库 + 可选依赖，并在文档中说明。
- 不要让现有 app 启动依赖 PostgreSQL migration 包。

Step 3：SQL migration 0001：extensions 和 schema

创建：

- extensions：`pgcrypto`、`pg_trgm`、`btree_gin`
- schema：`app`、`read_model`、`job`、`audit`、`staging`
- 基础表：
  - `audit.events`
  - `job.outbox_events`

要求：

- `create schema if not exists`。
- extension 使用 `create extension if not exists`。
- 基础表包含 `id uuid primary key default gen_random_uuid()`、时间戳、类型、scope、payload JSONB、status 等必要字段。
- `audit.events` 支持 actor、event_type、object_type、object_id、occurred_at、payload。
- `job.outbox_events` 支持 event_type、aggregate_type、aggregate_id、status、available_at、attempt_count、payload。
- 不创建业务样例数据。

Step 4：SQL migration 0002：导入、文件、发票、银行流水

创建：

- `app.import_batches`
- `app.import_batch_rows`
- `app.import_files`
- `app.file_objects`
- `app.invoices`
- `app.bank_transactions`
- `app.bank_transaction_categories`
- `app.bank_transaction_category_events`

要求：

- 所有 Mongo 迁入对象保留 `legacy_mongo_id text` 或对应 `legacy_*` 字段。
- 所有金额使用 `numeric`，禁止 float。
- 日期/time/scope month 按业务含义拆列。
- `raw_payload jsonb not null default '{}'::jsonb`。
- 建立核心唯一约束和索引：
  - import batch legacy id unique。
  - invoice source_unique_key/data_fingerprint partial unique。
  - bank source_unique_key/data_fingerprint partial unique。
  - month/date/status/source_batch 查询索引。
  - trigram 索引用于 counterparty/name/invoice text 字段。
- 文件表支持 GridFS legacy 引用和后续对象存储：`storage_backend`、`storage_uri`、`sha256`、`size_bytes`、`content_type`、`metadata`。

Step 5：SQL migration 0003：工作台、关系、异常、免 OA

创建：

- `app.workbench_pair_relations`
- `app.workbench_pair_relation_history`
- `app.workbench_row_overrides`
- `app.workbench_exception_cases`
- `app.workbench_exception_case_events`
- `app.no_oa_bank_batches`
- `app.no_oa_bank_batch_events`

要求：

- 保留 `case_id`、`relation_mode`、`status`、`version`、`month_scope`、`row_ids text[]`、`row_types text[]`、`amount_check jsonb`、`special_metadata jsonb`、`source_versions jsonb`、`raw_payload jsonb`。
- active relation 查询需要 GIN/BTREE 组合索引。
- exception case 保留 `case_id` unique、状态、business_line/scenario/resolution、candidate_ids、source_versions、history/audit payload。
- no OA batch 保留 `batch_id` unique、status/status_bucket、version、scope_month、account_key、total_amount、submitted/withdrawn 字段和 audit events。

Step 6：SQL migration 0004：OA 只读投影和同步

创建：

- `app.oa_applications`
- `app.oa_application_items`
- `app.oa_attachments`
- `app.oa_sync_runs`
- `app.oa_sync_watermarks`
- `app.oa_attachment_invoice_cache`
- `app.manual_oa_imports`

要求：

- 这些表是 app 自己的只读同步投影和缓存，不是 OA 源事实替代。
- 保留 `oa_source_id`、`form_id`、`form_type`、`row_id`、`status`、`applicant`、`project_name`、`amount`、`source_updated_at`、`normalized_payload`、`raw_payload`。
- `app.oa_applications.row_id` unique。
- `unique(oa_source_id, form_id)` 或能表达同等约束。
- attachment cache 必须保留 parser version、cache schema version、source attachment key、parsed_at、evidences/invoices/artifacts payload。
- manual OA imports 保留 row_id、source、actor、imported_at、audit payload。
- 不连接 OA Mongo，不读取 OA 数据，不写 `form_data_db`。

Step 7：SQL migration 0005：税金、ETC、往来、设置、任务、健康

创建：

- `app.tax_certified_import_sessions`
- `app.tax_certified_import_batches`
- `app.tax_certified_import_records`
- `app.etc_invoices`
- `app.etc_import_sessions`
- `app.etc_import_batches`
- `app.etc_submission_batches`
- `app.etc_business_batches`
- `app.etc_reconciliation_tasks`
- `app.etc_reconciliation_files`
- `app.historical_etc_repair_bundles`
- `app.historical_etc_repair_parsed_seeds`
- `app.historical_etc_repair_states`
- `app.turnover_relations`
- `app.turnover_relation_events`
- `app.turnover_ledger_extras`
- `app.app_settings`
- `job.background_jobs`
- `audit.app_health_alerts`

要求：

- 税金记录保留 certified unique key、invoice identity、tax amount、month scope、matched plan id、raw payload。
- ETC 表第一版允许较多 JSONB，但主字段必须拆列：invoice number、dates、amounts、status、batch ids、task id、business batch id、version、OA detection fields、file paths/hash。
- settings 表保留 singleton key、settings payload、updated_by、updated_at、version。
- background jobs 保留 job id、type、status、owner、visibility、source、affected_months、progress、result_summary、error、created/updated timestamps。
- app health alerts 保留 alert id、kind、scope、severity、status、active/recovered timestamps、payload。

Step 8：SQL migration 0006：read models

创建：

- `read_model.workbench_rows`
- `read_model.workbench_snapshots`
- `read_model.workbench_candidate_matches`
- `read_model.search_index_rows`
- `read_model.cost_statistics_read_models`
- `read_model.tax_offset_read_models`

要求：

- read model 表可重建，但要支持 shadow-read 和对账。
- 保留 scope month、scope key、row id、source kind、status、source_versions、generated_at、cache_status、payload JSONB。
- search index 支持 trigram/GIN 索引；字段覆盖 OA、bank、invoice 的文本搜索。
- cost/tax read model 保留 scope、project_scope、payload、generated_at、entry_count/source counts。

Step 9：SQL migration 0007：grants 和 owner 策略

要求：

- 确认 roles：`fin_ops_migrator`、`fin_ops_api`、`fin_ops_worker`、`fin_ops_readonly`。
- 不在 migration 中设置或输出密码。
- grant 原则：
  - `fin_ops_migrator`：DDL owner 或 migration 执行者。
  - `fin_ops_api`：读写 app/read_model 必要表，读 job 必要状态，不给 DDL。
  - `fin_ops_worker`：读写 job/outbox/read_model/app 必要表。
  - `fin_ops_readonly`：select。
- 如果当前 role 权限不足或 owner 策略无法安全确认，migration 可以创建 grant SQL 但不要强行执行；记录 `BLOCKED` 或 `manual step required`。

Step 10：测试

新增或更新测试：

- migration discovery：
  - migration 文件按 version 排序。
  - checksum 稳定。
  - 修改已应用 migration checksum 会失败。
- SQL static checks：
  - 所有 migration 文件不包含 `drop database`、`drop schema`、`drop table`、`truncate`、`delete from`、`insert into app.` 样例业务数据。
  - 所有核心表包含 `raw_payload jsonb` 或明确豁免。
  - 所有 schema/table 命名符合 `app/read_model/job/audit/staging` 分层。
- runner behavior：
  - status/plan 不修改数据库。
  - apply 对已应用 migration 幂等跳过。
- PostgreSQL integration：
  - 如果可用测试 PostgreSQL，则在临时数据库跑完整 migration。
  - 如果不可用，测试应明确 skip，不能假绿。

建议命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres.migrate plan
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

Step 11：服务器 PostgreSQL 执行策略

先本地验证，再决定是否连接服务器执行 migration。

如果执行服务器 migration：

- 只能连接 `139.155.5.132` 上的 PostgreSQL `fin_ops`。
- 执行前运行：
  - PostgreSQL version。
  - current_database。
  - current_user。
  - 已存在 schema/table 列表。
  - extension 列表。
- 必须先运行 `plan/status`。
- `apply` 只允许执行阶段 02 migration DDL。
- 执行后验证：
  - schema：`app`、`read_model`、`job`、`audit`、`staging`。
  - migration table 记录。
  - 表、索引、constraint 数量。
  - extension 状态。
  - role grants 摘要。
- 不写业务行，不执行 backfill。

如果不执行服务器 migration：

- 仍需生成 migration 文件和本地测试。
- 阶段 02 文档标记 gate 为 `BLOCKED` 或 `READY_NOT_APPLIED`，并说明未执行的原因。

Step 12：更新文档

新增：

- `docs/database-migration/02-postgresql-schema-migration.md`

必要时更新：

- `docs/database-migration/README.md`
- `docs/database-migration/02-execution-plan.md`
- `docs/index.md`

文档必须包含：

1. 执行摘要：是否创建 migration 工具、是否生成 SQL migration、是否执行服务器 migration。
2. 阶段 01 输入：备份路径、restore DB、PostgreSQL 基础状态。
3. migration 文件清单和每个文件负责的 schema/table。
4. schema/table/index/grant 摘要。
5. 执行过的 PostgreSQL DDL 范围。
6. 明确未执行：Mongo 导出、backfill、dual-write、切读、OA Mongo 写入。
7. 测试结果。
8. 阶段 02 gate：
   - `PASS`：migration 可在空库跑通，已有库重复安全，schema/table/index/grant 可列出。
   - `READY_NOT_APPLIED`：代码和 SQL 已完成，但未执行服务器 migration。
   - `BLOCKED`：列出阻断项。
9. 阶段 03 前置条件：规范化导出设计、staging import、对账报告、PITR/备份补齐要求。

Step 13：验证

本地必须运行：

```bash
find docs/database-migration -maxdepth 2 -type f -name '*.md' | sort
rg -n "(PASSWORD|SECRET|TOKEN|KEY|URI)=.*[A-Za-z0-9]|DATABASE_URL=.*[:][/][/]|mongodb:[/][/]|postgres:[/][/]" docs/database-migration backend tests docs/index.md || true
rg -n 'mongodb:[/][/][^`[:space:]]+@|postgres:[/][/][^`[:space:]]+@' docs/database-migration backend tests docs/index.md || true
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
git diff -- backend tests docs/database-migration docs/index.md
git status --short
```

如果实现了 migration runner，还需运行：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres.migrate plan
```

如果有可用 PostgreSQL 测试库，还需运行完整 apply 验证并在文档记录：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres.migrate apply
PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres.migrate status
```

任何敏感信息扫描命中必须立即清理并重新运行扫描。

Step 14：最终输出

最终回答必须包含：

- 修改了哪些文件。
- 子代理并行完成了哪些任务。
- 是否连接服务器。
- 是否写入数据库：
  - MongoDB：必须说明没有写入 app Mongo/OA Mongo。
  - PostgreSQL：列出是否执行 DDL；如果执行，列出 schema/table/grant 范围；如果未执行，说明原因。
- migration 文件清单。
- 测试和验证命令结果。
- 阶段 02 gate：`PASS`、`READY_NOT_APPLIED` 或 `BLOCKED`。
- 如果 `PASS`，说明可以进入阶段 03：规范化导出和 staging 导入。

停止条件：

- 任何步骤需要写 OA Mongo 或 app Mongo。
- 任何步骤需要把 Mongo 数据写入 PostgreSQL。
- PostgreSQL 目标库不是 `fin_ops` 或无法确认。
- 已有 schema/table 与 migration 设计冲突且来源不明。
- migration runner 无法避免已应用 migration checksum drift。
- 敏感信息扫描发现密码、token、secret、完整 URI 且无法清理。
```
