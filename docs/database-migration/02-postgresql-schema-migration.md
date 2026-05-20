# 阶段 02：PostgreSQL schema 和 migration 基础

本文记录 2026-05-20 执行阶段 02 的结果。阶段目标是建立 PostgreSQL DDL/migration 基础，使 `fin_ops` 后续能承载 app 事实、read model、后台任务、审计和 staging 结构。

## 执行摘要

| 项 | 结果 |
| --- | --- |
| 执行时间 | 2026-05-20 CST |
| 本地 migration runner | 完成 |
| SQL migration 文件 | 完成 `0001` 至 `0007` |
| Mongo/OA 访问 | 未连接、未读取、未写入 |
| 业务数据迁移 | 未执行 |
| 本地专项测试 | 通过 |
| app readiness | 通过 |
| 后端全量单测 | 通过 |
| 服务器 PostgreSQL apply | 已执行 |
| 阶段 02 gate | `PASS` |

本阶段没有导出 Mongo 数据，没有 backfill，没有 dual-write，没有 shadow-read，没有切换应用读写路径，没有重启服务器服务。

## 并行复核

本阶段按 prompt 使用 3 个只读子代理并行复核，子代理均未写文件、未连接服务器或数据库：

- migration 工具复核：确认应放在独立 `fin_ops_platform.postgres` module，避免接入 `fin_ops_platform.app.main` 后触发 `Application`、`ApplicationStateStore`、Mongo/OA adapter 初始化。
- schema/table 复核：确认 DDL 覆盖导入、文件、发票、流水、matching、工作台、异常、免 OA、OA 投影、税金、ETC、往来、设置、任务、健康、read model 和 staging。
- 测试策略复核：确认新增无数据库依赖的静态/单元测试，服务器执行前必须通过本地 gate，SQL 禁止危险 DDL/DML 和敏感信息。

## 新增文件

| 文件 | 说明 |
| --- | --- |
| `backend/src/fin_ops_platform/postgres/__init__.py` | PostgreSQL migration package。 |
| `backend/src/fin_ops_platform/postgres/__main__.py` | 支持 `python -m fin_ops_platform.postgres`。 |
| `backend/src/fin_ops_platform/postgres/migrate.py` | 独立 migration runner，支持 `plan/status/apply`。 |
| `backend/src/fin_ops_platform/postgres/migrations/0001_extensions_and_schemas.sql` | extensions、schema、audit/job 基础表、staging 基础表。 |
| `backend/src/fin_ops_platform/postgres/migrations/0002_core_imports_invoices_bank.sql` | 导入、文件、发票、银行流水和分类表。 |
| `backend/src/fin_ops_platform/postgres/migrations/0003_workbench_relations_exceptions.sql` | matching、工作台关系、异常、免 OA、dirty scope。 |
| `backend/src/fin_ops_platform/postgres/migrations/0004_oa_projection_sync.sql` | OA 只读投影、附件、同步状态、附件发票缓存、手工导入。 |
| `backend/src/fin_ops_platform/postgres/migrations/0005_tax_etc_turnover_settings_jobs.sql` | 税金、ETC、往来、设置、后台任务、健康告警。 |
| `backend/src/fin_ops_platform/postgres/migrations/0006_read_models.sql` | 工作台、搜索、成本统计、税金抵扣 read model。 |
| `backend/src/fin_ops_platform/postgres/migrations/0007_grants.sql` | `fin_ops_*` 角色的最小权限 grant，角色不存在时跳过。 |
| `tests/test_postgres_migrations.py` | migration runner 和 SQL 静态测试。 |

## Migration runner 行为

命令：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres plan
PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres status
PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres apply
```

关键约束：

- `plan` 无 `DATABASE_URL` 时只读取本地 SQL，不连接数据库。
- `status/apply` 需要 `DATABASE_URL` 或 `--database-url`。
- runner 不 import `fin_ops_platform.app.server`，不构造 `Application`，不触发 Mongo/OA 初始化。
- `psql` subprocess 使用 `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD` 环境变量，不把完整连接 URI 放入 argv。
- `apply` 只允许默认应用到 `fin_ops`；一次性测试库必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1` 且库名包含 `test`。
- migration 元数据表为 `public.schema_migrations`，字段包含 `version`、`name`、`checksum_sha256`、`applied_at`、`execution_ms`、`metadata`。
- 已应用版本 checksum 一致则跳过；checksum 不一致则失败。
- 每个 migration 在事务内执行，并使用 transaction-level advisory lock。

