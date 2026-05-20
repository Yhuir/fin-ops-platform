# 阶段 05：PostgreSQL repository 层和测试

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for parallel work or `superpowers:executing-plans` for serial execution. 本阶段文档用于生成后续 Codex 执行 prompt；执行时必须按模块保留 Mongo 模式兼容，并逐步增加 PostgreSQL 模式测试。

**Goal:** 在当前 Python 后端中加入 PostgreSQL repository/state store，使 app 能在 PostgreSQL 模式下读取和写入 app 自身数据，同时继续通过 OA Mongo 只读 adapter 获取 OA 源数据。

**Architecture:** 先定义 `ApplicationStateStore` 兼容接口和 factory，再实现 `PostgresStateStore`。Mongo 模式保持默认可用；PostgreSQL 模式通过 feature flag 启动；所有现有 service 尽量不改业务逻辑，只替换 state store/repository 边界。

**Tech Stack:** Python 3, PostgreSQL 16, `psycopg` 或 SQLAlchemy Core 评估后择一, existing unittest suite, optional temporary PostgreSQL test DB.

---

## 前置条件

- 阶段 02 gate 是 `PASS`。
- 阶段 03 gate 是 `PASS`。
- 阶段 04 gate 是 `PASS`。
- PostgreSQL 正式表已有可对账通过的数据。
- OA Mongo 只读边界仍有效。
- app 当前 Mongo 模式全量测试通过。

## 阶段边界

允许：

- 新增 PostgreSQL 连接配置和 repository/state store。
- 新增测试数据库集成测试。
- 在本地/测试库写 PostgreSQL。
- 在生产启用只读 smoke 或受控 Postgres 模式验证。

禁止：

- 修改 OA Mongo。
- 直接把 service 业务逻辑散落改成 SQL。
- 默认启动强依赖 PostgreSQL，导致 Mongo 模式不可用。
- 在未通过 shadow-read/dual-write 前切生产用户读写。
- 用旧 app Mongo 全量覆盖 PostgreSQL。

## 建议新增/修改文件

| 路径 | 动作 | 责任 |
| --- | --- | --- |
| `backend/src/fin_ops_platform/services/state_store_protocol.py` | Create | `ApplicationStateStore` public method Protocol。 |
| `backend/src/fin_ops_platform/services/state_store_factory.py` | Create/Modify | 根据配置选择 Mongo/local/Postgres store。 |
| `backend/src/fin_ops_platform/services/postgres_state_store.py` | Create | PostgreSQL state store 主实现。 |
| `backend/src/fin_ops_platform/services/postgres_connection.py` | Create | PostgreSQL connection/pool/config。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/` | Create | 按领域拆分 SQL repository。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/core.py` | Create | imports/invoices/bank/files。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py` | Create | workbench/matching/no OA/categories。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py` | Create | settings/jobs/health/tax/ETC/turnover。 |
| `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` | Create | read model/search。 |
| `backend/src/fin_ops_platform/app/server.py` | Modify | 使用 state store factory；Mongo 默认行为不变。 |
| `backend/src/fin_ops_platform/app/main.py` | Modify if needed | `--check` 输出 storage backend；不触发未选 backend。 |
| `backend/requirements.txt` | Modify if needed | PostgreSQL driver，需有明确理由。 |
| `tests/test_state_store_contract.py` | Create | Mongo fake/Postgres store contract tests。 |
| `tests/test_postgres_state_store.py` | Create | PostgreSQL store 单元/集成测试。 |
| `tests/test_app_postgres_mode.py` | Create | app 在 Postgres 模式 readiness/API smoke。 |
| `docs/database-migration/05-postgresql-repository-tests.md` | Modify | 阶段执行记录。 |

## 配置设计

新增环境变量建议：

| 变量 | 值 | 说明 |
| --- | --- | --- |
| `FIN_OPS_APP_STORAGE_BACKEND` | `local_pickle` / `mongo` / `postgres` / `dual` | app 写事实源；阶段 05 只实现 `postgres`，`dual` 可预留到阶段 06。 |
| `FIN_OPS_APP_READ_BACKEND` | `storage` / `mongo` / `postgres` / `shadow` | app 读来源；阶段 05 实现 `postgres` smoke，`shadow` 到阶段 06。 |
| `DATABASE_URL` | redacted | PostgreSQL 连接。不得打印完整值。 |
| `FIN_OPS_POSTGRES_CONNECT_TIMEOUT_SECONDS` | integer | 连接超时。 |
| `FIN_OPS_POSTGRES_STATEMENT_TIMEOUT_MS` | integer | statement timeout。 |
| `FIN_OPS_POSTGRES_POOL_SIZE` | integer | 连接池大小。 |

