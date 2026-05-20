# 08 阶段 Codex 执行 Prompt：PostgreSQL domain repository 最终闭合

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 08：基于阶段 07 的 `PARTIAL` 结果，必须解决阶段 07 以及此前所有未完成内容，使 PostgreSQL mode 覆盖 app 自身数据的关键 runtime domains，并达到“可以生成后续 shadow/dual-write/cutover prompt”的前置条件。

阶段 08 不是生产切换阶段。阶段 08 完成后必须能清楚回答：

1. app 自身数据是否已经可以完整接入 PostgreSQL。
2. OA 数据是否仍只从 Mongo OA 只读读取。
3. 哪些 domain 已经由 PostgreSQL 正式表承担 runtime 读写。
4. 哪些 domain 如仍无法完成，具体阻塞是什么。
5. 用户需要提供什么信息、权限、schema 决策或业务确认才能解除阻塞。

如果阶段 08 无法完全完成，最终输出和文档必须用 `BLOCKED` 或 `PARTIAL` 标明原因，不得把 skip、fallback 或 JSON snapshot 临时兜底包装成完成。

阶段 08 完成标准：

1. 默认 local/Mongo 模式全量测试通过。
2. 无 `FIN_OPS_TEST_DATABASE_URL` 时 PostgreSQL integration tests 安全 skip。
3. 有 disposable PostgreSQL test DB 或本机临时 PostgreSQL cluster 时，migrations、repository integration、state store contract、API smoke 全部通过。
4. 生产 PostgreSQL 只允许只读 smoke；不得切换、不得 dual-write、不得重启服务。
5. `PostgresStateStore` 的关键 runtime domains 不再以 `app.app_settings state:<key>` JSON snapshot 作为主要运行时读写路径；正式表必须优先读写，JSON snapshot 只能作为兼容 fallback。
6. `imports`、`file_imports` 已保持阶段 07 PASS 状态，不能回退。
7. tax certified import、ETC、ETC reconciliation、historical ETC、turnover、workbench/no OA/category、read models/search index、jobs/health/settings 的正式表 mapper、domain hydration、event/history 表写入必须闭合，或明确记录无法闭合的 blocker。
8. `changed_case_ids`、`changed_row_ids`、`changed_scope_keys`、`changed_scope_months`、changed job ids、changed tax/ETC session ids 等局部写入语义必须正确：只改应改的数据，删除 stale 数据时不能误删其他 scope。
9. API DTO 不变，前端契约不变。
10. 文档更新为阶段 08 执行记录和 Gate 判定。

你必须使用子代理并行完成可并行任务：

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- 主线程负责最终集成、冲突处理、测试、文档和 Gate 判定。
- 子代理可以只读梳理，也可以作为 worker 修改代码；如果让 worker 写代码，必须给出明确文件所有权，避免多个 worker 修改同一文件。
- 如果当前 subagent 数量达到上限，先关闭不再需要的旧 agent。

硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. OA Mongo 只能继续作为现有 `MongoOAAdapter` 的只读源；阶段 08 不实现 OA 数据写回。
3. app Mongo `fin_ops_platform_app` 不得写入。只允许只读兼容校验；不得重导出、清理、建索引或改 schema。
4. 生产 PostgreSQL `fin_ops` 只能做只读 smoke/count/schema/readiness 检查；不得在生产库做 destructive truncate、seed、contract write、API write smoke。
5. 所有 destructive integration test 必须使用 disposable PostgreSQL test DB。DB 名必须包含 `test`，否则必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；如果无法证明是 test DB，立即停止并记录 `BLOCKED`。
6. 优先使用本机临时 PostgreSQL cluster 跑真实 integration；必须使用 UTF8 cluster，例如 `initdb --encoding=UTF8 --locale=C`。测试结束必须 stop cluster 并删除 temp dir。
7. 禁止修改或重启生产 `fin-ops.service`；禁止修改生产运行配置；禁止切换生产 backend；禁止 shadow-read/dual-write/生产 cutover。
8. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码或 prompt。所有 URI 输出必须脱敏。
9. 不得把业务 SQL 散落到 app route/service 业务逻辑里。service 层继续通过 state store/repository 边界访问数据。
10. 默认 local/Mongo 模式必须保持现有行为。未配置 PostgreSQL 时，不得读取生产 `DATABASE_URL`，不得初始化 PostgreSQL connection，不得影响 `python -m pytest -q` 和 `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`。
11. PostgreSQL 模式下所有 SQL 必须参数化；禁止用用户输入拼 SQL。只允许对受控 schema/table 名使用白名单拼接。
12. PostgreSQL 写路径必须有事务边界；失败必须 rollback；version/expected_version 语义必须与现有 service 错误语义兼容。
13. 文件读取必须保持阶段 07 已有兼容：
    - app-owned local path
    - 旧 store：`gridfs://<file_id>/<name>`
    - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`
14. 不修改前端 DTO、不改 API 返回结构。若 PostgreSQL mode 需要 DTO 变化，先记录 `BLOCKED`，不要自行修改前端契约。
15. 如果发现阶段 02 schema 或阶段 04 数据不足以支撑某 public state store method，不得静默 fallback 到 Mongo 写路径；必须补 repository/schema/mapping，或记录明确 `BLOCKED`。

阶段 07 已完成事实：

- 阶段 07 Gate：`PARTIAL`。
- 已新增：
  - `backend/src/fin_ops_platform/services/postgres_repositories/__init__.py`
  - `backend/src/fin_ops_platform/services/postgres_repositories/core.py`
  - `tests/test_postgres_repositories_core.py`
  - `docs/database-migration/07-postgresql-domain-repository-completion.md`
- 已修改：
  - `backend/src/fin_ops_platform/services/postgres_connection.py`
  - `backend/src/fin_ops_platform/services/postgres_state_store.py`
  - `tests/test_postgres_state_store_integration.py`
  - `tests/test_app_postgres_mode_integration.py`
- 阶段 07 已闭合：
  - `load()["imports"]` 可从正式表恢复并被 `ImportNormalizationService.from_snapshot()` 消费。
  - `load()["file_imports"]` 可从正式表恢复并被 `FileImportService.from_snapshot()` 消费。
  - `PostgresStateStore.save()` 已对 imports、file_imports、categories、workbench/no-OA/read models、turnover、cost/tax read models、jobs/health 等已有路径做分发写入。
  - `full_state` 不再覆盖正式表恢复出来的非空 domain state。
  - `workbench_read_models.changed_scope_keys` stale 删除已覆盖。
  - `workbench_candidate_matches.changed_scope_months` 按月 stale 删除已覆盖。
  - `bank_transaction_categories` 已兼容 `category_code/category_label`。
  - bytes 文本归一化已补齐。
- 阶段 07 已验证：
  - 无 `FIN_OPS_TEST_DATABASE_URL`：`9 passed, 5 skipped`
  - 本机 UTF8 disposable PostgreSQL `fin_ops_stage07_test`：`8 passed, 12 subtests passed`
  - 阶段相关测试：`29 passed, 8 skipped, 10 subtests passed`
  - 默认全量测试：`1144 passed, 13 skipped, 17 subtests passed`
  - 默认 app check：`status=ready, storage.backend=local_pickle`
  - 生产只读 smoke：`fin-ops.service active`，`schema_migrations=0001..0007`
- 生产只读 counts：
  - `app.import_batches=6`
  - `app.import_batch_rows=897`
  - `app.import_files=31`
  - `app.invoices=391`
  - `app.bank_transactions=431`
  - `read_model.search_index_rows=822`

阶段 07 仍未闭合、阶段 08 必须优先解决：

1. tax certified import、ETC、historical ETC 仍主要依赖 JSONB snapshot，尚未拆出完整正式表 mapper 和 dataclass/Enum/Decimal/datetime hydration。
2. pair relation/no OA/category/turnover 的 event/history 表写入仍未完整闭合。
3. `read_model.search_index_rows` 仍是迁移/预留表；尚未把 app search runtime 切到正式 search index repository，或明确证明当前 app search 可从正式表稳定派生且无需 search index runtime。
4. repository package 当前只拆出 core；workbench/read_models/ops_tax_etc 仍在 `PostgresStateStore` 内集中实现，需继续拆分或明确无法拆分原因。
5. 05/06 以来仍需强化的事务 rollback、局部更新、正式表优先读取、API smoke 范围。

必须先读的文档：

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `backend/README.md`
- `docs/index.md`
- `docs/dev/index.md`
- `docs/dev/backend.md`
- `docs/dev/testing.md`
- `docs/database-migration/README.md`
- `docs/database-migration/04-staging-transform-reconciliation.md`
- `docs/database-migration/05-postgresql-repository-tests.md`
- `docs/database-migration/06-postgresql-integration-repository-closure.md`
- `docs/database-migration/07-postgresql-domain-repository-completion.md`
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md`
- `docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`

