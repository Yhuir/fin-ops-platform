# 阶段 06：真实 PostgreSQL integration 和 repository 缺口闭合

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for parallel work or `superpowers:executing-plans` for serial execution. 本阶段要在 disposable PostgreSQL test DB 上证明 app 的 PostgreSQL mode 可真实运行，并闭合阶段 05 留下的 repository、事务和 API smoke 缺口。

**Goal:** 让 app 在真实 PostgreSQL 测试库中完成关键读写、DTO、文件兼容和 repository contract 验证，同时保持默认 local/Mongo 模式全量测试通过。

**Architecture:** 阶段 05 已提供 `PostgresConnection`、`PostgresStateStore`、factory、Protocol 和本地 fake tests。阶段 06 在此基础上接入真实测试库 fixture，补足正式表 repository 写路径、事务边界、JSONB/domain mapper 和 API smoke。生产服务仍不切换，本阶段只允许测试库写入和生产只读检查。

**Tech Stack:** Python 3, PostgreSQL 16, `psycopg`, pytest/unittest, existing SQL migrations 0001-0007, existing app HTTP handler tests.

---

## 05 已完成事实

- 默认模式不依赖 PostgreSQL，`python -m pytest -q` 已通过。
- `FIN_OPS_APP_STORAGE_BACKEND=postgres` 的配置入口、URI 脱敏、factory 和 readiness 骨架已存在。
- `ApplicationStateStoreProtocol` 已覆盖 public method 清单。
- `PostgresStateStore` 已支持基础 snapshot round-trip、文件元数据写入和 legacy GridFS reader 注入。
- 新增测试：
  - `tests/test_state_store_contract.py`
  - `tests/test_postgres_state_store.py`
  - `tests/test_app_postgres_mode.py`
- 阶段 05 文档 gate 为 `PARTIAL`，不是最终完成。

## 05 剩余缺口

- 未使用真实 `FIN_OPS_TEST_DATABASE_URL` 跑 PostgreSQL integration。
- `PostgresStateStore` 写路径多数仍落 `app.app_settings state:<key>` JSONB snapshot，尚未完整写入正式领域表。
- 多表业务 mutation 缺少显式事务上下文。
- API smoke 只覆盖 readiness/factory 层，尚未覆盖 workbench/search/no OA/tax/ETC/import/file 等真实 Postgres mode DTO。
- 阶段 04 导入的正式表数据尚未通过 app service mapper 做端到端验证。
- 生产服务器只读 smoke 尚未执行。

## 阶段边界

允许：

- 在 disposable PostgreSQL test DB 上 apply 0001-0007。
- 在 test DB 内 truncate/seed/write。
- 新增/修改 PostgreSQL repository 代码、mapper、测试 fixture。
- 对生产 PostgreSQL 做只读 count/schema/readiness smoke。
- 使用注入式 legacy file reader 读取 app Mongo GridFS 文件内容，前提是只读。

禁止：

- 写 OA Mongo `form_data_db.form_data`。
- 写生产 app Mongo。
- 在生产 PostgreSQL 上执行 destructive test setup。
- 切换或重启生产服务。
- 直接把旧 app Mongo 全量覆盖 PostgreSQL。
- 为了让测试通过改变前端 DTO 或业务语义。

## 配置和测试库要求

新增/确认环境变量：

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `FIN_OPS_TEST_DATABASE_URL` | integration 必需 | disposable PostgreSQL test DB URL；不得指向生产库。 |
| `FIN_OPS_ALLOW_POSTGRES_TEST_DB` | 条件必需 | 当 DB 名不含 `test` 时必须显式为 `1`，否则测试拒绝写入。 |
| `FIN_OPS_APP_STORAGE_BACKEND` | Postgres mode 必需 | integration 中设置为 `postgres`。 |
| `FIN_OPS_APP_READ_BACKEND` | 可选 | 阶段 06 可设为 `postgres`，不实现 shadow 切换。 |
| `FIN_OPS_POSTGRES_DATABASE_URL` / `DATABASE_URL` | Postgres app check 必需 | app runtime 连接 URL。 |

测试库 guard：

