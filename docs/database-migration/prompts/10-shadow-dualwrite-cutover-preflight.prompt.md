# 10 阶段 Codex 执行 Prompt：Shadow-read / Dual-write / Cutover preflight

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 10：基于阶段 09 `PASS` 结果，实现并验证生产切换前的 shadow-read、dual-write、cutover preflight 基础设施、守卫、测试和运行文档。

阶段 10 是 preflight 阶段，不是生产切换阶段。阶段 10 完成后必须能清楚回答：

1. 生产服务是否可以在“不改变事实源”的前提下进行 shadow-read diff。
2. app 自身写路径是否具备可控 dual-write/mirror-write wrapper、失败策略、审计摘要和重试/补偿入口。
3. cutover 前需要检查的 backups、schema、counts、health、flags、readiness、rollback commands 是否已固化为脚本和 runbook。
4. 所有 preflight 代码是否默认关闭，且不会在默认 local/Mongo 模式或 PostgreSQL 单库模式下改变行为。
5. 是否仍有不能进入真正 shadow/dual-write 生产演练的 blocker；如果有，具体 blocker 是业务决策、环境权限、schema、测试覆盖还是运维流程。

如果阶段 10 无法完全完成，最终输出和文档必须用 `BLOCKED` 或 `PARTIAL` 标明原因，不得把“只写了文档”“测试 skip”“没有实际 guard”包装成完成。

阶段 10 完成标准：

1. 默认 local/Mongo 模式全量测试通过。
2. `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check` 仍显示默认 `storage.backend=local_pickle`。
3. 无 PostgreSQL test DB 时 integration tests 安全 skip。
4. 有 disposable PostgreSQL test DB 或本机临时 UTF8 PostgreSQL cluster 时，migrations、state store contract、PostgreSQL integration、app smoke 全部通过。
5. 生产 PostgreSQL 只允许只读 smoke；不得写生产库、不得启用 dual-write、不得切换生产 backend、不得重启生产服务。
6. 新增 shadow/dual/cutover preflight 代码默认不启用；未设置新增 flags 时行为与阶段 09 完全一致。
7. `state_store_factory.py` 支持 preflight 所需配置解析，但必须 fail-fast，配置不完整时不得静默 fallback 到错误事实源。
8. Shadow read wrapper 能比较 primary store 与 shadow store 的 domain snapshot，生成脱敏 diff summary，不阻断主请求。
9. Dual write wrapper 能按配置执行 primary write + mirror write，并明确支持：
   - non-strict mirror failure 不阻断 primary success，但记录 mismatch/retry signal；
   - strict mirror failure 阻断并抛出明确错误；
   - primary failure 时不得执行 mirror write；
   - 所有 secret/URI 必须脱敏。
10. Cutover preflight 脚本必须只读生产数据，输出 schema/counts/health/flag readiness/rollback readiness；不得包含密码、token、完整 URI。
11. 新增或更新 tests 覆盖 shadow diff、dual write failure semantics、factory guard、redaction、preflight script dry-run、PostgreSQL app smoke。
12. 文档更新为阶段 10 执行记录和 Gate 判定。

你必须使用子代理并行完成可并行任务：

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- 主线程负责最终集成、冲突处理、测试、文档和 Gate 判定。
- 子代理可以只读梳理，也可以作为 worker 修改代码；如果让 worker 写代码，必须给出明确文件所有权，避免多个 worker 修改同一文件。
- Worker 必须知道“不是独自在 codebase 中工作”，不得 revert 其他 worker 或用户改动。
- 如果当前 subagent 数量达到上限，先关闭不再需要的旧 agent。

硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. OA Mongo 只能继续作为现有 `MongoOAAdapter` 的只读源；阶段 10 不实现 OA 数据写回。
3. app Mongo `fin_ops_platform_app` 不得写入。阶段 10 可实现 dual wrapper 代码和 fake-store tests，但不得在生产或真实 app Mongo 上启用写入、清理、建索引或 schema 修改。
4. 生产 PostgreSQL `fin_ops` 只能做只读 smoke/count/schema/readiness/preflight 检查；不得在生产库做 destructive truncate、seed、contract write、API write smoke、shadow write、dual write 或 cutover。
5. 阶段 10 不得修改或重启生产 `fin-ops.service`；不得修改生产运行配置；不得把生产 backend 切到 PostgreSQL/dual/shadow。
6. 所有 destructive integration test 必须使用 disposable PostgreSQL test DB。DB 名必须包含 `test`，否则必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；如果无法证明是 test DB，立即停止并记录 `BLOCKED`。
7. 优先使用本机临时 PostgreSQL cluster 跑真实 integration；必须使用 UTF8 cluster，例如 `initdb --encoding=UTF8 --locale=C`。测试结束必须 stop cluster 并删除 temp dir。
8. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码、prompt 或测试快照。所有 URI 输出必须脱敏。
9. 不得把业务 SQL 散落到 app route/service 业务逻辑里。service 层继续通过 state store/repository 边界访问数据。
10. 默认 local/Mongo 模式必须保持现有行为。未配置 PostgreSQL 时，不得读取生产 `DATABASE_URL`，不得初始化 PostgreSQL connection，不得影响 `python -m pytest -q` 和 app `--check`。
11. PostgreSQL 模式下所有 SQL 必须参数化；禁止用用户输入拼 SQL。只允许对受控 schema/table 名使用白名单拼接。
12. 文件读取必须保持已有兼容：
    - app-owned local path
    - 旧 store：`gridfs://<file_id>/<name>`
    - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`
13. 不修改前端 DTO、不改 API 返回结构。若 preflight 需要新增字段，只能放在 readiness/health 的后向兼容扩展字段中；如会影响现有前端契约，先记录 `BLOCKED`。
14. 不新增 schema migration，除非 preflight 过程发现必须有持久化审计/outbox 表；如需新增 `0008`，必须先写 blocker 说明、migration tests、rollback plan，并确认不是用现有 `job.background_jobs` / `audit.app_health_alerts` 可表达。
15. 不做真正 cutover。阶段 10 只能生成并验证切换前能力，不允许执行“生产事实源切换”。

阶段 09 已完成事实：

- 阶段 09 Gate：`PASS`。
- `PostgresStateStore` 已收口为 public API、snapshot fallback、文件存储桥接和 repository 编排。
- 正式表 domain SQL 已拆到：
  - `postgres_repositories/common.py`
  - `postgres_repositories/workbench.py`
  - `postgres_repositories/read_models.py`
  - `postgres_repositories/ops_tax_etc.py`
- 多表写入已通过 `run_in_transaction(connection, callback)` 收口并有 transaction boundary tests。
- app 自身关键 runtime domains 的 PostgreSQL 正式表读写已通过真实 PostgreSQL integration。
- `/api/search` runtime 继续由 `SearchService` 实时派生；`read_model.search_index_rows` 作为迁移/对账/后续加速表保留。
- 默认全量测试通过：`1147 passed, 16 skipped`。
- 本机 UTF8 disposable PostgreSQL integration 通过：`21 passed`。
- 生产只读 smoke 通过：
  - `fin-ops.service=active`
  - `schema_migrations=0001,0002,0003,0004,0005,0006,0007`
  - 核心 counts 顺序为 `import_batches, import_batch_rows, import_files, invoices, bank_transactions, search_index_rows`。

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
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md`
- `docs/database-migration/08-postgresql-domain-repository-final-closure.md`
- `docs/database-migration/09-postgresql-repository-extraction-transaction-boundary.md`
- `docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`

必须先读的代码：

- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/state_store_protocol.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_connection.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/__init__.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/common.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/core.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- `backend/src/fin_ops_platform/app/main.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/app_health_service.py`
- `backend/src/fin_ops_platform/services/background_job_service.py`
- `backend/src/fin_ops_platform/services/search_service.py`
- `tests/test_state_store_contract.py`
- `tests/test_postgres_state_store.py`
- `tests/test_postgres_state_store_integration.py`
- `tests/test_app_postgres_mode.py`
- `tests/test_app_postgres_mode_integration.py`
- `tests/test_postgres_repositories_boundaries.py`
- `tests/postgres_test_utils.py`

启动步骤：

1. 记录当前 git branch 和 `git status --short`。不要 revert 非本阶段改动。
2. 运行基线：
   - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q`
   - `python -m pytest -q`
   - `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
3. 检查本机 PostgreSQL 工具：
   - `command -v initdb && command -v pg_ctl && command -v createdb && command -v psql`