## Plan/Status 输出

本地离线 `plan` 输出如下；服务器 apply 前也显示 0001-0007 均为 pending：

```text
0001 pending extensions_and_schemas 32ea9c113b306d351fdaa2f3344da0014bcd9a9dfd1c6471d2777a72542d9328
0002 pending core_imports_invoices_bank b16b4b32ff8a219dfbb321a6e43b6b7801bab031a8469d97b40236f75fe68cf2
0003 pending workbench_relations_exceptions 5c9f2bb477d6537eb350c70bf251bc62916e81b7a0036899625a45b8cd8ab8b8
0004 pending oa_projection_sync 3f358b0a830f6de933c4b15f27987c83d1e2be076833585c574685b5121d65f3
0005 pending tax_etc_turnover_settings_jobs 46d92cb88233997fa1a04bfb941c79e24cfb3da50779e7edfd9915ba86e6befa
0006 pending read_models c9707b4f2a32b834fb4703e6dbd15ae1e9e536fe19cdf1a247292ee5742d9ef5
0007 pending grants 2a10c903e5daa5d8a30c8d3e9d3aa357306f7f24e058b826fee64419e8f8c2ac
```

服务器 apply 后 `status` 输出如下：

```text
0001 applied extensions_and_schemas 32ea9c113b306d351fdaa2f3344da0014bcd9a9dfd1c6471d2777a72542d9328
0002 applied core_imports_invoices_bank b16b4b32ff8a219dfbb321a6e43b6b7801bab031a8469d97b40236f75fe68cf2
0003 applied workbench_relations_exceptions 5c9f2bb477d6537eb350c70bf251bc62916e81b7a0036899625a45b8cd8ab8b8
0004 applied oa_projection_sync 3f358b0a830f6de933c4b15f27987c83d1e2be076833585c574685b5121d65f3
0005 applied tax_etc_turnover_settings_jobs 46d92cb88233997fa1a04bfb941c79e24cfb3da50779e7edfd9915ba86e6befa
0006 applied read_models c9707b4f2a32b834fb4703e6dbd15ae1e9e536fe19cdf1a247292ee5742d9ef5
0007 applied grants 2a10c903e5daa5d8a30c8d3e9d3aa357306f7f24e058b826fee64419e8f8c2ac
```

## Schema 覆盖

创建的 schema：

- `app`
- `read_model`
- `job`
- `audit`
- `staging`

表分组：

- `audit.events`、`audit.app_health_alerts`
- `job.outbox_events`、`job.background_jobs`、`job.workbench_matching_dirty_scopes`
- `staging.mongo_exports`、`staging.mongo_raw_records`、`staging.id_mappings`
- `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects`
- `app.invoices`、`app.bank_transactions`、`app.bank_transaction_categories`、`app.bank_transaction_category_events`
- `app.matching_runs`、`app.matching_results`
- `app.workbench_pair_relations`、`app.workbench_pair_relation_history`、`app.workbench_row_overrides`
- `app.workbench_exception_cases`、`app.workbench_exception_case_events`
- `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events`
- `app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`
- `app.oa_sync_runs`、`app.oa_sync_watermarks`、`app.oa_attachment_invoice_cache`、`app.manual_oa_imports`
- `app.tax_certified_import_sessions`、`app.tax_certified_import_batches`、`app.tax_certified_import_records`
- `app.etc_invoices`、`app.etc_import_sessions`、`app.etc_import_batches`、`app.etc_submission_batches`、`app.etc_business_batches`、`app.etc_reconciliation_tasks`、`app.etc_reconciliation_files`
- `app.historical_etc_repair_bundles`、`app.historical_etc_repair_parsed_seeds`、`app.historical_etc_repair_states`
- `app.turnover_relations`、`app.turnover_relation_events`、`app.turnover_ledger_extras`、`app.app_settings`
- `read_model.workbench_rows`、`read_model.workbench_snapshots`、`read_model.workbench_candidate_matches`
- `read_model.search_index_rows`、`read_model.cost_statistics_read_models`、`read_model.tax_offset_read_models`

