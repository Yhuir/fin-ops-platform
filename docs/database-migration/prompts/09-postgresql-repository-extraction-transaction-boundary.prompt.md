# 09 阶段 Codex 执行 Prompt：PostgreSQL repository extraction + transaction boundary

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 09：基于阶段 08 的 `PARTIAL` 结果，只做 PostgreSQL repository package 拆分、事务边界收口、search index runtime 决策记录和回归验证，使阶段 08 剩余工程收口项闭合，并达到可以生成后续 shadow/dual-write/cutover prompt 的前置条件。

阶段 09 不是生产切换阶段。阶段 09 完成后必须能清楚回答：

1. `PostgresStateStore` 是否只保留 public state-store API、文件存储桥接、snapshot fallback 和 repository 编排，不再集中承载大量 domain SQL。
2. app 自身关键 runtime domains 的 PostgreSQL 正式表读写是否仍保持阶段 08 已闭合状态。
3. 多表写入是否通过明确 transaction boundary 保证失败 rollback。
4. search runtime 是否继续实时派生，还是切到 `read_model.search_index_rows`，以及该决策的依据。
5. 若仍无法完成，具体 blocker 是 schema、业务决策、测试环境还是代码边界。

如果阶段 09 无法完全完成，最终输出和文档必须用 `BLOCKED` 或 `PARTIAL` 标明原因，不得把“测试 skip”“还留在 PostgresStateStore 里”或“只做了文档说明”包装成完成。

阶段 09 完成标准：

1. 默认 local/Mongo 模式全量测试通过。
2. 无 `FIN_OPS_TEST_DATABASE_URL` 时 PostgreSQL integration tests 安全 skip。
3. 有 disposable PostgreSQL test DB 或本机临时 PostgreSQL cluster 时，migrations、repository integration、state store contract、API smoke 全部通过。
4. 生产 PostgreSQL 只允许只读 smoke；不得切换、不得 dual-write、不得重启服务。
5. `PostgresStateStore` public API 和 API DTO 不变。
6. `PostgresStateStore` 中 workbench/no OA/category/turnover SQL 已抽到 `postgres_repositories/workbench.py`。
7. `PostgresStateStore` 中 workbench/candidate/cost/tax read model SQL 已抽到 `postgres_repositories/read_models.py`。
8. `PostgresStateStore` 中 settings/jobs/health/tax certified/ETC/ETC reconciliation/historical ETC SQL 已抽到 `postgres_repositories/ops_tax_etc.py`。
9. 新 repository 只接收 connection 或 transaction-like object；不得读取环境变量；不得知道 Mongo 或 OA 凭据。
10. 多表写路径必须通过 transaction boundary 执行；任一中途失败必须 rollback，且新增或更新 tests 证明 rollback。
11. 阶段 08 已闭合能力不能回退：
    - imports/file_imports 正式表优先恢复；
    - tax certified import 正式表 round-trip；
    - ETC 正式表 round-trip；
    - ETC reconciliation task/file 正式表 round-trip；
    - historical ETC bundle/parsed seed/state 正式表 round-trip；
    - pair relation/no OA/category/turnover event/history 正式表写入；
    - `load_turnover_relations()` 返回 service 需要的 list shape；
    - GridFS/local file 兼容读取。
12. search runtime 必须明确决策：
    - 如果保持 `SearchService` 从 workbench loader 实时派生，必须在文档写明 `read_model.search_index_rows` 继续作为迁移/加速/后续优化表，不是 runtime source，并有 no-OA PostgreSQL API smoke 证明 `/api/search` 可用。
    - 如果切到 `read_model.search_index_rows`，必须实现 repository、刷新时机、stale 删除、API smoke 和回退说明；不得改变前端 DTO。
13. 文档更新为阶段 09 执行记录和 Gate 判定。

你必须使用子代理并行完成可并行任务：

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- 主线程负责最终集成、冲突处理、测试、文档和 Gate 判定。
- 子代理可以只读梳理，也可以作为 worker 修改代码；如果让 worker 写代码，必须给出明确文件所有权，避免多个 worker 修改同一文件。
- Worker 必须知道“不是独自在 codebase 中工作”，不得 revert 其他 worker 或用户改动。
- 如果当前 subagent 数量达到上限，先关闭不再需要的旧 agent。

硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. OA Mongo 只能继续作为现有 `MongoOAAdapter` 的只读源；阶段 09 不实现 OA 数据写回。
3. app Mongo `fin_ops_platform_app` 不得写入。只允许只读兼容校验；不得重导出、清理、建索引或改 schema。
4. 生产 PostgreSQL `fin_ops` 只能做只读 smoke/count/schema/readiness 检查；不得在生产库做 destructive truncate、seed、contract write、API write smoke。
5. 所有 destructive integration test 必须使用 disposable PostgreSQL test DB。DB 名必须包含 `test`，否则必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；如果无法证明是 test DB，立即停止并记录 `BLOCKED`。
6. 优先使用本机临时 PostgreSQL cluster 跑真实 integration；必须使用 UTF8 cluster，例如 `initdb --encoding=UTF8 --locale=C`。测试结束必须 stop cluster 并删除 temp dir。
7. 禁止修改或重启生产 `fin-ops.service`；禁止修改生产运行配置；禁止切换生产 backend；禁止 shadow-read/dual-write/生产 cutover。
8. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码或 prompt。所有 URI 输出必须脱敏。
9. 不得把业务 SQL 散落到 app route/service 业务逻辑里。service 层继续通过 state store/repository 边界访问数据。
10. 默认 local/Mongo 模式必须保持现有行为。未配置 PostgreSQL 时，不得读取生产 `DATABASE_URL`，不得初始化 PostgreSQL connection，不得影响 `python -m pytest -q` 和 `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`。
11. PostgreSQL 模式下所有 SQL 必须参数化；禁止用用户输入拼 SQL。只允许对受控 schema/table 名使用白名单拼接。
12. 文件读取必须保持已有兼容：
    - app-owned local path
    - 旧 store：`gridfs://<file_id>/<name>`
    - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`
13. 不修改前端 DTO、不改 API 返回结构。若 PostgreSQL mode 需要 DTO 变化，先记录 `BLOCKED`，不要自行修改前端契约。
14. 不新增 schema migration，除非 repository extraction 过程中发现现有 schema 无法表达已存在 runtime 语义；如需新增 `0008`，必须先写 blocker 说明和 migration tests。
15. 不做性能优化型大重写。阶段 09 是边界收口和事务安全，不是重新设计 domain service。

阶段 08 已完成事实：

- 阶段 08 Gate：`PARTIAL`。
- 已闭合：
  - tax certified import 正式表优先读写和 dict -> dataclass hydration。
  - ETC 正式表优先读写和 `EtcInvoice/EtcBatch/EtcImportBatch/EtcBusinessBatch` hydration。
  - ETC reconciliation task/file 正式表读写。
  - historical ETC bundle/parsed seed/state 正式表读写。
  - workbench pair relation、no OA、bank category、turnover event/history 写入。
  - bank category event 外键阻止主表替换的问题已修复。
  - 默认 local/Mongo 全量测试通过。
  - 本机 UTF8 disposable PostgreSQL integration 通过。
  - 生产 PostgreSQL 只读 smoke 通过。
- 阶段 08 仍未闭合：
  1. repository package 拆分未完成：
     - `postgres_repositories/workbench.py`
     - `postgres_repositories/read_models.py`
     - `postgres_repositories/ops_tax_etc.py`
  2. 部分多表写路径未统一通过 transaction boundary。
  3. `read_model.search_index_rows` 未作为 runtime repository；需明确实时派生还是索引表优先。

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
- `docs/database-migration/05-postgresql-repository-tests.md`
- `docs/database-migration/06-postgresql-integration-repository-closure.md`
- `docs/database-migration/07-postgresql-domain-repository-completion.md`
- `docs/database-migration/08-postgresql-domain-repository-final-closure.md`
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
4. 如果可用，启动 UTF8 临时 cluster，创建 `fin_ops_stage09_test`，运行真实 integration；测试结束必须 stop cluster 并删除 temp dir。
5. 如果不可用，检查 `FIN_OPS_TEST_DATABASE_URL`；无 test DB 时 integration tests 必须 skip，并在文档中记录“未完成真实 DB 验证”。
6. 使用子代理并行完成以下任务：
   - Worker A：抽取 `workbench.py`，负责 workbench/no OA/category/turnover/event-history。
   - Worker B：抽取 `read_models.py`，负责 workbench snapshots/candidate/cost/tax read models/search decision support。
   - Worker C：抽取 `ops_tax_etc.py`，负责 settings/jobs/health/tax certified/ETC/reconciliation/historical ETC。
   - Worker D：事务边界和 rollback tests，负责跨 repository transaction helper 和 failure injection tests。
   - Explorer E：search runtime 决策、API smoke matrix、文档 Gate 核验。

推荐文件结构：

- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/__init__.py`
- Keep/Modify: `backend/src/fin_ops_platform/services/postgres_repositories/core.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/common.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Create: `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Modify only if necessary: `backend/src/fin_ops_platform/services/postgres_connection.py`
- Create/Modify: `tests/test_postgres_repositories_workbench.py`
- Create/Modify: `tests/test_postgres_repositories_read_models.py`
- Create/Modify: `tests/test_postgres_repositories_ops_tax_etc.py`
- Modify: `tests/test_postgres_state_store.py`
- Modify: `tests/test_postgres_state_store_integration.py`
- Modify: `tests/test_app_postgres_mode_integration.py`
- Create: `docs/database-migration/09-postgresql-repository-extraction-transaction-boundary.md`