- DB 名必须包含 `test`，或显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`。
- 每个 test case 只能 truncate test DB schema。
- 测试输出不得打印完整 URL、密码、token。

## 建议新增/修改文件

| 路径 | 动作 | 责任 |
| --- | --- | --- |
| `backend/src/fin_ops_platform/services/postgres_connection.py` | Modify | 增加事务 context、批量 execute、integration guard helper。 |
| `backend/src/fin_ops_platform/services/postgres_state_store.py` | Modify | 拆出领域 repository 调用，减少 snapshot-only 写路径。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/__init__.py` | Create | repository package。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/core.py` | Create | imports、invoices、bank transactions、import files、file objects。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py` | Create | workbench pair relations、overrides、exception cases、no OA、categories、dirty scopes。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` | Create | workbench rows/snapshots、candidate matches、search index、cost/tax read models。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py` | Create | settings、jobs、health、tax certified、ETC、turnover、historical ETC。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/files.py` | Create | `app.file_objects`、legacy GridFS URI parsing、app-owned file deletion semantics。 |
| `tests/postgres_test_utils.py` | Create | test DB guard、migration apply、truncate、seed helpers。 |
| `tests/test_postgres_state_store_integration.py` | Create | real PostgreSQL store contract/integration。 |
| `tests/test_app_postgres_mode_integration.py` | Create | real PostgreSQL API smoke。 |
| `tests/test_state_store_contract.py` | Modify | 将 real Postgres store 纳入同一 contract，缺 env 时 skip。 |
| `docs/database-migration/06-postgresql-integration-repository-closure.md` | Modify | 执行记录和 gate。 |

## Repository 闭合范围

### Core repository

目标表：

- `app.import_batches`
- `app.import_batch_rows`
- `app.file_objects`
- `app.import_files`
- `app.invoices`
- `app.bank_transactions`
- `app.bank_transaction_categories`

要求：

- domain-facing id 必须优先使用 `legacy_mongo_id` / `legacy_source_batch_id`，不能把 UUID 暴露给现有 DTO。
- `raw_payload.normalized_payload` 中未拆列字段必须保留并可重建。
- `load()["imports"]` 必须可被 `ImportNormalizationService.from_snapshot()` 消费。
- `load()["file_imports"]` 必须可被 `FileImportService.from_snapshot()` 消费；session/file item shape 不能退化为前端不可用 dict。
- `store_import_file()` 必须写 `app.file_objects` 和 `app.import_files`。
- `read_import_file()` 必须支持：
  - app-owned local path。
  - 旧 store `gridfs://<file_id>/<name>`。
  - 阶段 04 `gridfs://<bucket>/<legacy_gridfs_id>`。

### Workbench repository

目标表：

- `app.workbench_pair_relations`
- `app.workbench_pair_relation_history`
- `app.workbench_row_overrides`
- `app.workbench_exception_cases`
- `app.workbench_exception_case_events`
- `app.no_oa_bank_batches`
- `app.no_oa_bank_batch_events`
- `job.workbench_matching_dirty_scopes`
- `app.bank_transaction_categories`
- `app.bank_transaction_category_events`

要求：

- 保存 pair relation/no OA/category 时写正式表结构化列和完整 `raw_payload`。
- version 字段不得被 JSON snapshot 绕过；service 内版本语义要保持。
- 失败时必须能被现有 service 恢复 previous snapshot 或返回现有错误。
- write 方法幂等：重复保存同一 snapshot 不制造重复 rows。
- changed ids 参数必须限制写入范围，不能因为增量保存误删未变数据。

### Read model repository

目标表：

- `read_model.workbench_rows`
- `read_model.workbench_snapshots`
- `read_model.workbench_candidate_matches`
- `read_model.search_index_rows`
- `read_model.cost_statistics_read_models`
- `read_model.tax_offset_read_models`

要求：

- read model 保存写正式表 `payload` 和索引列。
- `source_versions` freshness 语义保持。
- search DTO 不变。
- cache stale/dirty scope 语义保持。

### Ops/Tax/ETC repository

目标表：