默认行为：

- 未设置 PostgreSQL backend 时，现有 `ApplicationStateStore` 行为保持不变。
- `FIN_OPS_STORAGE_MODE=mongo_only` 继续支持。
- PostgreSQL 配置缺失只应阻断 PostgreSQL 模式，不应阻断 Mongo 模式。

## Repository contract

必须覆盖 `code-evidence-index.md` 中列出的 `ApplicationStateStore` public 方法，至少分批实现：

### 基础/设置/OA app cache

- `load()`
- `save(payload)`
- `load_app_settings()`
- `save_app_settings()`
- `load_oa_sync_state()`
- `save_oa_sync_state()`
- `load_manual_oa_imports()`
- `save_manual_oa_imports()`
- `add_manual_oa_imports()`
- `remove_manual_oa_import()`
- `load_oa_attachment_invoice_cache_entry()`
- `save_oa_attachment_invoice_cache_entry()`
- `clear_oa_attachment_invoice_cache()`

### 导入和文件

- `store_import_file()`
- `read_import_file()`
- `delete_import_files()`
- `import_session_exists()`
- `import_file_exists()`
- `import_batch_exists()`
- `invoice_exists()`
- `transaction_exists()`

### 工作台

- `load_workbench_pair_relations()`
- `save_workbench_pair_relations()`
- `load_workbench_read_models()`
- `save_workbench_read_models()`
- `load_workbench_candidate_matches()`
- `save_workbench_candidate_matches()`
- `save_workbench_matching_dirty_scopes()`
- `save_workbench_overrides()`
- `save_workbench_exception_cases()`

### 银行/免 OA/往来/读模型

- `load_bank_transaction_categories()`
- `save_bank_transaction_categories()`
- `load_no_oa_bank_batches()`
- `save_no_oa_bank_batches()`
- `load_turnover_relations()`
- `save_turnover_relations()`
- `load_turnover_relation_audit_log()`
- `save_turnover_relation_audit_log()`
- `load_turnover_ledger_extras()`
- `save_turnover_ledger_extras()`
- `load_cost_statistics_read_models()`
- `save_cost_statistics_read_models()`
- `load_tax_offset_read_models()`
- `save_tax_offset_read_models()`

### 税金/ETC/运维

- `load_tax_certified_imports()`
- `save_tax_certified_imports()`
- `load_etc_state()`
- `save_etc_state()`
- `load_etc_reconciliation_state()`
- `save_etc_reconciliation_state()`
- `store_etc_reconciliation_file()`
- `read_etc_reconciliation_file()`
- `store_etc_invoice_file()`
- `read_etc_invoice_file()`
- `etc_invoice_file_exists()`
- `delete_etc_invoice_file()`
- `save_historical_etc_repair_bundle()`
- `load_historical_etc_repair_bundle_metadata()`
- `read_historical_etc_repair_bundle()`
- `save_historical_etc_repair_parsed_seed()`
- `load_historical_etc_repair_parsed_seeds()`
- `load_historical_etc_repair_parsed_seed()`
- `load_historical_etc_repair_states()`
- `save_historical_etc_repair_states()`
- `load_background_jobs()`
- `save_background_jobs()`
- `load_app_health_alerts()`
- `save_app_health_alerts()`

## 并行任务

### 任务 5.1：连接、配置和 factory

**Files:**

- Create: `backend/src/fin_ops_platform/services/postgres_connection.py`
- Create/Modify: `backend/src/fin_ops_platform/services/state_store_factory.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_app_postgres_mode.py`

**Steps:**

- [ ] 评估 `backend/requirements.txt` 是否已有 PostgreSQL driver。
- [ ] 如新增 `psycopg`，记录理由：需要参数化 SQL、事务、连接池；不引入 ORM。
- [ ] 实现 `PostgresSettings`，从 `DATABASE_URL` 和 `FIN_OPS_POSTGRES_*` 读取。
- [ ] 实现 URI 脱敏函数。
- [ ] 实现连接 health check：`select 1`、`current_database()`、schema migration version。
- [ ] 实现 state store factory：
  - Mongo/local 默认路径不变。
  - PostgreSQL 模式才初始化 Postgres connection。