设计要求：

1. `PostgresStateStore.__init__` 初始化 repository 实例，例如：
   - `_core_repository`
   - `_workbench_repository`
   - `_read_model_repository`
   - `_ops_tax_etc_repository`
2. Repository method 命名应贴近现有 state store public method，避免引入泛型过度抽象。
3. 共享 helpers 放在 `common.py`，例如：
   - `_jsonb`
   - `serialize_value`
   - `row_payload`
   - `text`
   - `text_list`
   - `month_start`
   - `decimal_text`
   - `int_value`
   - `max_numeric_suffix`
   - `event_uuid`
4. `common.py` 不得读取 env，不得持有全局 connection，不得 import app server。
5. 文件存储和 GridFS 兼容读取继续留在 `PostgresStateStore`，repository 只负责 SQL persistence。
6. `PostgresStateStore` 可保留 `_load_snapshot` / `_save_snapshot` / `_load_snapshot_or_empty` 作为 fallback 机制，但正式表优先读取的 SQL 应由 repository 承担。
7. 不改变 existing service hydration 修复；如果移动 helper，必须保持 tests 通过。

任务 9.0：安全基线和执行记录

- [ ] 读完必读文档和代码。
- [ ] 记录 branch 和 dirty worktree。不要 revert 非 09 改动。
- [ ] 运行启动步骤中的基线测试。
- [ ] 创建 `docs/database-migration/09-postgresql-repository-extraction-transaction-boundary.md`。
- [ ] 文档记录阶段边界：09 不做生产 cutover。
- [ ] 文档列出 08 `PARTIAL` 剩余项和本阶段目标。
- [ ] 确认没有任何命令触碰 `form_data_db.form_data`。

Acceptance:

- 文档存在。
- 基线结果已记录。
- 如果基线失败，先判断是否与 09 范围相关；相关则修复，不相关则记录风险。

任务 9.1：抽取共享 repository helpers

- [ ] 创建 `postgres_repositories/common.py`。
- [ ] 从 `PostgresStateStore` 和 `PostgresCoreRepository` 中识别可共享 helper，但只移动纯函数/无状态 helper。
- [ ] 保持 `_jsonb` 行为一致。
- [ ] 保持 dataclass、datetime、Decimal、Enum、Path、bytes 序列化行为一致。
- [ ] 保持 `row_payload()` 对 `{"normalized_payload": ...}` 的兼容行为。
- [ ] 更新 `core.py` 使用共享 helper，避免复制两套实现。
- [ ] 添加 `tests/test_postgres_repositories_common.py` 或在已有 repository tests 中覆盖 helper 行为。

Acceptance:

- helper tests 通过。
- `PostgresCoreRepository` tests 仍通过。
- 没有引入 env 读取或全局 connection。

任务 9.2：抽取 WorkbenchRepository

文件所有权：

