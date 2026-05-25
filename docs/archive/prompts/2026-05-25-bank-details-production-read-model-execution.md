# 2026-05-25 银行明细生产级 Read Model 性能整合执行 Prompt

/goal Implement a production-grade performance architecture for the 银行明细 page: SQL-native `bank_detail` read model, month-sharded dirty scopes, worker refresh, RabbitMQ-compatible envelope transport, optional Redis short-TTL page cache, SQL-first API read paths, frontend DataGrid virtualization fixes, backfill/runbook/observability, and end-to-end verification. This is not a temporary rescue patch: the API hot path must not synchronously rebuild or scan all bank/workbench facts in production PostgreSQL runtime.

## 背景和已确认问题

- 前端 `web/src/pages/BankDetailsPage.tsx` 已经使用 server pagination，但当前 `DataGrid` 同时启用了 `disableVirtualization`、`getRowHeight={() => "auto"}`、高 `columnBufferPx` 和 100/200/500 page size。MUI X 文档明确说明关闭虚拟化会显著扩大 DOM，只适合测试或小数据集。
- 后端 `BankDetailsService.list_transactions()` 当前直接调用 `fact_repository.list_bank_transactions_page()`，从 `app.bank_transactions` 分页读取，再在请求线程内补人工分类、自动分类、关联标签和分类计数。
- `PostgresCoreRepository.list_bank_transaction_accounts()` 通过 CTE 从 `app.bank_transactions` 归一化账户、统计日期范围 count、取最新余额。数据增长后会成为首屏账户侧栏风险点。
- 银行明细没有独立 SQL read model；`RuntimeQueueRepository.DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES` 里没有 `bank_detail.read_model.refresh`。
- Redis helper 和 RabbitMQ runtime 已存在，但银行明细查询链路没有接入 Redis page cache，也没有 read model refresh worker。
- 当前 `docs/operations/read-model-production-audit-2026-05-24.md` 认为银行明细暂不需要单独 read model；本次需求已经改变：用户明确要求生产级整合方案，不接受只加索引或只调 DataGrid 的临时补丁。

## 总体架构

目标链路：

```text
app.bank_transactions / app.bank_transaction_categories / settings / workbench relation facts
        |
        v
bank_detail SQL projection builder
        |
        v
read_model.bank_detail_rows + read_model.bank_detail_scopes
        |
        +--> optional Redis short TTL cache, keyed by schema/source_version/query hash
        |
        v
/api/bank-details/accounts + /api/bank-details/transactions
        |
        v
BankDetailsPage DataGrid with virtualization and server-side search/filter/sort
```

生产正确性源：

- PostgreSQL app/read_model/job 表是唯一事实源。
- RabbitMQ 只投递 outbox envelope，不能携带业务 payload、页面 snapshot 或 read model JSON。
- Redis 只允许做短 TTL cache 和 wakeup；Redis miss/error 必须回到 SQL read model，不能回到 live scan。

## 强约束

1. 先写失败测试，再实现。
2. PostgreSQL production/lightweight runtime 下，银行明细 API 不允许同步调用旧 live builder、`StateStore.load()`、`ImportNormalizationService.list_transactions()` 全量扫描、`_build_raw_workbench_payload("all")` 或类似全量构建兜底。
3. SQL fresh empty 是合法状态：返回 200、rows/accounts 为空、`read_model_status="fresh"`。
4. SQL missing/stale/schema mismatch：写 dirty scope/outbox，返回 202、`read_model_status="refreshing"`，不能请求内补建。
5. Legacy/local 非 PostgreSQL runtime 可保留现有直接查询路径，但必须被明确隔离，生产默认不走。
6. 关系标签必须来自持久化事实或持久化 read model；银行明细 API 不得在请求内重建 workbench all payload。
7. 任何 Redis 接入必须 best-effort：get/set/delete 异常只记录结构化日志，不打断 SQL read model 路径。
8. 所有变更必须考虑权限、审计、回滚、数据一致性和验证方式。
9. 不做无关重构；如果发现必须改大范围架构，先把阻塞点写清楚并停止扩大 scope。
10. 不为测试环境把生产 `DataGrid` 配置改回 `disableVirtualization`。如果 jsdom 测试需要特殊处理，只能在测试 helper/mock 层隔离。
11. 使用 MUI X Community DataGrid 时，生产 page size 不得超过该版本限制；除非明确升级到 Pro/Premium，否则不要保留 200/500 这种大页选项。

## 执行方式