必须先读的代码：

- `backend/src/fin_ops_platform/services/postgres_repositories/__init__.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/core.py`
- `backend/src/fin_ops_platform/services/postgres_connection.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/state_store_protocol.py`
- `backend/src/fin_ops_platform/services/tax_certified_import_service.py`
- `backend/src/fin_ops_platform/services/tax_offset_service.py`
- `backend/src/fin_ops_platform/services/etc_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `backend/src/fin_ops_platform/services/historical_etc_repair_service.py`
- `backend/src/fin_ops_platform/services/turnover_relation_service.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `backend/src/fin_ops_platform/services/bank_transaction_category_service.py`
- `backend/src/fin_ops_platform/services/workbench_read_model_service.py`
- `backend/src/fin_ops_platform/services/workbench_candidate_match_service.py`
- `backend/src/fin_ops_platform/services/search_service.py`
- `backend/src/fin_ops_platform/services/background_job_service.py`
- `backend/src/fin_ops_platform/services/app_health_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/domain/models.py`
- `backend/src/fin_ops_platform/domain/enums.py`
- `backend/src/fin_ops_platform/postgres/migrations/0002_core_imports_invoices_bank.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0003_workbench_relations_exceptions.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0005_tax_etc_turnover_settings_jobs.sql`
- `backend/src/fin_ops_platform/postgres/migrations/0006_read_models.sql`
- `tests/postgres_test_utils.py`
- `tests/test_postgres_repositories_core.py`
- `tests/test_postgres_state_store.py`
- `tests/test_postgres_state_store_integration.py`
- `tests/test_app_postgres_mode_integration.py`
- `tests/test_state_store_contract.py`

启动步骤：

1. 记录当前 git branch 和 `git status --short`。不要 revert 非本阶段改动。
2. 运行基线：
   - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py -q`
   - `python -m pytest -q`
   - `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
3. 检查本机 PostgreSQL 工具：
   - `command -v initdb && command -v pg_ctl && command -v createdb && command -v psql`
4. 如果可用，启动 UTF8 临时 cluster，创建 `fin_ops_stage08_test`，运行真实 integration；测试结束必须 stop cluster 并删除 temp dir。
5. 如果不可用，检查 `FIN_OPS_TEST_DATABASE_URL`；无 test DB 时 integration tests 必须 skip，并在文档中记录“未完成真实 DB 验证”。
6. 使用子代理并行完成以下任务：
   - Explorer/Worker A：tax certified import mapper 和 tests。
   - Explorer/Worker B：ETC + ETC reconciliation + historical ETC mapper 和 tests。
   - Explorer/Worker C：workbench/no OA/category/turnover event/history repository 和 tests。
   - Explorer/Worker D：read model/search index repository 和 API smoke。
   - Explorer/Worker E：integration/API smoke matrix、production read-only smoke、文档 Gate 核验。

推荐文件结构：

- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/__init__.py`
- Keep/Modify: `backend/src/fin_ops_platform/services/postgres_repositories/core.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- Create if useful: `backend/src/fin_ops_platform/services/postgres_repositories/json_helpers.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Modify only if required: `backend/src/fin_ops_platform/services/postgres_connection.py`
- Modify only if schema insufficient: `backend/src/fin_ops_platform/postgres/migrations/0008_*.sql`
- Modify if 0008 added: `tests/postgres_test_utils.py`
- Create/Modify: `tests/test_postgres_repositories_workbench.py`
- Create/Modify: `tests/test_postgres_repositories_read_models.py`
- Create/Modify: `tests/test_postgres_repositories_ops_tax_etc.py`
- Modify: `tests/test_postgres_state_store_integration.py`
- Modify: `tests/test_app_postgres_mode_integration.py`
- Create: `docs/database-migration/08-postgresql-domain-repository-final-closure.md`

任务 8.0：安全基线和执行记录

- [ ] 读完必读文档和代码。
- [ ] 记录 branch 和 dirty worktree。不要 revert 非 08 改动。
- [ ] 运行基线测试。
- [ ] 创建 `docs/database-migration/08-postgresql-domain-repository-final-closure.md`。
- [ ] 文档记录阶段边界：08 不做生产 cutover。
- [ ] 文档列出 07 `PARTIAL` 剩余项。
- [ ] 确认没有任何命令触碰 `form_data_db.form_data`。

Acceptance:

- 文档存在。
- 基线结果已记录。
- 如果基线失败，先判断是否与 08 范围相关；相关则修复，不相关则记录风险。

任务 8.1：Repository package 继续拆分

- [ ] 将 `PostgresStateStore` 中 workbench/no OA/category/turnover SQL 拆到 `postgres_repositories/workbench.py`。
- [ ] 将 read model/search/cost/tax offset read model SQL 拆到 `postgres_repositories/read_models.py`。
- [ ] 将 settings/jobs/health/tax/ETC/historical ETC SQL 拆到 `postgres_repositories/ops_tax_etc.py`。
- [ ] `PostgresStateStore` 保持 public API，不直接暴露 repository。
- [ ] repositories 只接收 connection 或 transaction-like object，不读取环境变量。
- [ ] 对 schema/table 名只允许白名单，不接受用户输入。

Acceptance:

- `PostgresStateStore` public method 行为不变。
- 默认模式和 Postgres mode 测试通过。
- 新 repository 有 unit tests 或 integration tests 覆盖。

任务 8.2：tax certified import 正式表 mapper

目标表：

- `app.tax_certified_import_sessions`
- `app.tax_certified_import_batches`
- `app.tax_certified_import_records`

要求：

- [ ] 阅读 `TaxCertifiedImportService.from_snapshot()` / `snapshot()` 的 exact shape。
- [ ] 写 failing tests：正式表恢复出的 snapshot 可被 tax certified service 消费，并能继续预览/确认或查询。
- [ ] `save_tax_certified_imports()` 写 sessions/batches/records 正式表，不只写 JSON snapshot。
- [ ] `load_tax_certified_imports()` 正式表优先恢复 service 需要的 dataclass/Enum/Decimal/datetime shape。
- [ ] 处理 session files、batch/version/status、record month/amount/tax fields。
- [ ] 增加 real PostgreSQL integration：保存后重建 store/service，断言仍可查询 certified imports。

Acceptance:

- `tests/test_postgres_repositories_ops_tax_etc.py` 覆盖 tax certified mapper。
- `tests/test_postgres_state_store_integration.py` 覆盖真实 DB round-trip。
- 不改变 `/api/tax-offset/*` DTO。

任务 8.3：ETC、ETC reconciliation、historical ETC 正式表 mapper

目标表：

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

要求：

- [ ] 阅读 ETC 相关 services 的 snapshot/from_snapshot/hydrate 方法和现有 tests。
- [ ] 写 failing tests：正式表恢复出的 ETC snapshot 可被 ETC service 使用，不出现 dict 替代 dataclass 后的 attribute error。
- [ ] `save_etc_state()`、`load_etc_state()` 正式表优先。
- [ ] `save_etc_reconciliation_state()`、`load_etc_reconciliation_state()` 正式表优先。
- [ ] historical ETC bundle/seed/state metadata 正式表优先。
- [ ] 文件内容仍走现有 file object/local path/GridFS 兼容，不把大二进制塞入 JSON snapshot。
- [ ] API smoke 使用 no-OA/task-aware ETC 路径，不触发 OA draft/status endpoint。

Acceptance:

- ETC service 从 PostgreSQL 正式表恢复后现有查询和 task-aware import smoke 通过。
- 无 OA Mongo env/config 时 ETC no-OA smoke 不触发 OA Mongo。
- 若现有 schema 无法表达某 ETC nested state，必须新增 0008 migration 或记录 `BLOCKED`。

任务 8.4：workbench/no OA/category/turnover event/history 表写入

目标表：

- `app.workbench_pair_relations`
- `app.workbench_pair_relation_history`
- `app.no_oa_bank_batches`
- `app.no_oa_bank_batch_events`
- `app.bank_transaction_categories`
- `app.bank_transaction_category_events`
- `app.turnover_relations`
- `app.turnover_relation_events`

要求：

- [ ] 写 tests 覆盖 pair relation 保存同时写 history。
- [ ] 写 tests 覆盖 no OA batch submit/withdraw 写 event。
- [ ] 写 tests 覆盖 category manual/auto update 写 category event，且 `category_code/category_label` 不丢。
- [ ] 写 tests 覆盖 turnover relation create/update/withdraw 写 event。
- [ ] 局部保存参数如 `changed_case_ids` 不得误删未变数据。
- [ ] event/history 写入必须幂等或有稳定 operation id，重复保存不能制造重复事件。
- [ ] 如果 service snapshot 没有足够 event metadata，必须记录需要用户确认的 event 语义，不能凭空 invent 审计口径。

Acceptance:

- event/history 表有真实 integration counts 和 payload assertions。
- API smoke 可覆盖至少 no-OA submit 或 category update 的 PostgreSQL persistence。
- 不改变现有 API 返回结构。

任务 8.5：read model/search index runtime

目标表：

- `read_model.workbench_rows`
- `read_model.workbench_snapshots`
- `read_model.workbench_candidate_matches`
- `read_model.search_index_rows`
- `read_model.cost_statistics_read_models`
- `read_model.tax_offset_read_models`
- `job.workbench_matching_dirty_scopes`

要求：

- [ ] 明确 app search runtime 是否必须使用 `read_model.search_index_rows`。
- [ ] 如果必须使用：实现 search index repository，保存/读取 search index rows，API `/api/search` 在 PostgreSQL mode 可从正式 search index 或正式 workbench rows 返回稳定结果。
- [ ] 如果不必须使用：在文档中证明 search 可由正式表或 workbench read models 稳定派生，并说明 `search_index_rows` 仅作为迁移/加速表。
- [ ] `workbench_rows` 若已在 schema 中存在，应补 mapper 或明确不使用原因。
- [ ] dirty scopes 正式表或 settings fallback 语义必须明确。
- [ ] 增加 no-OA `/api/search` smoke：无 OA Mongo env/config，seed imports/settings 后 search 可返回结果，invalid query 仍返回现有错误。

Acceptance:

- search API smoke 在 disposable PostgreSQL test DB 通过。
- read model stale deletion 和 source_versions freshness 语义保持。
- 文档明确 `search_index_rows` 的 runtime 角色。

任务 8.6：settings/jobs/health 正式表和事务强化

目标表：

- `app.app_settings`
- `job.background_jobs`
- `audit.app_health_alerts`
- `job.outbox_events` 如需要

要求：

- [ ] settings 默认 shape 和 `ApplicationStateStore.load_app_settings()` 一致。
- [ ] jobs `type`/`job_type` 显式映射，不丢 owner/visibility/progress/result/error/retry/attention。
- [ ] health alerts `records` shape 保持。
- [ ] 加 rollback integration：一次跨表 save 中途异常必须 rollback。
- [ ] 如果需要 outbox，必须和业务写同事务；如果不需要，文档说明原因。

Acceptance:

- 事务 commit/rollback tests 通过。
- readiness 和 `/api/app-health` 不泄漏 URI/password/token。

任务 8.7：API smoke 扩展

必须在 no-OA PostgreSQL mode 下执行，且清空以下环境变量：

- `FIN_OPS_OA_MONGO_URI`
- `FIN_OPS_OA_MONGO_DATABASE`
- `FIN_OPS_OA_MONGO_COLLECTION`
- `FIN_OPS_STATE_MONGO_URI`
- `FIN_OPS_STATE_MONGO_DATABASE`

建议 smoke：

- [ ] `/health`
- [ ] `/api/session/me`
- [ ] `/api/app-health`
- [ ] `/api/workbench/settings`
- [ ] `POST /api/workbench/settings/projects` 后 rebuild app 再读
- [ ] `POST /imports/preview` + `POST /imports/confirm` 后 rebuild app 再查 batch
- [ ] `GET /api/no-oa-bank-batches` + submit/withdraw 中至少一个写路径
- [ ] `GET /api/tax-offset` + certified import preview/confirm 或可证明的 tax read model route
- [ ] ETC task-aware import/reconciliation smoke，禁止 OA draft/status endpoints
- [ ] `/api/search` valid/invalid query

Acceptance:

- 所有 smoke 在 disposable PostgreSQL test DB 通过。
- 响应中不含完整 URI、password、token。
- 无 OA Mongo env/config 时不创建 `MongoOAAdapter`。

任务 8.8：生产只读 smoke

只允许执行：

- [ ] `systemctl is-active fin-ops.service`
- [ ] `select string_agg(version, ',' order by version) from public.schema_migrations`
- [ ] 关键正式表 count
- [ ] 如新增 0008 migration，本阶段仍不得直接在生产执行 migration；只能记录“生产未应用 0008，因此生产只读 smoke 仍停留在 0001..0007”。

禁止：

- [ ] 不得在生产库写 seed/test 数据。
- [ ] 不得 truncate。
- [ ] 不得重启服务。
- [ ] 不得修改运行环境变量。

Acceptance:

- 文档记录只读 smoke 结果。
- 所有连接 URI 和密码均脱敏或不记录。

任务 8.9：文档和 Gate 判定

- [ ] 更新 `docs/database-migration/08-postgresql-domain-repository-final-closure.md`。
- [ ] 写清楚每个 domain 的状态：`PASS` / `PARTIAL` / `BLOCKED`。
- [ ] 如果 `PARTIAL` 或 `BLOCKED`，必须写：
  - 无法完成的具体功能。
  - 代码或 schema 证据。
  - 为什么当前 agent 无法安全完成。
  - 用户需要做什么，例如提供业务审计口径、确认 schema 设计、提供 disposable test DB、允许新增 0008 migration、提供非生产样本文件等。
- [ ] 若所有 Gate PASS，明确“可以生成下一阶段 shadow/dual-write/cutover prompt”，但不得执行 cutover。

Acceptance:

- 文档可作为后续阶段事实源。
- 不能只写“测试通过”；必须逐项列出 domain gate。

最终必须运行的验证：

```bash
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_workbench.py tests/test_postgres_repositories_read_models.py tests/test_postgres_repositories_ops_tax_etc.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py -q
python -m pytest -q
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
```

还必须在 UTF8 disposable PostgreSQL test DB 上运行：

```bash
python -m pytest tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
```

如果新增 migration，还必须运行：

```bash
python -m pytest tests/test_postgres_migrations.py tests/test_postgres_test_utils.py -q
```

完成后的最终回复必须包含：

1. 08 Gate：`PASS` / `PARTIAL` / `BLOCKED`。
2. 已修改文件。
3. 已运行验证和结果。
4. 是否触碰 OA Mongo `form_data_db.form_data`：必须回答“没有”。
5. 是否写 app Mongo：必须回答“没有”。
6. 是否写生产 PostgreSQL：必须回答“没有，只读 smoke”。
7. 如果无法完成：原因、阻塞证据、用户需要做什么。
```