- `app.app_settings`
- `job.background_jobs`
- `audit.app_health_alerts`
- `app.tax_certified_import_sessions`
- `app.tax_certified_import_batches`
- `app.tax_certified_import_records`
- `app.etc_*`
- `app.historical_etc_repair_*`
- `app.turnover_relations`
- `app.turnover_relation_events`
- `app.turnover_ledger_extras`

要求：

- settings 默认 shape 与 `ApplicationStateStore.load_app_settings()` 完全一致。
- jobs snapshot 不泄漏敏感字段，job payload 的 `type` 与 SQL `job_type` 显式映射。
- health alerts 的 `records` shape 保持。
- tax/ETC/historical ETC dataclass、Enum、Decimal、datetime 必须 JSONB round-trip。
- turnover relation 多 bank/principal/settlement rows 不得因正式表单列字段丢失。

## 事务要求

必须新增 transaction API，例如：

```python
with connection.transaction() as tx:
    tx.execute(...)
    tx.execute(...)
```

至少覆盖：

- `save(payload)` core imports/files 批量保存。
- no OA submit/withdraw 相关 snapshot 保存。
- pair relation 保存及 history event。
- category save 及 category event。
- read model save 与 dirty scope save。

测试必须覆盖：

- 成功 commit。
- 中途异常 rollback。
- 重复保存幂等。
- version conflict 或 stale snapshot 不破坏旧数据。

## 测试计划

### 任务 6.1：真实 PostgreSQL test fixture

**Files:**

- Create: `tests/postgres_test_utils.py`
- Modify: `tests/test_postgres_state_store_integration.py`

**Steps:**