- 推荐由一个总控 Codex 先完成串行准备和测试契约，然后并行分派任务 A-E。
- 每个并行执行者都不是单独占用代码库：不得 revert 他人改动；如果发现目标文件已有其他任务改动，必须顺着现有改动集成，不得覆盖。
- 并行任务的写入范围应尽量不重叠；如果任务之间必须修改同一文件，例如 `server.py` 或 `read_models.py`，先用测试明确契约，再在最终集成任务 F 统一收口。
- 任务 F 必须由一个执行者串行完成，负责最终冲突解决、契约一致性和完整验证。

## 串行主线

1. 读取事实源和现有模式：
   - `AGENTS.md`
   - `README.md`
   - `ARCHITECTURE.md`
   - `docs/product-specs/bank-details.md`
   - `docs/dev/runtime-infrastructure.md`
   - `docs/operations/read-model-production-audit-2026-05-24.md`
   - `backend/src/fin_ops_platform/services/bank_details_service.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/core.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/worker.py`
   - `backend/src/fin_ops_platform/services/runtime_queue.py`
   - `web/src/pages/BankDetailsPage.tsx`
2. 先补测试，锁定生产边界：
   - API miss/stale 不 live scan，只 enqueue refresh 并返回 202。
   - SQL fresh 返回 200。
   - SQL fresh empty 返回 200 空结果。
   - worker 可以处理 `bank_detail.read_model.refresh`。
   - `all` umbrella scope 展开为月份 shards。
   - RabbitMQ dispatch event types 包含 `bank_detail.read_model.refresh`。
   - Redis hit 直接返回 fresh payload；Redis error 回 SQL。
   - DataGrid 不再关闭虚拟化。
3. 新增 migration：
   - `read_model.bank_detail_rows`
   - `read_model.bank_detail_scopes`
   - 必要索引、grants、migration tests。
4. 扩展 SQL read repository：
   - list/save/mark bank detail rows/scopes。
   - accounts 和 transactions API 均从 SQL read model 查询。
   - 查询、过滤、排序、分页必须使用 native columns；payload 只作为返回体和兼容字段，不作为查询主路径。
5. 新增 projection builder 和 refresh service：
   - 按 `YYYY-MM` scope 重建银行明细行。
   - `all` 只 fan-out 到月份 scope，不直接全量重建。
   - 手工分类、自动分类、有效分类、OA/发票关系标签在 worker 中投影到 read model。
   - worker 完成后调用 `complete_read_model_refresh`，旧 source_version 不得覆盖新 dirty scope。
6. 扩展 runtime queue / worker / RabbitMQ topology：
   - 新 event type：`bank_detail.read_model.refresh`。
   - 新 worker flag：`--enable-bank-detail-read-model-refresh`。
   - RabbitMQ route/topology/dispatcher/preflight 覆盖新 event type。
7. 改 API：
   - `/api/bank-details/accounts`
   - `/api/bank-details/transactions`
   - PostgreSQL production 默认 SQL-first；missing/stale 返回 202。
   - 响应补 `read_model_status`、`read_model_scope_keys`、`read_model_generated_at`、`cache_status`。
8. 改 invalidation：
   - 银行流水导入确认。
   - 银行明细分类保存。
   - 银行明细标签字典变更。
   - workbench pair relation/candidate/exception 变化。
   - 自动分类规则版本变化。
   - 这些路径必须 enqueue 受影响月份或 `all`，不能只清内存。
9. 改前端：
   - 恢复 DataGrid virtualization。
   - 固定或可预测行高，避免动态 auto row height 造成大量测量。
   - search debounce。
   - 明确 server-side pagination/search/filter/sort 边界。
   - 处理 202 refreshing 状态，不当成硬错误。
10. 加 backfill 和 runbook：
   - 支持 dry-run、enqueue missing、enqueue all、worker drain。
   - 文档说明 RabbitMQ 灰度、PostgreSQL polling 回滚、Redis 边界、监控指标、生产验证 SQL。
11. 集成后跑聚焦测试、迁移测试、worker check、前端测试和 build。能跑全量时跑全量；否则说明未跑原因和剩余风险。

## Scope Key 和 Schema 要求

### Scope

- `scope_type`: `bank_detail`
- month shard: `YYYY-MM`
- umbrella: `all`
- API 按 date range 计算覆盖月份；任一覆盖月份 missing/stale/schema mismatch 时，enqueue 对应 month scope 并返回 202。

### `read_model.bank_detail_rows`

至少包含：