- Create: `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Create/Modify: `tests/test_postgres_repositories_workbench.py`
- Modify: `tests/test_postgres_state_store_integration.py`

需要迁出的现有行为：

- `load_workbench_pair_relations`
- `save_workbench_pair_relations`
- `load_no_oa_bank_batches`
- `save_no_oa_bank_batches`
- `load_bank_transaction_categories`
- `save_bank_transaction_categories`
- `load_turnover_relations`
- `save_turnover_relations`
- `load_turnover_relation_audit_log`
- `save_turnover_relation_audit_log`
- `load_turnover_ledger_extras`
- `save_turnover_ledger_extras`
- `save_workbench_overrides`
- `save_workbench_exception_cases`
- event/history helpers：
  - pair relation history
  - no OA bank batch events
  - bank transaction category events
  - turnover relation events
  - workbench exception case events

步骤：

- [ ] 写 characterization tests：直接调用 `PostgresWorkbenchRepository`，用 fake connection 或 real disposable DB，断言 SQL 参数化、event idempotency、changed scope 不误删。
- [ ] 将 workbench/no OA/category/turnover SQL 移入 repository。
- [ ] `PostgresStateStore` public method 改为薄委托，并继续负责 `_save_snapshot` fallback。
- [ ] 保持 bank category 主表替换前先清理同 transaction scope events 的修复。
- [ ] 保持 `load_turnover_relations()` 返回 `{"relations": list, "audit_log": list}`，且每条 relation 补齐 `relation_id`。
- [ ] 保持 `changed_case_ids`、`changed_row_ids` 等局部写入语义。

Acceptance:

- `tests/test_postgres_repositories_workbench.py` 通过。
- `tests/test_postgres_state_store_integration.py` 中 event/history counts 和 turnover shape 仍通过。
- `PostgresStateStore` 内不再保留上述 domain SQL。

任务 9.3：抽取 ReadModelRepository，并完成 search runtime 决策

文件所有权：

- Create: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Create/Modify: `tests/test_postgres_repositories_read_models.py`
- Modify: `tests/test_app_postgres_mode_integration.py`
- Modify: `docs/database-migration/09-postgresql-repository-extraction-transaction-boundary.md`

需要迁出的现有行为：

- `load_workbench_read_models`
- `save_workbench_read_models`
- `load_workbench_candidate_matches`
- `save_workbench_candidate_matches`
- `save_workbench_matching_dirty_scopes` 如果仍是 snapshot-only，可留在 state store，但必须在文档说明原因。
- `load_cost_statistics_read_models`
- `save_cost_statistics_read_models`
- `load_tax_offset_read_models`
- `save_tax_offset_read_models`
- `_save_generic_read_model_snapshots`

search 决策：

- [ ] 阅读 `SearchService` 和 `/api/search` 路由。
- [ ] 判断是否切到 `read_model.search_index_rows`。
- [ ] 推荐默认：保持实时派生 runtime，不在 09 切换 search source，原因是 09 是边界收口，search index runtime 化需要刷新时机和 stale policy 的业务确认。
- [ ] 如果保持实时派生：写 no-OA PostgreSQL API smoke，证明 `/api/search` 在 PostgreSQL mode 下可用，并在 09 文档写明 `read_model.search_index_rows` 的当前角色。
- [ ] 如果切换 search source：必须实现 search repository、刷新和 stale 删除，并补完整 API smoke；如果无法完整实现，回退到实时派生并记录决策。

Acceptance:

- `tests/test_postgres_repositories_read_models.py` 覆盖 changed_scope_keys、changed_scope_months、cost/tax read models。
- API smoke 覆盖 `/api/search` 的 valid/invalid no-OA PostgreSQL mode。
- `PostgresStateStore` 内不再保留 read model SQL。

任务 9.4：抽取 OpsTaxEtcRepository

文件所有权：

- Create: `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Create/Modify: `tests/test_postgres_repositories_ops_tax_etc.py`
- Modify: `tests/test_postgres_state_store_integration.py`

需要迁出的现有行为：

- settings：
  - `load_app_settings`
  - `save_app_settings`
  - app state snapshot get/set 可保留在 state store，也可由 repository 提供 `load_settings/save_settings`；必须保持 `STATE_KEY_PREFIX` fallback。