- [ ] `Application.__init__` 改为通过 factory 获取 state store。
- [ ] 测试 Mongo 模式不需要 `DATABASE_URL`。
- [ ] 测试 Postgres 模式缺少 `DATABASE_URL` 报清晰错误。
- [ ] 测试 `--check` 输出当前 backend，但不泄漏 URI。

**Acceptance:**

- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` 在默认模式通过。
- PostgreSQL 模式连接测试在测试库通过。

### 任务 5.2：state store Protocol 和 contract tests

**Files:**

- Create: `backend/src/fin_ops_platform/services/state_store_protocol.py`
- Create: `tests/test_state_store_contract.py`

**Steps:**

- [ ] 将 `ApplicationStateStore` public method 语义写成 `Protocol`。
- [ ] 建立 contract fixtures：settings、manual OA imports、attachment cache、jobs、read models、workbench relations、tax/ETC state。
- [ ] 每个 contract test 接收 store factory。
- [ ] 先让现有 `ApplicationStateStore` 通过 contract。
- [ ] 新增 Postgres store 后必须跑同一组 contract。

**Acceptance:**

- Contract tests 能发现缺方法、返回结构差异、幂等差异。
- 不要求一次覆盖全部业务细节，但必须覆盖所有 public method 的空值、写入、读取、覆盖更新。

### 任务 5.3：PostgresStateStore 基础读

**Files:**

- Create: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/core.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- Test: `tests/test_postgres_state_store.py`

**Scope:**

- settings
- background jobs
- app health alerts
- bank categories
- no OA batches
- turnover relations/extras
- tax/ETC snapshots
- read model load

**Steps:**

- [ ] 实现 `PostgresStateStore.__init__`，接收 connection/pool。
- [ ] 实现 JSONB 到 dataclass/domain object 的 mapper。
- [ ] 实现 `load_app_settings` / `save_app_settings` round-trip。
- [ ] 实现 `load_background_jobs`。
- [ ] 实现 `load_bank_transaction_categories`。
- [ ] 实现 read model load。
- [ ] 测试从阶段 04 已转换数据读取后，与 export normalized payload 等价。

**Acceptance:**

- app 在 Postgres read mode 下可初始化 service。
- 不触发 OA Mongo 写入。

### 任务 5.4：核心写路径

**Files:**

- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Modify/Create: `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- Test: `tests/test_postgres_state_store.py`

**Scope:**

- settings save
- background jobs save/update
- workbench pair relations save
- workbench overrides save
- exception cases save
- candidate matches save
- dirty scopes save
- bank categories save
- no OA batches save

**Steps:**

- [ ] 每个写方法使用事务。
- [ ] 使用 upsert 时必须保留 version/updated_at 语义。
- [ ] expected version 冲突要能被 service 层转成现有错误语义。
- [ ] 写 audit/outbox 的边界要明确；阶段 05 可先写 `audit.events` 基础事件。
- [ ] 测试失败回滚。
- [ ] 测试重复保存幂等。
- [ ] 测试并发 version conflict。

**Acceptance:**

- 现有 service 不需要知道 backend 是 Mongo 还是 Postgres。
- 关键写路径有 contract tests。

### 任务 5.5：文件兼容层

**Files:**

- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Create/Modify: `backend/src/fin_ops_platform/services/postgres_repositories/files.py`
- Test: `tests/test_postgres_state_store.py`
- Test: `tests/test_import_file_service.py`

**Steps:**

- [ ] `read_import_file` 支持阶段 04 转换出的 `gridfs://` legacy reference。
- [ ] `store_import_file` 在 Postgres 模式写 `app.file_objects` 和 `app.import_files` 元数据。
- [ ] 文件内容第一版允许继续写 GridFS 或本地兼容路径；必须在 metadata 标明 storage backend。
- [ ] `delete_import_files` 只删除 app-owned 文件引用，不碰 OA Mongo。
- [ ] ETC reconciliation/invoice file 方法同样支持 legacy reference。
- [ ] 测试旧 GridFS reference 可读取。
- [ ] 测试新文件元数据写 PostgreSQL。