- identity: `transaction_id`, `scope_key`, `scope_month`, `source_batch_id`, `legacy_source_batch_id`
- account: `account_key`, `bank_name`, `account_last4`, `account_no`, `account_name`
- date/sort: `trade_time`, `trade_date`, `trade_time_sort`
- money: `direction`, `direction_label`, `amount`, `signed_amount`, `balance`, `currency`
- display: `counterparty_name`, `summary`, `purpose`
- category: manual category fields, auto category fields, effective category fields, category version/source
- relation: `oa_relation_tag`, `invoice_relation_tag`, `relation_tags`, `relation_case_id`
- search: `search_text`
- metadata: `schema_version`, `source_versions`, `generated_at`, `payload`, `raw_payload`, `updated_at`

Required indexes:

- unique row identity, preferably `transaction_id`
- `(scope_month, trade_time_sort desc, transaction_id)`
- `(scope_month, account_key, trade_time_sort desc, transaction_id)`
- `(scope_month, effective_category_code)`
- `gin(search_text gin_trgm_ops)`
- any expression/index needed by API filters must be justified by tests or EXPLAIN.

### `read_model.bank_detail_scopes`

At minimum:

- `tenant_id`
- `scope_type`
- `scope_key`
- `schema_version`
- `status`
- `row_count`
- `source_version`
- `source_versions`
- `generated_at`
- `last_error`
- `raw_payload`

Scope table must let repository distinguish:

- fresh empty
- missing/unbuilt
- stale/dirty
- schema mismatch

## 可并行任务

并行任务必须使用不重叠写入范围。每个任务完成后只提交自己负责的文件，集成阶段再统一修正冲突。

### 任务 A：Schema / Repository / Migration

/goal Add the SQL-native bank detail read model schema and repository methods, with tests proving fresh, fresh-empty, missing, stale, indexed pagination, account aggregation, keyword search, and native filtering semantics.

负责文件：

- Create: `backend/src/fin_ops_platform/postgres/migrations/0029_bank_detail_read_model.sql` or the next available migration number.
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Modify: `tests/test_postgres_migrations.py`
- Create or modify: `tests/test_bank_details_sql_runtime.py`
- Create or modify: focused repository tests if the existing test file is too large.

要求：

1. 先写 repository/migration 失败测试。
2. 建 `read_model.bank_detail_rows` 和 `read_model.bank_detail_scopes`。
3. 实现：
   - `list_bank_detail_transactions(...)`
   - `list_bank_detail_accounts(...)`
   - `save_bank_detail_rows(scope_key, rows)`
   - `mark_bank_detail_scope(scope_key, row_count=0)`
   - `bank_detail_source_summary(...)` if useful for API metadata.
4. 查询必须支持：
   - `account_key`
   - `date_from/date_to`
   - `keyword`
   - `page/page_size`
   - stable order by `trade_time_sort desc, transaction_id desc`
   - category counts based on full matched query, not only current page.
5. Fresh empty scope must return a payload with empty rows/accounts and `read_model_status="fresh"`; never return `None` for a built empty scope.
6. Missing scope returns `None` so API can enqueue refresh and return 202.
7. Do not query `app.bank_transactions` in the repository read path except inside projection/backfill tests.

Verification:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_bank_details_sql_runtime -v
```

### 任务 B：Projection Builder / Worker / RabbitMQ

/goal Add a bank detail projection builder and runtime refresh service that rebuilds month shards from PostgreSQL facts, completes dirty scopes idempotently, supports `all` fan-out, and is routable through both PostgreSQL polling and RabbitMQ envelope transport.

负责文件：

- Create: `backend/src/fin_ops_platform/services/bank_detail_sql_projection.py`
- Create: `backend/src/fin_ops_platform/services/bank_detail_read_model_refresh.py`
- Modify: `backend/src/fin_ops_platform/app/worker.py`
- Modify: `backend/src/fin_ops_platform/services/runtime_queue.py`
- Modify: RabbitMQ topology/runtime files if event route lists are separate.
- Modify: `tests/test_runtime_queue.py`
- Modify or create: `tests/test_bank_details_sql_runtime.py`
- Modify: `tests/test_rabbitmq_runtime.py` / `tests/test_rabbitmq_staging_preflight.py` if event allowlists are asserted there.

要求：

1. 先写 worker/refresh 失败测试。
2. Event type must be `bank_detail.read_model.refresh`.
3. `scope_type` must be `bank_detail`; invalid scope must fail fast.
4. `scope_key="all"` must enqueue month shards and complete only the umbrella dirty scope. It must not synchronously rebuild all history in one event.
5. Month shard rebuild must:
   - read bank transactions for the month from PostgreSQL,
   - apply manual category from `app.bank_transaction_categories` or the existing repository source,
   - apply automatic category using existing rule code or an equivalent SQL-safe projection boundary,
   - project relation tags from persisted relation facts/read models without calling request-time workbench builders,
   - save rows through `PostgresReadModelRepository`.
6. If required source read models are missing/stale, enqueue their refresh or mark bank detail scope stale; do not silently fabricate relation tags.
7. Worker flag: `--enable-bank-detail-read-model-refresh`.
8. `app.worker --check` must show handler and RabbitMQ route when enabled.

Verification:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --check \
  --enable-bank-detail-read-model-refresh \
  --event-type bank_detail.read_model.refresh

PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_bank_details_sql_runtime tests.test_rabbitmq_runtime -v
```

