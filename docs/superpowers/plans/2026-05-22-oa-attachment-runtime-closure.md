# OA Attachment Runtime Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every OA attachment invoice that exists in the configured OA source or PostgreSQL projection is represented in the app through PostgreSQL facts, SQL read models, and worker refreshes, without request-path Mongo/snapshot fallback.

**Architecture:** OA sync worker reads OA records from the existing source adapter according to `oa_retention.cutoff_date` / OA import start date, preserves source-bound invoice attachment facts, writes `app.oa_attachments` and indexed cache lookup rows, then marks workbench/search/pending-invoice scopes dirty. Workbench API all-scope filtered/page reads must use `read_model.workbench_rows` SQL directly and only load lightweight summaries, not full grouped payloads.

**Tech Stack:** Python, pytest, PostgreSQL, `job.outbox_events`, `read_model.workbench_rows`, Redis wakeup optional, MinIO unrelated for this task.

---

## /goal OA 附件事实与 Workbench SQL 查询收口

目标：
1. OA sync worker 按 `oa_retention.cutoff_date` / “OA 导入起始日期”重新拉取可见月份 OA，并保留付款项附件中的发票信息。
2. OA projection 写入 `app.oa_application_items`、`app.oa_attachments`、`app.oa_attachment_invoice_cache_sources`，保证附件解析缓存和真实附件 key 可索引关联。
3. 写入 OA projection 后 enqueue workbench/search/pending-invoice dirty scope，不依赖 API 请求路径同步补数据。
4. `/api/workbench?month=all&page/filter/source_kind=...` 走 `read_model.workbench_rows` SQL 分页，不先拼全量 grouped payload。
5. 用测试和本地 PostgreSQL smoke 证明：PG 有内容时 app 能显示；没有显示时必须能从 facts/projection/queue 看到明确缺口。

串行任务：
1. 读取 `OAProjectionSyncService`、`PostgresOAProjectionRepository`、`MongoOAAdapter` 附件解析逻辑、`PostgresReadModelRepository.get_workbench_view`。
2. 写失败测试：OA sync worker 不得丢弃 source-bound attachment invoice payload；all-scope filtered rows_page 不得加载 full grouped snapshots。
3. 实现 OA sync projection hardening：保留发票附件 payload；维护 cache source lookup；同步结果报告 attachment counts。
4. 实现 workbench all-scope rows_page SQL-first 查询：summary 轻量聚合，rows 直接查 `read_model.workbench_rows`。
5. 跑 targeted tests、migration tests、本地 runtime smoke；如有真实 OA source 配置，跑 `oa.sync` worker/backfill。
6. 输出剩余数据缺口：哪些月份有 OA application、哪些月份有 `app.oa_attachments`、哪些月份有 read model 附件行。

可并行任务：
- A: OA sync/projection tests and implementation.
- B: Workbench repository SQL-first all-scope query tests and implementation.
- C: PostgreSQL diagnostics/backfill smoke.
- D: docs/plan verification notes.

完成门槛：
- 生产请求路径不读 Mongo/GridFS/snapshot fallback 来补 OA 附件。
- `app.oa_attachments` 中可匹配 cache source lookup 的附件能进入 `read_model.workbench_rows`。
- all-scope filtered/page API 不再因全量 payload 拼装导致 20s+ 查询。
- 队列无 pending/processing/failed 后，workbench rows 覆盖 PostgreSQL facts 可观测。
- 如果 OA source 未配置，明确报告无法拉取源端附件，而不是声称迁移完成。

## Execution Notes

- [x] `OAProjectionSyncService` now preserves invoice-like top-level and item-level attachment facts while still dropping non-invoice payment/unknown attachment payloads.
- [x] Workbench all-scope filtered/page reads now query `read_model.workbench_rows` directly and load only lightweight per-month summaries.
- [x] Targeted tests were added for source-bound OA invoice attachment preservation and SQL-first all-scope workbench pagination.
- [x] Verification run: `PYTHONPATH=backend/src pytest tests/test_oa_projection_sql_runtime.py tests/test_workbench_sql_runtime.py tests/test_postgres_repositories_boundaries.py tests/test_postgres_migrations.py -q` passed with 53 tests.
- [x] Local runtime smoke passed with PostgreSQL, Redis, MinIO, backend health, and workbench API ready.
- [x] Performance smoke: `/api/workbench?month=all&page_size=200&source_kind=oa_attachment_invoice` returned 94 rows in about 1.3s, down from the previously observed about 27s full-payload path.
- [ ] Real OA source backfill is still required for months where PostgreSQL has OA applications but no attachment facts. Current diagnostic: 2025-12 has 64 OA attachments and 94 workbench attachment-invoice rows; 2026-01 through 2026-05 currently have 0 `app.oa_attachments` rows.
- [ ] Local OA source credentials are not present in `.runtime/fin_ops_platform/local-postgres.env`; `oa.sync` must be run in an environment with `FIN_OPS_OA_MONGO_*` or `oa_mongo_config.json` configured.