- OA-adjacent app state，但不得触碰 OA Mongo：
  - `load_oa_attachment_invoice_cache_entry`
  - `save_oa_attachment_invoice_cache_entry`
  - `clear_oa_attachment_invoice_cache`
  - `load_oa_sync_state`
  - `save_oa_sync_state`
  - `load_manual_oa_imports`
  - `save_manual_oa_imports`
  - `add_manual_oa_imports`
  - `remove_manual_oa_import`
- tax/ETC/historical:
  - `load_tax_certified_imports`
  - `save_tax_certified_imports`
  - `load_etc_state`
  - `save_etc_state`
  - `load_etc_reconciliation_state`
  - `save_etc_reconciliation_state`
  - `save_historical_etc_repair_bundle` SQL portion only; file write remains in state store
  - `load_historical_etc_repair_bundle_metadata`
  - `save_historical_etc_repair_parsed_seed`
  - `load_historical_etc_repair_parsed_seeds`
  - `load_historical_etc_repair_parsed_seed`
  - `load_historical_etc_repair_states`
  - `save_historical_etc_repair_states`
- jobs/health:
  - `load_background_jobs`
  - `save_background_jobs`
  - `load_app_health_alerts`
  - `save_app_health_alerts`

步骤：

- [ ] 写 repository tests 覆盖 tax/ETC/reconciliation/historical/jobs/health/settings formal table round-trip。
- [ ] 将 SQL 移入 `OpsTaxEtcRepository`。
- [ ] 对需要文件内容的 methods 设计清晰边界：
  - state store 负责 `_store_local_file` 和 `_save_file_object`；
  - repository 负责把 file object id 和 raw payload 写入正式表。
- [ ] 保持 snapshot fallback 不变。
- [ ] 保持阶段 08 hydration 修复不变。

Acceptance:

- `tests/test_postgres_repositories_ops_tax_etc.py` 通过。
- `tests/test_postgres_state_store_integration.py` 中 tax/ETC/reconciliation/historical round-trip 仍通过。
- `PostgresStateStore` 内不再保留上述 domain SQL，除文件读写和 fallback 编排外。

任务 9.5：统一 transaction boundary

文件所有权：

- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/common.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/*.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Modify: `tests/test_postgres_state_store_integration.py`
- Create/Modify: repository rollback tests

要求：

- [ ] 定义一致的 transaction 入口。可选方案：
  - repository public save method 内部检测 `connection.transaction()` 并在有 transaction factory 时包裹；
  - 或由 `PostgresStateStore` 在 save 编排时打开 transaction，把 tx 传给 repository。
- [ ] 避免嵌套 transaction 导致 psycopg 行为不清晰；如需要 helper，命名为 `run_in_transaction(connection, callback)`。
- [ ] 多表写入必须 transaction：
  - imports/file_imports 已在 core 中有 transaction pattern，保持或迁入通用 helper。
  - tax certified sessions/batches/records。
  - ETC invoices/import/submission/business batches。
  - ETC reconciliation tasks/files。
  - historical ETC bundle/file object/formal row、parsed seed、states。
  - workbench pair relation + history。
  - no OA batch + events。
  - bank category + events。
  - turnover relation + events。
  - app health/jobs 如单表可不强制，但 save(payload) 跨多个 domain 写入需要明确行为。
- [ ] 写 failure injection tests：
  - 用 fake connection 在第 N 条 execute 抛异常，断言前面 SQL 没有被永久提交，或真实 PostgreSQL transaction 中模拟失败断言 rollback。
  - 至少覆盖一个 workbench multi-table write、一个 tax/ETC multi-table write、一个 historical/file-object formal row write。
- [ ] 明确 `PostgresStateStore.save(payload)` 的事务策略：
  - 若整体 state save 包含多个 domain，推荐整个 save 使用一个 transaction，避免 partial domain writes；
  - 如果无法整体 transaction，因为文件系统写入无法 rollback，必须文档记录并把 DB 部分保持 transaction。

Acceptance:

- rollback tests 在真实 PostgreSQL 或可证明事务语义的 fake connection 上通过。
- 失败时不留下半写 DB 行。
- 文件系统写入不可 rollback 的 residual risk 已写入 09 文档。

任务 9.6：State store 薄化和 public contract 回归

- [ ] 检查 `PostgresStateStore` 剩余代码。
- [ ] `PostgresStateStore` 应主要保留：
  - constructor/repository wiring；
  - health/storage metadata；
  - public state-store API 委托；
  - snapshot fallback load/save；
  - file storage/read/delete/GridFS compatibility；
  - minimal glue code。
- [ ] 不要求把文件存储移入 repository。
- [ ] 不要求把 `ApplicationStateStore` normalization 静态方法复制到 repository；如需要，保留 state store glue。
- [ ] 运行 state store contract。

Acceptance:

- `tests/test_state_store_contract.py` 通过。
- `tests/test_postgres_state_store.py` 通过。
- `PostgresStateStore` 没有大段 domain SQL 留存；如仍留存，文档逐项解释原因。

任务 9.7：API smoke 和生产只读 smoke

No-OA PostgreSQL mode API smoke 必须覆盖：

- `/health`
- `/api/session/me`
- `/api/app-health`
- `/imports/preview`
- `/imports/confirm`
- `/imports/files/preview`
- `/imports/files/confirm`
- `/api/workbench/settings`
- `/api/tax-offset/certified-import/preview`
- `/api/tax-offset/certified-import/confirm`
- `/api/tax-offset/certified-imports?month=...`
- `/api/etc/import/preview`
- `/api/etc/import/confirm`
- `/api/etc/invoices`
- `/api/search` valid/invalid

必须避免：

- `/integrations/oa*`
- workbench settings OA manual-search/manual-imports
- data-reset
- OA bank exception
- ETC OA draft/submit/status endpoints
- destructive/revert endpoints

生产只读 smoke：

- [ ] 只查 `fin-ops.service` active 状态。
- [ ] 只查 `public.schema_migrations`。
- [ ] 只查关键表 count。
- [ ] 不写生产库，不重启服务，不改配置。

Acceptance:

- no-OA API smoke 通过。
- 生产只读 smoke 结果写入文档，所有 URI/密码脱敏。

任务 9.8：最终验证矩阵

必须运行：

- [ ] `python -m py_compile backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/services/postgres_repositories/*.py backend/src/fin_ops_platform/services/tax_certified_import_service.py backend/src/fin_ops_platform/services/etc_service.py`
- [ ] `python -m pytest tests/test_postgres_repositories_core.py tests/test_postgres_repositories_workbench.py tests/test_postgres_repositories_read_models.py tests/test_postgres_repositories_ops_tax_etc.py -q`
- [ ] `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_workbench.py tests/test_postgres_repositories_read_models.py tests/test_postgres_repositories_ops_tax_etc.py -q`
- [ ] `python -m pytest -q`
- [ ] `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
- [ ] 本机 UTF8 disposable PostgreSQL `fin_ops_stage09_test` 上运行真实 integration。

Acceptance:

- 默认全量测试通过。
- PostgreSQL integration 在 test DB 上通过。
- app check 显示默认 `storage.backend=local_pickle`。

任务 9.9：文档和 Gate

- [ ] 创建 `docs/database-migration/09-postgresql-repository-extraction-transaction-boundary.md`。
- [ ] 更新 `docs/database-migration/README.md` 阅读顺序，加入 09。
- [ ] 文档记录：
  - 09 边界；
  - repository 拆分结果；
  - `PostgresStateStore` 剩余职责；
  - transaction boundary 策略；
  - rollback tests；
  - search runtime 决策；
  - no-OA API smoke；
  - production read-only smoke；
  - 是否触碰 OA/app Mongo；
  - Gate：`PASS` / `PARTIAL` / `BLOCKED`。
- [ ] 如果 `PASS`，写明后续可以生成 shadow/dual-write/cutover prompt。
- [ ] 如果 `PARTIAL` 或 `BLOCKED`，写明用户需要提供什么或下一阶段必须做什么。

Acceptance:

- 文档存在且与验证结果一致。
- 不含密码、token、完整 URI。
- Gate 判定不夸大。

最终输出要求：

1. 用中文总结实际完成项。
2. 明确 Gate。
3. 列出测试命令和结果。
4. 列出新增/修改文件。
5. 明确是否触碰 OA Mongo/app Mongo/生产 PostgreSQL 写入。
6. 如果无法 `PASS`，说明具体原因和用户下一步需要做什么。
```