### 任务 C：API / Redis / Invalidation

/goal Switch `/api/bank-details/accounts` and `/api/bank-details/transactions` to SQL-first read model behavior in production PostgreSQL runtime, add optional Redis short-TTL page cache, and enqueue bank detail refresh scopes from every write path that changes bank detail display state.

负责文件：

- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/bank_details_service.py` only if a thin DTO mapper remains useful.
- Modify: `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py` if it owns invalidation families.
- Modify: import/category/workbench action paths only where needed to enqueue bank detail scopes.
- Modify or create: `tests/test_bank_details_sql_runtime.py`
- Modify: `tests/test_workbench_sql_runtime.py` or focused invalidation tests if existing behavior is covered there.

要求：

1. 先写 API/invalidation 失败测试.
2. Production PostgreSQL runtime:
   - SQL fresh -> 200.
   - SQL fresh empty -> 200.
   - SQL miss/stale/schema mismatch -> enqueue `bank_detail` refresh and return 202.
   - Redis hit -> 200 fresh, without SQL query.
   - Redis get/set/delete error -> structured warning, continue SQL path.
3. Legacy/local non-PostgreSQL runtime may keep existing `BankDetailsService` direct path, but tests must prove production PostgreSQL does not call it on miss.
4. Redis keys must include:
   - schema version
   - covered scope keys or source version
   - endpoint kind
   - normalized query hash
5. Redis TTL must be short, e.g. 30-120 seconds, and configurable or locally constant with justification.
6. Invalidation must enqueue bank detail refresh for affected months after:
   - bank transaction import/confirm,
   - category save,
   - tag dictionary save,
   - workbench confirm/withdraw/exception/candidate lifecycle changes,
   - data reset affecting bank transactions.
7. Invalidation must delete relevant Redis keys when cache versioning is insufficient; prefer versioned keys when practical.

Verification:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime tests.test_workbench_sql_runtime tests.test_import_job_queue -v
```

### 任务 D：Frontend 银行明细页面

/goal Make the bank details UI consume the SQL read model contract correctly and remove DataGrid rendering bottlenecks by restoring virtualization, stabilizing row layout, debouncing search, and handling 202 refreshing responses without treating them as hard failures.

负责文件：

- Modify: `web/src/pages/BankDetailsPage.tsx`
- Modify: `web/src/features/bankDetails/api.ts`
- Modify: `web/src/features/bankDetails/types.ts`
- Modify: `web/src/test/BankDetailsPage.test.tsx`
- Modify: `web/src/test/BankDetailsApi.test.ts`
- Modify CSS only if fixed-height row layout requires it: `web/src/app/styles.css`

要求：

1. 先写前端失败测试.
2. Remove `disableVirtualization`.
3. Avoid `getRowHeight={() => "auto"}` unless a tested MUI-supported virtualization-safe strategy is used. Prefer fixed/predictable row height with text clamping.
4. Reduce `columnBufferPx`; do not disable column virtualization by oversized buffer.
5. Debounce search input so every keystroke does not immediately fire API requests.
6. Handle backend 202/refreshing:
   - show refreshing state,
   - keep controls usable where safe,
   - retry or expose refresh action according to existing page conventions,
   - do not display it as a fatal error.
7. Keep page state semantics: selected account, date filter, dirty category guard, tag sync.
8. Server-side pagination remains the source of truth for row count.
9. Page size options must fit the installed MUI X DataGrid plan. With the current Community package, keep options at or below 100 unless the task explicitly upgrades the package/license.
10. If export remains visible, make scope explicit: current page export only, or route to a server export endpoint. Do not imply full dataset export from client rows.

Verification:

```bash
cd web
npm test -- BankDetailsPage BankDetailsApi
npm run build
```