4. 如果可用，启动 UTF8 临时 cluster，创建 `fin_ops_stage10_test`，运行真实 integration；测试结束必须 stop cluster 并删除 temp dir。
5. 如果不可用，检查 `FIN_OPS_TEST_DATABASE_URL`；无 test DB 时 integration tests 必须 skip，并在文档中记录“未完成真实 DB 验证”。
6. 使用子代理并行完成以下任务：
   - Explorer A：梳理 state-store public methods、domain snapshot shape、可比较 domain、忽略字段和敏感字段。
   - Worker B：实现 `state_store_diff.py` 和 `shadow_state_store.py`，负责 shadow diff 和 tests。
   - Worker C：实现 `dual_state_store.py`，负责 dual write failure semantics 和 tests。
   - Worker D：实现 factory/config guard 和 app readiness/preflight summary，负责 tests。
   - Worker E：实现 cutover preflight 只读脚本和 runbook 文档，负责 redaction 和 script tests。
   - Explorer F：核验生产只读 smoke、PostgreSQL test matrix、09 回归项不回退。

推荐文件结构：

- Create: `backend/src/fin_ops_platform/services/state_store_diff.py`
- Create: `backend/src/fin_ops_platform/services/shadow_state_store.py`
- Create: `backend/src/fin_ops_platform/services/dual_state_store.py`
- Create: `backend/src/fin_ops_platform/services/cutover_preflight.py`
- Modify: `backend/src/fin_ops_platform/services/state_store_factory.py`
- Modify: `backend/src/fin_ops_platform/services/state_store_protocol.py` only if protocol additions are unavoidable; prefer wrapper delegation over protocol churn.
- Modify: `backend/src/fin_ops_platform/app/server.py` only for readiness/health summary extensions; do not change existing API DTO.
- Create: `backend/src/fin_ops_platform/tools/verify_cutover_preflight.py`
- Create: `tests/test_state_store_diff.py`
- Create: `tests/test_shadow_state_store.py`
- Create: `tests/test_dual_state_store.py`
- Create/Modify: `tests/test_app_postgres_mode.py`
- Create/Modify: `tests/test_app_postgres_mode_integration.py`
- Create: `tests/test_cutover_preflight.py`
- Create: `docs/database-migration/10-shadow-dualwrite-cutover-preflight.md`
- Modify: `docs/database-migration/README.md`
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md` only to link stage 10 preflight outcome; do not rewrite it as execution record unless stage 10 needs it.

建议配置设计：

- `FIN_OPS_APP_STORAGE_BACKEND`
  - existing: `local_pickle`, `mongo`, `auto`, `postgres`
  - new preflight-only values may include `shadow` and `dual`
- `FIN_OPS_PRIMARY_STORAGE_BACKEND`
  - explicit primary backend for `shadow`/`dual`; allowed values initially should be `local_pickle` or `postgres` in tests/preflight.
- `FIN_OPS_SHADOW_STORAGE_BACKEND`
  - explicit shadow backend; usually `postgres` during Mongo/local primary shadow-read.
- `FIN_OPS_MIRROR_STORAGE_BACKEND`
  - explicit mirror backend; usually `postgres` during controlled mirror write.
- `FIN_OPS_SHADOW_COMPARE_ENABLED`
  - default `0`; wrapper must be inactive unless explicitly enabled.
- `FIN_OPS_SHADOW_COMPARE_SAMPLE_RATE`
  - default `1.0` for deterministic tests; must validate `0.0 <= value <= 1.0`.
- `FIN_OPS_DUAL_WRITE_STRICT`
  - default `0`; strict mode only in tests/preflight, not production by default.
- `FIN_OPS_CUTOVER_PREFLIGHT_ONLY`
  - default `1` for phase 10 scripts; script refuses write/cutover actions.
- `FIN_OPS_POSTGRES_CUTOVER_PHASE`
  - allowed phase labels only; do not use it to execute cutover in phase 10.
- `FIN_OPS_CUTOVER_RUN_ID`
  - text id for logs/docs; optional in tests.

所有 config parsing 必须：

- fail fast on unknown/unsupported values;
- redact any URI in errors/logs;
- not instantiate PostgreSQL connection unless the selected mode requires it;
- preserve existing default behavior when new env vars are absent.

任务 10.0：安全基线和阶段文档

- [ ] 读完必读文档和代码。
- [ ] 记录 branch 和 dirty worktree。不要 revert 非 10 改动。
- [ ] 运行启动步骤中的基线测试。
- [ ] 创建 `docs/database-migration/10-shadow-dualwrite-cutover-preflight.md`。
- [ ] 文档记录阶段边界：10 不做生产 cutover、不启用生产 dual-write、不写生产 DB、不写 app Mongo、不触碰 OA Mongo。
- [ ] 文档列出阶段 09 `PASS` 事实和本阶段目标。
- [ ] 确认没有任何命令触碰 `form_data_db.form_data`。

Acceptance:

- 文档存在。
- 基线结果已记录。
- 如果基线失败，先判断是否与 10 范围相关；相关则修复，不相关则记录风险。

任务 10.1：state snapshot diff 和脱敏

Files:

- Create: `backend/src/fin_ops_platform/services/state_store_diff.py`
- Create: `tests/test_state_store_diff.py`

Requirements:

- [ ] 实现 `StateStoreDiffResult` 数据结构，至少包含：
  - `matched: bool`
  - `domain: str`
  - `primary_count: int | None`
  - `shadow_count: int | None`
  - `mismatch_count: int`
  - `mismatches: list[dict[str, object]]`
  - `redacted: bool`
- [ ] 实现 `diff_state_snapshots(primary, shadow, *, domain=None, ignored_paths=None, max_mismatches=20)`。
- [ ] 支持 dict/list/scalar diff，mismatch path 使用稳定字符串，例如 `imports.batches.batch_1.status`。
- [ ] 默认忽略字段：
  - `updated_at`
  - `created_at` only when source object has stable business id and values are otherwise equal
  - `generated_at`
  - `raw_payload.migration_metadata`
  - internal PostgreSQL UUID fields where legacy ids match
- [ ] 实现 `redact_diff_payload(value)`：
  - 移除 password/token/secret/uri/database_url/mongo_uri/authorization/cookie 等 key；
  - URI 输出使用已有 redaction 或 `<redacted-uri>`；
  - 不输出完整 connection string。
- [ ] tests 覆盖 equal、missing key、value mismatch、ignored fields、max mismatch、redaction。

Acceptance:

- `python -m pytest tests/test_state_store_diff.py -q` 通过。
- diff result 可以被 JSON 序列化。
- 不泄漏 secret。

任务 10.2：ShadowStateStore

Files:

- Create: `backend/src/fin_ops_platform/services/shadow_state_store.py`
- Create: `tests/test_shadow_state_store.py`

Requirements:

- [ ] 创建 `ShadowStateStore` wrapper，接收：
  - `primary_store`
  - `shadow_store`
  - `compare_enabled`
  - `sample_rate`
  - `logger` 或 callback
  - `diff_options`
- [ ] 所有 read methods 必须返回 primary result。
- [ ] compare enabled 且命中 sample 时，同步或 best-effort 调用 shadow store 的对应 read method 并 diff。
- [ ] Shadow store exception 不得阻断 primary read；必须记录 `shadow_error` summary。
- [ ] 支持至少以下 read methods：
  - `load`
  - `load_app_settings`
  - `load_tax_certified_imports`
  - `load_etc_state`
  - `load_etc_reconciliation_state`
  - `load_workbench_pair_relations`
  - `load_no_oa_bank_batches`
  - `load_bank_transaction_categories`
  - `load_turnover_relations`
  - `load_workbench_read_models`
  - `load_workbench_candidate_matches`
  - `load_cost_statistics_read_models`
  - `load_tax_offset_read_models`
- [ ] Write methods must delegate only to primary store in shadow mode; phase 10 shadow mode must not write shadow store.
- [ ] Expose `shadow_summary()` with counts:
  - compared
  - matched
  - mismatched
  - shadow_errors
  - last_mismatch
  - last_error
- [ ] Tests use fake stores only; no real app Mongo writes.

Acceptance:

- Shadow mode never changes returned primary payload.
- Shadow mismatch is observable and redacted.
- Shadow exception does not break primary read.

任务 10.3：DualStateStore / controlled mirror write

Files:

- Create: `backend/src/fin_ops_platform/services/dual_state_store.py`
- Create: `tests/test_dual_state_store.py`

Requirements:

- [ ] 创建 `DualStateStore` wrapper，接收：
  - `primary_store`
  - `mirror_store`
  - `strict: bool`
  - `logger` 或 callback
  - `operation_id_factory`
- [ ] Read methods 默认只读 primary store；阶段 10 不实现 “mirror primary read switch”。
- [ ] Write methods 执行顺序：
  1. primary write
  2. primary 成功后 mirror write
  3. 记录 operation summary
- [ ] primary write 失败时不得调用 mirror write。
- [ ] mirror write 失败：
  - non-strict：返回 primary success，记录 `mirror_failed`；
  - strict：抛出明确异常，记录 `mirror_failed_strict`。
- [ ] 支持至少以下 write methods：
  - `save`
  - `save_app_settings`
  - `save_tax_certified_imports`
  - `save_etc_state`
  - `save_etc_reconciliation_state`
  - `save_workbench_pair_relations`
  - `save_no_oa_bank_batches`
  - `save_bank_transaction_categories`
  - `save_turnover_relations`
  - `save_workbench_read_models`
  - `save_workbench_candidate_matches`
  - `save_cost_statistics_read_models`
  - `save_tax_offset_read_models`
  - `save_background_jobs`
  - `save_app_health_alerts`
- [ ] File write methods are high risk. For stage 10:
  - default: primary-only for `store_import_file`, `store_etc_invoice_file`, `store_etc_reconciliation_file`, `save_historical_etc_repair_bundle`;
  - document that binary/file mirroring requires later dedicated file-object reconciliation or a shared file object strategy.
- [ ] Expose `dual_write_summary()` with counts:
  - primary_success
  - primary_failed
  - mirror_success
  - mirror_failed
  - strict_failures
  - last_failure
- [ ] Tests cover non-strict, strict, primary failure, method args/kwargs preservation, no secret leakage.

Acceptance:

- Mirror failure semantics are deterministic.
- No real production writes happen in tests.
- Default behavior without dual mode is unchanged.

任务 10.4：Factory/config guard

Files:

- Modify: `backend/src/fin_ops_platform/services/state_store_factory.py`
- Create/Modify: `tests/test_app_postgres_mode.py`
- Create: `tests/test_state_store_factory_preflight.py` if clearer.

Requirements:

- [ ] Keep existing behavior:
  - unset/`auto`/`local_pickle`/`mongo` returns `ApplicationStateStore`.
  - `postgres` returns `PostgresStateStore`.
- [ ] Add preflight mode parsing for `shadow` and `dual` only if explicitly configured.
- [ ] `shadow` mode requires explicit primary + shadow backend variables; no implicit production DATABASE_URL if primary/shadow does not need PostgreSQL.
- [ ] `dual` mode requires explicit primary + mirror backend variables and `FIN_OPS_CUTOVER_PREFLIGHT_ONLY=1` unless tests explicitly override.
- [ ] Reject unsupported combinations that would write app Mongo in phase 10. If code supports generic stores, factory must not build a real app Mongo writer.
- [ ] All errors must redact URLs/secrets.
- [ ] Add readiness/health summary fields only if app already exposes a safe storage summary hook; otherwise document as `PARTIAL` and do not alter API DTO.

Acceptance:

- Existing factory tests still pass.
- New preflight config tests pass.
- Bad config fails fast with actionable, redacted errors.

任务 10.5：Cutover preflight service and CLI

Files:

- Create: `backend/src/fin_ops_platform/services/cutover_preflight.py`
- Create: `backend/src/fin_ops_platform/tools/verify_cutover_preflight.py`
- Create: `tests/test_cutover_preflight.py`

Requirements:

- [ ] Implement a read-only preflight checker that can report:
  - current app storage config mode, redacted;
  - PostgreSQL connectivity and schema version;
  - PostgreSQL core counts;
  - migration schema table location (`public.schema_migrations`);
  - app readiness summary;
  - backup checklist placeholders;
  - rollback command checklist placeholders;
  - forbidden-action guard status.
- [ ] CLI must support:
  - `--json`
  - `--require-backup-confirmation`
  - `--no-production-writes` default true
  - `--database-url-env FIN_OPS_POSTGRES_DATABASE_URL`
- [ ] CLI must refuse to run any write action. It should not accept flags named `--cutover`, `--enable-dual-write`, `--restart-service`, or similar.
- [ ] Output must redact URI/password/token.
- [ ] Tests should use fake connection/checker; real production access is not required for unit tests.

Acceptance:

- `python -m fin_ops_platform.tools.verify_cutover_preflight --json` works with fake/test env or exits with clear redacted config error.
- Unit tests prove command output is JSON serializable and secret-safe.

任务 10.6：PostgreSQL integration and API smoke

Files:

- Modify: `tests/test_app_postgres_mode_integration.py`
- Modify/Create: integration tests only where necessary.

Requirements:

- [ ] Keep stage 09 PostgreSQL integration coverage passing.
- [ ] Add no-OA / workbench read model search smoke only if not already sufficient.
- [ ] Add shadow/dual wrapper integration with fake primary/mirror if real DB integration would be unsafe.
- [ ] If using disposable PostgreSQL:
  - DB name must include `test`;
  - cluster must be UTF8;
  - cleanup must stop and delete temp cluster.

Acceptance:

- Without `FIN_OPS_TEST_DATABASE_URL`, integration tests skip safely.
- With disposable PostgreSQL, integration passes.

任务 10.7：Production read-only smoke

Requirements:

- [ ] Only run read-only production checks:
  - service active status;
  - `public.schema_migrations` versions;
  - core counts;
  - no full URI/secrets in output.
- [ ] Do not restart service.
- [ ] Do not modify production env.
- [ ] Do not write production PostgreSQL.
- [ ] Do not read/write OA Mongo `form_data_db.form_data`.

Acceptance:

- Smoke output recorded in `docs/database-migration/10-shadow-dualwrite-cutover-preflight.md`.
- Any credential is omitted/redacted.

任务 10.8：Runbook and Gate

Files:

- Create/Modify: `docs/database-migration/10-shadow-dualwrite-cutover-preflight.md`
- Modify: `docs/database-migration/README.md`
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md` only to link stage 10 preflight status.