**Acceptance:**

- 导入预览/确认能读取阶段 04 迁移后的旧文件引用。
- 文件内容迁移可延期到后续文件阶段，不阻断 repository 切换。

### 任务 5.6：API 兼容和 Postgres 模式测试

**Files:**

- Create: `tests/test_app_postgres_mode.py`
- Modify: existing API tests only if adding backend parametrization

**Steps:**

- [ ] 增加测试库 fixture，要求 `FIN_OPS_TEST_DATABASE_URL`，无测试库时 skip integration。
- [ ] 对测试库 apply 0001-0007。
- [ ] 导入一小组阶段 04 fixture 数据。
- [ ] 启动 app with `FIN_OPS_APP_STORAGE_BACKEND=postgres`。
- [ ] 验证 `/health`、`/api/session/me`、settings、background jobs、imports history、bank details、workbench single month、search、tax、ETC smoke。
- [ ] 复用现有 API DTO 断言，禁止改前端 DTO。
- [ ] 测试 Mongo 模式全量仍通过。

**Acceptance:**

- Postgres 模式下关键 API smoke 通过。
- Mongo 模式下现有 1118+ tests 仍通过。

## 串行执行顺序

1. 定义 state store Protocol 和 contract tests。
2. 实现 config/connection/factory，保持默认 Mongo/local 行为。
3. 实现基础读。
4. 实现核心写。
5. 实现文件兼容。
6. 增加 Postgres 模式 API smoke。
7. 在本地测试库跑 integration。
8. 在服务器 Postgres 上做只读/受控 smoke。
9. 更新阶段 05 文档。

## 推荐命令

默认全量：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

Postgres integration：

```bash
export FIN_OPS_TEST_DATABASE_URL='<redacted>'
export FIN_OPS_ALLOW_POSTGRES_TEST_DB=1
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store_contract tests.test_postgres_state_store tests.test_app_postgres_mode -v
```

Postgres app check：