### 任务 E：Backfill / Operations / Observability

/goal Add production backfill, warm-up, runbook, and monitoring hooks for the bank detail read model so historical data is warmed before cutover and operators can verify freshness, queue health, RabbitMQ routing, Redis behavior, rollback, and API p95.

负责文件：

- Modify: `scripts/backfill-runtime-read-models.py`
- Create: `docs/operations/bank-detail-read-model-backfill.md`
- Modify: `docs/operations/index.md`
- Modify: `docs/dev/runtime-infrastructure.md` if event lists or worker roles change.
- Modify: `backend/src/fin_ops_platform/services/runtime_monitoring.py` if metrics need event allowlist updates.
- Modify or create: tests for backfill planner/CLI.

要求：

1. 先写 backfill/ops 失败测试 where practical.
2. Backfill supports:
   - dry-run,
   - enqueue all,
   - enqueue explicit month,
   - enqueue missing scopes,
   - JSON report,
   - worker drain with bank detail handler.
3. Runbook must include:
   - migration apply,
   - backfill dry-run,
   - enqueue,
   - RabbitMQ dispatcher/consumer check,
   - PostgreSQL polling rollback,
   - Redis optional cache verification,
   - API smoke,
   - SQL count/freshness checks,
   - dirty scope/outbox/DLQ checks,
   - p95/p99 observation method.
4. No production claim is complete until backfill and at least one worker smoke pass.

Verification:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --check \
  --enable-bank-detail-read-model-refresh \
  --event-type bank_detail.read_model.refresh

PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_runtime_monitoring tests.test_bank_details_sql_runtime -v
```

### 任务 F：最终集成与审阅

/goal Integrate the parallel task outputs, resolve contract mismatches, run the complete verification set, and perform a production-readiness review focused on correctness, performance, consistency, rollback, and operational safety.

负责范围：

- Resolve conflicts across tasks A-E.
- Ensure scope key, schema version, DTO fields, Redis key format, event type, worker flag, and runbook commands are consistent.
- Run focused and broad verification.

必跑检查：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --check \
  --enable-bank-detail-read-model-refresh \
  --event-type bank_detail.read_model.refresh
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_details_sql_runtime tests.test_postgres_migrations tests.test_runtime_queue tests.test_rabbitmq_runtime -v
cd web && npm test -- BankDetailsPage BankDetailsApi
cd web && npm run build
git diff --check
```

如时间和环境允许，再跑：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
cd web && npm test
```

审阅清单：

- [ ] PostgreSQL production API miss/stale 不 live scan。
- [ ] Fresh empty 与 missing scope 行为清晰区分。
- [ ] `bank_detail.read_model.refresh` 在 PostgreSQL queue 和 RabbitMQ route 中都可见。
- [ ] Worker handler 幂等，旧 source_version 不覆盖新 scope。
- [ ] Redis 只做短 TTL cache，异常不影响 SQL 路径。
- [ ] 银行导入、分类、标签、workbench 关系变化都会触发 bank detail dirty scope。
- [ ] 前端 DataGrid virtualization 恢复，page size 合法，搜索 debounce 生效，202 refreshing 有正常 UI。
- [ ] Runbook 覆盖迁移、backfill、worker、RabbitMQ、Redis、回滚和观测。
- [ ] 所有新增测试先失败后通过，最终验证结果写入交付说明。

## 最终验收标准

- 银行明细首屏不再依赖请求线程 live build。
- `/api/bank-details/accounts` 和 `/api/bank-details/transactions` 的生产热路径是 SQL read model。
- Missing/stale 只 enqueue refresh，返回 202，不同步重建。
- `bank_detail` read model 支持按月份 shard backfill 和 worker refresh。
- RabbitMQ 可作为新 event 的 envelope transport，PostgreSQL outbox/dirty scope 仍是事实源。
- Redis 若实现，只是 SQL read model 后的短 TTL page cache。
- DataGrid 渲染不再关闭虚拟化。
- 文档和运维命令足以让生产先 backfill 再灰度切流。
- 验证命令已执行；未执行项必须有明确原因和风险说明。

## 不做事项

- 不把 Redis 当 read model 或业务事实源。
- 不让 RabbitMQ 消息体携带银行明细 rows、页面 snapshot 或业务 payload。
- 不用 DataGrid 客户端过滤/排序替代后端查询。
- 不只添加索引或只调前端参数来宣布完成。
- 不在生产 PostgreSQL runtime 下回退到 `StateStore.load()` 或全量 Application snapshot。
- 不做无关页面重构。