Requirements:

- [ ] Document:
  - what was implemented;
  - what remains disabled by default;
  - how to run shadow-read preflight in staging/test;
  - how to run dual-write wrapper in tests/staging only;
  - production preflight checklist;
  - rollback prerequisites;
  - exact verification commands and outputs;
  - risks and follow-up work.
- [ ] Gate must be one of:
  - `PASS`: all code, tests, docs, local + PostgreSQL integration, production read-only smoke done.
  - `PARTIAL`: code/tests mostly done but no real PostgreSQL validation or no production read-only smoke.
  - `BLOCKED`: missing business decision/permission/environment prevents safe preflight.
- [ ] If Gate is `PASS`, state clearly that next phase may generate stage 11 prompt for controlled shadow-read production exercise, not immediate cutover.

Acceptance:

- Documentation is detailed enough for another Codex run to execute stage 11.
- No secrets in docs.

最终验证矩阵：

Run all applicable commands before final response:

```bash
python -m py_compile \
  backend/src/fin_ops_platform/services/state_store_factory.py \
  backend/src/fin_ops_platform/services/state_store_diff.py \
  backend/src/fin_ops_platform/services/shadow_state_store.py \
  backend/src/fin_ops_platform/services/dual_state_store.py \
  backend/src/fin_ops_platform/services/cutover_preflight.py \
  backend/src/fin_ops_platform/tools/verify_cutover_preflight.py

python -m pytest \
  tests/test_state_store_diff.py \
  tests/test_shadow_state_store.py \
  tests/test_dual_state_store.py \
  tests/test_cutover_preflight.py \
  tests/test_app_postgres_mode.py \
  tests/test_postgres_state_store.py \
  tests/test_postgres_repositories_boundaries.py \
  -q

python -m pytest \
  tests/test_state_store_contract.py \
  tests/test_postgres_state_store.py \
  tests/test_app_postgres_mode.py \
  tests/test_postgres_test_utils.py \
  tests/test_postgres_state_store_integration.py \
  tests/test_app_postgres_mode_integration.py \
  tests/test_postgres_migrations.py \
  tests/test_postgres_repositories_core.py \
  tests/test_postgres_repositories_boundaries.py \
  -q

python -m pytest -q

PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
```