```bash
FIN_OPS_APP_STORAGE_BACKEND=postgres \
FIN_OPS_APP_READ_BACKEND=postgres \
DATABASE_URL='<redacted>' \
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

## Gate

`PASS` 条件：

- Mongo/default 模式全量测试通过。
- PostgreSQL store contract tests 通过。
- PostgreSQL 模式 app readiness 通过。
- 关键 API smoke 在 Postgres 模式通过。
- OA Mongo 仍只读；未新增写 OA 代码路径。
- 所有新增 SQL 参数化，不拼接用户输入。
- 错误日志不泄漏完整 URI/密码/token。
- 文档记录 Postgres mode 测试库、commands、结果、剩余缺口。

`BLOCKED` 条件：

- Mongo 模式被破坏。
- Postgres 模式启动需要 OA Mongo 写权限。
- 任一 public state store method 未覆盖且被现有 service 调用。
- DTO 与前端 API 合约不兼容。
- 写路径缺事务或 version conflict 语义。
- 文件读取无法兼容阶段 04 迁移后的 legacy reference。

## 阶段产物

- `PostgresStateStore`
- state store Protocol/contract tests
- Postgres connection/factory
- Postgres mode API smoke tests
- 阶段 05 执行报告

## 2026-05-20 执行记录

### 执行范围

- 使用 5 个只读子代理并行梳理：
  - A：`ApplicationStateStore` public contract、app 初始化、`--check`。
  - B：imports/invoices/bank/files 与 GridFS legacy reference。
  - C：workbench/no OA/categories/read models/search。
  - D：settings/jobs/health/tax/ETC/turnover。
  - E：测试策略、fixtures、skip/测试库 guard。
- 主线程统一实现和写文档；子代理未写文件、未连接数据库、未触碰 Mongo。
- 未对 OA Mongo `form_data_db.form_data` 做任何读写。
- 未修改、重启生产服务。

### 已落地文件

| 文件 | 结果 |
| --- | --- |
| `backend/src/fin_ops_platform/services/postgres_connection.py` | 新增 `PostgresSettings`、URI 脱敏、`PostgresConnection`、health summary。 |
| `backend/src/fin_ops_platform/services/state_store_factory.py` | 新增 state store factory；默认仍为现有 `ApplicationStateStore`，仅 `FIN_OPS_APP_STORAGE_BACKEND=postgres` 初始化 Postgres。 |
| `backend/src/fin_ops_platform/services/state_store_protocol.py` | 新增 `ApplicationStateStoreProtocol`，覆盖阶段 05 所列 public methods。 |
| `backend/src/fin_ops_platform/services/postgres_state_store.py` | 新增 Postgres state store；支持 settings、OA cache、manual imports、核心 snapshot、read model fallback、文件元数据、legacy GridFS read adapter。 |
| `backend/src/fin_ops_platform/app/server.py` | 改为通过 factory 构造 store；readiness 增加 Postgres health summary，且不输出 URI。 |
| `backend/requirements.txt` | 新增 `psycopg[binary,pool]==3.3.3`，用于参数化 SQL、连接 health check 和后续事务/连接池。 |
| `tests/test_state_store_contract.py` | 新增 local store + fake Postgres store contract tests。 |
| `tests/test_postgres_state_store.py` | 新增 Postgres 配置、脱敏、factory、snapshot、文件、legacy GridFS adapter 单元测试。 |
| `tests/test_app_postgres_mode.py` | 新增默认模式不依赖 Postgres、Postgres 缺 URL 清晰失败、readiness 不泄密测试。 |

### 关键设计决策

- 默认运行路径不读取 `DATABASE_URL`，也不 import/初始化 Postgres store；这保护现有 local/Mongo 模式。
- PostgreSQL 模式使用 `FIN_OPS_APP_STORAGE_BACKEND=postgres` 显式启用。
- 连接配置优先读取 `FIN_OPS_POSTGRES_DATABASE_URL`，其次 `DATABASE_URL`；readiness 和错误记录不得输出完整 URI。
- 第一版 `PostgresStateStore` 保持现有 service snapshot contract：
  - 已迁移正式表可作为读取 fallback。
  - runtime 写入优先保存到 `app.app_settings` 中的 `state:<key>` JSONB snapshot，避免大范围改动 service 业务逻辑。
  - `app.file_objects` / `app.import_files` 元数据写入已接入 `store_import_file()`。
- 文件兼容层支持两类 legacy ref grammar：
  - 旧 store：`gridfs://<file_id>/<name>`。
  - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`。
  - 实际读取通过注入式 `LegacyGridFSFileReader`，没有 reader 时返回清晰错误；删除 legacy GridFS ref 只标记 `app.import_files.status='deleted'`，不删除 GridFS content。

### 验证结果

已运行：

```bash
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py -q
```

结果：

```text
14 passed, 5 warnings, 6 subtests passed
```

已运行：

```bash
python -m pytest -q
```

结果：

```text
1139 passed, 5 skipped, 5 warnings, 13 subtests passed
```

已运行：

```bash
tmpdir=$(mktemp -d)
FIN_OPS_DATA_DIR="$tmpdir" PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

结果：

```text
storage.backend = local_pickle
storage.mode = auto
status = ready
```

### 未执行项和剩余缺口

- 未执行真实 PostgreSQL integration：本轮未提供/未使用 `FIN_OPS_TEST_DATABASE_URL`，因此没有在 disposable test DB 上 apply 0001-0007 并跑真实数据库 contract。
- 未执行服务器 smoke：本阶段没有修改生产服务，也没有在生产 Postgres 写测试数据。
- `PostgresStateStore` 第一版尚未把所有 workbench/no OA/categories/read model 写路径完全范式化写入正式表；当前策略是正式表 fallback 读取 + runtime JSONB snapshot 保存。
- 多表业务 mutation 尚未实现单事务 repository 边界；`PostgresConnection.execute()` 当前是单语句连接生命周期，后续阶段需要为联动写入补事务上下文。
- API smoke 当前覆盖 readiness/factory 层；尚未用真实测试库 fixture 覆盖 `/api/workbench`、`/api/search`、tax、ETC、no OA 等完整 Postgres mode HTTP DTO。

### Gate 状态

本地默认模式 gate：`PASS`。

阶段 05 完整生产切换 gate：`PARTIAL`。原因是真实 PostgreSQL integration、服务器只读 smoke、完整领域 repository 事务化写入尚未执行/完成。当前产物已经提供 Postgres mode 接入骨架、contract tests、默认模式保护和可继续推进真实测试库验证的基础。