设计要点：

- 所有核心表使用 `uuid primary key default gen_random_uuid()`。
- Mongo 迁入对象保留 `legacy_mongo_id` 或对应 `legacy_*` 字段。
- OA 投影保留 `oa_source_id`、`form_id`、`row_id`、`source_updated_at`、`normalized_payload`、`raw_payload`。
- 金额使用 `numeric(20, 6)`；没有使用 float/real/double precision/money。
- 业务扩展字段和迁移保留字段使用 `jsonb`。
- 发票、流水、关系、OA、搜索、read model 建立 partial unique、BTREE、GIN 和 trigram 索引。
- `0007_grants.sql` 不创建用户/角色，不记录密码，只对阶段 01 已确认的角色做条件 grant。

## 验证记录

已通过：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres plan
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

敏感信息和危险 SQL 静态规则已纳入 `tests/test_postgres_migrations.py`，并对 migration 目录和 runner 执行了额外 `rg` 抽查。

后端全量单测结果：

- Ran 1118 tests
- OK
- Skipped：5

## 服务器执行状态

已执行服务器 PostgreSQL migration。

执行前：

- `origin/main` 已合入当前分支，解除上一轮全量测试 gate。
- 目标库确认：`fin_ops`。
- 执行用户：本机 `postgres` 系统用户通过 Unix socket 连接。
- 目标 schema `app/read_model/job/audit/staging` 已存在但无表。
- `public.schema_migrations` apply 前不存在。
- `fin_ops_migrator`、`fin_ops_api`、`fin_ops_worker`、`fin_ops_readonly` 角色存在。

DDL 前备份：

| 项 | 值 |
| --- | --- |
| 备份目录 | `/data/backups/fin_ops/postgres_phase02_20260520024253` |
| Dump | `/data/backups/fin_ops/postgres_phase02_20260520024253/fin_ops_pre_phase02_20260520024253.dump` |
| SHA-256 | `60d641bde7392ca59b25aef26b46f1aede9daafd293d829ce6ed247501d92319` |
| 格式 | `pg_dump -Fc` |

执行结果：

- `0001` 到 `0007` 全部 applied。
- 修正 runner 的 `schema_migrations` 存在性判断后，远端 `status` 显示 0001-0007 全部 applied。
- 再次执行 `apply`，0001-0007 全部 skipped，验证重复执行安全。
- `public.schema_migrations` 行数为 7。
- extensions：`btree_gin`、`pg_trgm`、`pgcrypto`、`plpgsql`。
- 表数量：
  - `app`：41
  - `audit`：2
  - `job`：3
  - `read_model`：6
  - `staging`：3
- `app/read_model/job/audit/staging` 所有表总行数为 0，非零表数量为 0。
- `fin-ops.service` 执行后仍为 `active`。

权限摘要：

| Grantee | Privilege | Table count |
| --- | --- | ---: |
| `fin_ops_api` | `INSERT` | 42 |
| `fin_ops_api` | `SELECT` | 47 |
| `fin_ops_api` | `UPDATE` | 41 |
| `fin_ops_migrator` | `INSERT` | 55 |
| `fin_ops_migrator` | `SELECT` | 55 |
| `fin_ops_migrator` | `UPDATE` | 55 |
| `fin_ops_readonly` | `SELECT` | 55 |
| `fin_ops_worker` | `INSERT` | 55 |
| `fin_ops_worker` | `SELECT` | 55 |
| `fin_ops_worker` | `UPDATE` | 55 |

## 后续阶段影响

阶段 03 之前需要保留以下边界：

- 不手写解析 Mongo pickle/Binary payload。
- 规范化导出必须复用 `ApplicationStateStore` 或业务 service。
- 所有 Mongo 数据先进入 `staging`，再转换正式表。
- OA Mongo `form_data_db.form_data` 继续只读，不作为 app 写库或迁移状态表。