如果本机 PostgreSQL 工具可用，必须额外跑 UTF8 disposable PostgreSQL integration：

```bash
# Use a temp dir and unique free port. Stop cluster and remove temp dir after tests.
initdb --encoding=UTF8 --locale=C -D "$TMPDIR/data"
pg_ctl -D "$TMPDIR/data" -o "-p $PORT" -l "$TMPDIR/postgres.log" start
createdb -h 127.0.0.1 -p "$PORT" fin_ops_stage10_test
export FIN_OPS_TEST_DATABASE_URL="postgresql://127.0.0.1:$PORT/fin_ops_stage10_test"
export FIN_OPS_ALLOW_POSTGRES_TEST_DB=1
python -m pytest tests/test_postgres_migrations.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
pg_ctl -D "$TMPDIR/data" stop -m fast
rm -rf "$TMPDIR"
```

最终输出要求：

1. 列出 Gate：`PASS` / `PARTIAL` / `BLOCKED`。
2. 列出 changed files。
3. 列出验证命令和结果。
4. 明确说明：
   - 未触碰 OA Mongo `form_data_db.form_data`；
   - 未写 app Mongo；
   - 未写生产 PostgreSQL；
   - 未启用生产 shadow/dual/cutover；
   - 默认 local/Mongo 行为保持。
5. 如果有 blocker，说明原因以及用户需要做什么。
```