- [ ] 实现 `require_postgres_test_database_url()`。
- [ ] 校验 DB 名包含 `test` 或 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`。
- [ ] 用 migration runner apply 0001-0007。
- [ ] 实现 test DB truncate helper。
- [ ] 实现 minimal seed helper。
- [ ] 缺 env 时 `pytest.skip()`，不得 fail。

**Acceptance:**

- 无 `FIN_OPS_TEST_DATABASE_URL` 时 integration tests skip。
- 有 test DB 时 migrations apply 成功。
- 不可能误 truncate 生产库。

### 任务 6.2：PostgresStateStore real DB contract

**Files:**

- Modify: `tests/test_state_store_contract.py`
- Create: `tests/test_postgres_state_store_integration.py`

**Steps:**

- [ ] 将 real `PostgresStateStore` 加入 contract factory。
- [ ] 跑 app settings、manual OA imports、OA cache、background jobs、health alerts。
- [ ] 跑 workbench/no OA/categories/read models/tax/ETC/turnover snapshot round-trip。
- [ ] 跑 import/file store/read/delete/existence methods。
- [ ] 跑 legacy GridFS URI parsing with fake injected reader。

**Acceptance:**

- contract 在 local store 和 real Postgres store 均通过。
- 所有新增 SQL 使用参数化执行。

### 任务 6.3：正式表 repository 写路径

**Files:**

- Create: `backend/src/fin_ops_platform/services/postgres_repositories/*.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Test: `tests/test_postgres_state_store_integration.py`

**Steps:**

- [ ] 从 `PostgresStateStore` 中拆出 core/workbench/read_model/ops_tax_etc/files repositories。
- [ ] 为每个 repository 定义 load/save/upsert 方法。
- [ ] 写正式表结构化列，同时保留完整 `raw_payload.normalized_payload`。
- [ ] 保留 `app.app_settings state:<key>` 只作为兼容/恢复 fallback，不作为主要写路径。
- [ ] 加事务测试和 rollback 测试。

**Acceptance:**

- 关键业务写入后，对应正式表能查到结构化列和完整 raw payload。
- 不再仅依赖 `app.app_settings state:<key>` 证明 PostgreSQL mode 可用。

### 任务 6.4：Postgres mode API smoke

**Files:**

- Create: `tests/test_app_postgres_mode_integration.py`
- Modify: `tests/test_app_postgres_mode.py`

**Steps:**

- [ ] 用 test DB seed 最小 import batch、invoice、bank transaction、file object/import file。
- [ ] seed settings、job、health、workbench snapshot/read model/search rows。
- [ ] seed no OA、tax、ETC、turnover 最小数据。
- [ ] `FIN_OPS_APP_STORAGE_BACKEND=postgres` 启动 app。
- [ ] 验证 `/health`、`/api/session/me`。
- [ ] 验证 `/api/workbench/settings`。
- [ ] 验证 `/api/background-jobs/active`。
- [ ] 验证 `/api/workbench?month=...`。
- [ ] 验证 `/api/search`。
- [ ] 验证 `/api/no-oa-bank-batches`。
- [ ] 验证 `/api/tax-offset`。
- [ ] 验证 `/api/etc/invoices`、`/api/etc/batches`。
- [ ] 验证 import file retry/download 对 legacy ref 的错误/读取语义清晰。

**Acceptance:**

- API response status 和核心 DTO 字段与现有默认模式测试一致。
- 不触发 OA Mongo 写入。
- 不泄漏 DB URL。

### 任务 6.5：生产只读 smoke

**Files:**

- Modify: `docs/database-migration/06-postgresql-integration-repository-closure.md`

**Steps:**

- [ ] SSH 到服务器，只读检查服务状态。
- [ ] 只读查询 `public.schema_migrations` version。
- [ ] 只读查询核心表 counts，与阶段 04 reconciliation 对齐。
- [ ] 在不重启服务、不改生产配置前提下执行 app `--check`，仅在环境变量可安全提供时启用 Postgres mode。
- [ ] 记录命令、脱敏输出、结果。

**Acceptance:**

- 生产只读 smoke 不修改任何业务表。
- counts 与阶段 04 报告无异常偏差。

## 推荐命令

默认全量：

```bash
python -m pytest -q
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

PostgreSQL integration：

```bash
export FIN_OPS_TEST_DATABASE_URL='<redacted test db url>'
export FIN_OPS_ALLOW_POSTGRES_TEST_DB=1
export FIN_OPS_APP_STORAGE_BACKEND=postgres
export FIN_OPS_APP_READ_BACKEND=postgres
export DATABASE_URL="$FIN_OPS_TEST_DATABASE_URL"
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

生产只读 smoke 模板：

```bash
ssh root@139.155.5.132 'systemctl is-active fin-ops.service && systemctl show -p ActiveState -p SubState -p ExecMainPID fin-ops.service'
```

```bash
ssh root@139.155.5.132 'psql -X -At -v ON_ERROR_STOP=1 <<SQL
select version from public.schema_migrations order by version;
select '\''app.import_batches'\'', count(*) from app.import_batches
union all select '\''app.invoices'\'', count(*) from app.invoices
union all select '\''app.bank_transactions'\'', count(*) from app.bank_transactions
union all select '\''read_model.search_index_rows'\'', count(*) from read_model.search_index_rows;
SQL'
```

## 2026-05-20 执行记录

执行方式：

- 主线程执行代码修改、测试和文档更新。
- 只读子代理并行梳理 test fixture/migration runner、core/files repository、workbench/read model repository、ops/tax/ETC/turnover repository、API smoke/DTO。
- 子代理未写文件、未连接服务器或数据库、未触碰 OA Mongo。

本次已完成：

- 新增 `tests/postgres_test_utils.py`，提供 test DB guard、固定 0001-0007 migration discovery、migration apply、白名单业务表 truncate、脱敏约束。
- 新增 `tests/test_postgres_test_utils.py`，覆盖 guard 不读取 `DATABASE_URL`、拒绝 reserved DB、拒绝非 test DB 时脱敏。
- 新增 `tests/test_postgres_state_store_integration.py`，在真实 disposable PostgreSQL 上覆盖 migration apply、`public.schema_migrations`、health summary、transaction commit/rollback、关键正式表写入、import file 元数据。
- 新增 `tests/test_app_postgres_mode_integration.py`，在真实 disposable PostgreSQL 上覆盖 Postgres mode app 构建、readiness、`/health`、`/api/session/me`、`/api/app-health`、settings 写入和 app rebuild 后读取。
- 修改 `backend/src/fin_ops_platform/services/postgres_connection.py`，增加 transaction API，修正 `statement_timeout` 参数化方式，readiness 查询统一为 `public.schema_migrations`。
- 修改 `backend/src/fin_ops_platform/services/postgres_state_store.py`，补齐规范化 helper，关键 jobs/health/workbench/no OA/category/read model/turnover/ledger/cost/tax 写路径写正式表并保留 snapshot fallback，import file 写入 `file_object_id`，local delete 同步标记 deleted。

验证结果：

- 无 `FIN_OPS_TEST_DATABASE_URL` 时：`python -m pytest tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q`，结果 `4 passed, 5 skipped`。
- 临时本地 PostgreSQL cluster，库名 `fin_ops_stage06_test`：`tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py` 结果 `5 passed`。
- 本地阶段相关测试：`python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py -q`，结果 `28 passed, 5 skipped`。
- 本地全量测试：`python -m pytest -q`，结果 `1143 passed, 10 skipped`。
- 生产只读 smoke：
  - SSH 登录成功。
  - `fin-ops.service` 为 `active/running`，`ExecMainPID=251543`。
  - `public.schema_migrations` versions 为 `0001` 到 `0007`。
  - 只读 counts：`app.import_batches=6`，`app.import_batch_rows=897`，`app.file_objects=445`，`app.import_files=31`，`app.invoices=391`，`app.bank_transactions=431`，`read_model.search_index_rows=822`。

本次未完成，转入阶段 07：

- 未拆出 `postgres_repositories/*.py` package；当前仍在 `PostgresStateStore` 内集中实现。
- `load()["imports"]` 和 `load()["file_imports"]` 仍未完整恢复 `ImportNormalizationService.from_snapshot()` / `FileImportService.from_snapshot()` 需要的 domain object shape。
- tax certified、ETC、historical ETC 的正式表 mapper 和 JSONB dataclass hydration 仍未闭合。
- pair relation/no OA/category 的 history/event 表写入仍未完整闭合。
- `read_model.search_index_rows` 仍主要作为迁移/预留表，app search smoke 尚未覆盖正式 search index repository。
- `changed_case_ids`、`changed_row_ids`、`changed_scope_keys`、`changed_scope_months` 的删除/局部更新语义仍需阶段 07 深化。

## Gate

`PASS` 条件：

- 默认 local/Mongo 全量测试通过。
- 无 test DB 时 integration tests 正确 skip。
- 有 test DB 时 PostgreSQL migrations、contract、repository integration、API smoke 全部通过。
- 正式表写路径覆盖 core/workbench/read_models/ops_tax_etc/files 的关键 runtime writes。
- 多表写入具备事务测试。
- legacy GridFS URI 兼容测试通过。
- 生产只读 smoke 通过并记录。
- OA Mongo 仍只读；未新增 OA 写路径。

`BLOCKED` 条件：

- 默认模式被 PostgreSQL 配置或 driver 破坏。
- 真实 Postgres mode 启动失败。
- API DTO 与现有前端契约不兼容。
- 任何 public state store method 缺实现且被现有 service 调用。
- 文件 legacy reference 无法读取或无清晰错误边界。
- test DB guard 无法防止误写生产。

## 阶段产物

- real PostgreSQL integration test fixture。
- 领域 repository 拆分和事务边界。
- real Postgres store contract tests。
- Postgres mode API smoke tests。
- 生产只读 smoke 记录。
- 阶段 06 gate 结果。

## Gate 结果

`PARTIAL`

理由：

- 真实 disposable PostgreSQL integration、事务、关键正式表写入 smoke、Postgres app smoke、生产只读 smoke 已完成并通过。
- 默认 local/Mongo 全量测试通过。
- 但阶段 06 原 PASS 条件中的完整 repository package 拆分、core import/file domain mapper、tax/ETC/historical ETC JSONB hydration、event/history 表写入、局部更新删除语义仍未完成。
- 因此阶段 06 已把“真实 PostgreSQL 可运行验证”和一批关键写路径闭合，但不能声明整个 app 已完美接入 PostgreSQL；剩余项应作为阶段 07 的执行范围。
