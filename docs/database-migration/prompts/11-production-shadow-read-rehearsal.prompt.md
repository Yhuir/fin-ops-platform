# 11 阶段 Codex 执行 Prompt：Production shadow-read rehearsal

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 11：基于阶段 10 `PASS` 结果，规划并执行“生产 shadow-read 演练”。阶段 11 的目标是在不改变生产事实源、不启用 dual-write、不 cutover 的前提下，用生产只读数据和明确白名单 read domains 验证：当前 app 事实源与 PostgreSQL app 数据在关键读路径上的差异是否可观测、可脱敏记录、可人工判定，并形成是否可以进入后续 dual-write 演练的 Gate 结论。

阶段 11 是生产 shadow-read rehearsal，不是 dual-write，不是切换事实源，不是生产 cutover。阶段 11 完成后必须能清楚回答：

1. 当前生产 app 事实源是什么，是否能以只读方式构造 primary snapshot。
2. PostgreSQL `fin_ops` 中的 app 数据是否能作为 shadow source 参与只读比对。
3. 哪些 app read domains 已完成生产 shadow-read 比对，哪些不能比对，原因是什么。
4. mismatch 是否全部脱敏、可归类、可解释；是否存在阻断后续 dual-write 的 P0/P1 mismatch。
5. 阶段 11 是否真正执行了生产只读 shadow-read rehearsal；如果无法执行，具体 blocker 是代码未部署、环境权限、数据源不可只读、配置风险、schema 差异、测试覆盖还是人工授权缺失。

如果阶段 11 无法完全完成，最终输出和文档必须用 `BLOCKED` 或 `PARTIAL` 标明原因。不得把“只写了文档”“只跑了本地 fake test”“只做了 production count smoke”包装成生产 shadow-read rehearsal 完成。

阶段 11 完成标准：

1. 默认 local/Mongo 模式全量测试通过。
2. `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check` 仍显示默认 `storage.backend=local_pickle`。
3. 阶段 10 新增 shadow/diff/dual/preflight tests 仍通过。
4. 有 disposable PostgreSQL test DB 或本机临时 UTF8 PostgreSQL cluster 时，PostgreSQL migrations、state store integration、app smoke、shadow rehearsal tests 全部通过。
5. 生产 PostgreSQL 只允许只读查询；不得写生产库、不得 truncate、不得 seed、不得 contract write。
6. 生产 app 当前事实源只允许只读访问；不得写 app Mongo、不得写 app local state、不得清理/修复/建索引。
7. OA Mongo `form_data_db.form_data` 禁止触碰；不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
8. 阶段 11 不得启用 production dual-write，不得执行 cutover，不得把生产 backend 切到 PostgreSQL。
9. 若需要修改生产服务配置、部署新代码或重启 `fin-ops.service` 才能做 service-level shadow-read，必须先记录 `BLOCKED`，说明需要用户明确授权；不得自行修改或重启。
10. 优先实现/使用 one-off read-only rehearsal CLI 或脚本完成生产 shadow-read，比修改生产 service 更安全。
11. 所有输出、文档、日志、测试快照和 mismatch report 不得包含密码、token、secret、完整 Mongo/PostgreSQL URI 或业务敏感原文 payload。
12. shadow-read mismatch 必须有分级：
    - `P0`: 关键业务金额/状态/绑定关系不一致，且无法解释；
    - `P1`: 关键读模型缺失或数量不一致，影响后续切换；
    - `P2`: metadata、排序、runtime timestamp、可解释历史差异；
    - `ignored`: 已明确忽略字段或非业务差异。
13. 文档更新为阶段 11 执行记录和 Gate 判定。

你必须使用子代理并行完成可并行任务：

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- 主线程负责最终集成、冲突处理、测试、生产只读命令执行、文档和 Gate 判定。
- 子代理可以只读梳理，也可以作为 worker 修改代码；如果让 worker 写代码，必须给出明确文件所有权，避免多个 worker 修改同一文件。
- Worker 必须知道“不是独自在 codebase 中工作”，不得 revert 其他 worker 或用户改动。
- 如果当前 subagent 数量达到上限，先关闭不再需要的旧 agent。

硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. OA Mongo 只能继续作为现有 `MongoOAAdapter` 的只读源；阶段 11 不实现 OA 数据写回，也不把 OA 读路径纳入 app shadow-read rehearsal。
3. app Mongo `fin_ops_platform_app` 不得写入。若当前生产事实源是 app Mongo，只允许通过现有 app read APIs 或 read-only state-store adapter 读取 snapshot；不得执行写入、清理、建索引、compact、repair 或 migration。
4. 生产 PostgreSQL `fin_ops` 只能做只读 schema/count/snapshot/readiness/shadow compare 查询；不得在生产库做 destructive truncate、seed、contract write、API write smoke、dual write 或 cutover。
5. 阶段 11 不得修改或重启生产 `fin-ops.service`；不得修改生产运行配置；不得把生产 backend 切到 PostgreSQL/shadow/dual，除非用户在执行过程中另行明确授权。没有授权时，service-level shadow-read 必须标记 `BLOCKED`，并改用 one-off read-only rehearsal。
6. 所有 destructive integration test 必须使用 disposable PostgreSQL test DB。DB 名必须包含 `test`，否则必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；如果无法证明是 test DB，立即停止并记录 `BLOCKED`。
7. 优先使用本机临时 PostgreSQL cluster 跑真实 integration；必须使用 UTF8 cluster，例如 `initdb --encoding=UTF8 --locale=C`。测试结束必须 stop cluster 并删除 temp dir。
8. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码、prompt 或测试快照。所有 URI 输出必须脱敏。
9. 不得把业务 SQL 散落到 app route/service 业务逻辑里。shadow-read rehearsal 代码必须通过 state store/repository/preflight 边界访问数据。
10. 默认 local/Mongo 模式必须保持现有行为。未配置 PostgreSQL/shadow rehearsal 时，不得读取生产 `DATABASE_URL`，不得初始化 PostgreSQL connection，不得影响 `python -m pytest -q` 和 app `--check`。
11. PostgreSQL 模式下所有 SQL 必须参数化；禁止用用户输入拼 SQL。只允许对受控 schema/table/domain 名使用白名单拼接。
12. 文件读取必须保持已有兼容：
    - app-owned local path
    - 旧 store：`gridfs://<file_id>/<name>`
    - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`
13. 不修改前端 DTO、不改 API 返回结构。若 rehearsal 需要新增字段，只能放在 CLI report 或 readiness/health 的后向兼容扩展字段中；如会影响现有前端契约，先记录 `BLOCKED`。
14. 不新增 schema migration，除非 shadow rehearsal 过程发现必须有持久化审计/outbox 表；如需新增 `0008`，必须先写 blocker 说明、migration tests、rollback plan，并确认不是用本地 artifact 或现有 `job.background_jobs` / `audit.app_health_alerts` 可表达。
15. 不执行 dual-write、不执行 mirror-write、不执行 production cutover。阶段 11 只能做 shadow-read rehearsal 和 readiness judgment。
16. 不要在 prompt、文档或最终输出中写入 SSH 密码。若需要登录服务器，使用会话中已有凭据或向用户确认，不要把密码持久化。

阶段 10 已完成事实：

- 阶段 10 Gate：`PASS`。
- `state_store_diff.py` 已实现 JSON-safe diff、稳定 path、默认 ignored metadata 和 secret/URI redaction。
- `ShadowStateStore` 已实现 primary read + best-effort shadow compare，默认 compare disabled，不阻断 primary read。
- `DualStateStore` 已实现 primary-first dual write wrapper，但阶段 11 禁止启用 production dual-write。
- `state_store_factory.py` 已支持 `FIN_OPS_APP_STORAGE_BACKEND=shadow|dual` 的 preflight-only guard；`dual` 需要 `FIN_OPS_CUTOVER_PREFLIGHT_ONLY=1`。
- `verify_cutover_preflight.py` 已实现只读 PostgreSQL preflight CLI，并拒绝 cutover/write flags。
- 默认全量测试通过：`1187 passed, 16 skipped`。
- 本机 UTF8 disposable PostgreSQL integration 通过：`21 passed`。
- 生产只读 smoke 通过：
  - `fin-ops.service=active`
  - `schema_migrations=0001,0002,0003,0004,0005,0006,0007`
  - 核心 counts 顺序为 `import_batches, import_batch_rows, import_files, invoices, bank_transactions, search_index_rows`
  - counts 为 `6,897,31,391,431,822`
- 阶段 10 没有执行生产 shadow-read 观测窗口、生产 dual-write 或 cutover。

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
- `docs/database-migration/09-postgresql-repository-extraction-transaction-boundary.md`
- `docs/database-migration/10-shadow-dualwrite-cutover-preflight.md`
- `docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`

必须先读的代码：

- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/state_store_diff.py`
- `backend/src/fin_ops_platform/services/shadow_state_store.py`
- `backend/src/fin_ops_platform/services/dual_state_store.py`
- `backend/src/fin_ops_platform/services/cutover_preflight.py`
- `backend/src/fin_ops_platform/tools/verify_cutover_preflight.py`
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
- `tests/test_state_store_diff.py`
- `tests/test_shadow_state_store.py`
- `tests/test_dual_state_store.py`
- `tests/test_cutover_preflight.py`
- `tests/test_state_store_factory_preflight.py`
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
   - `python -m pytest tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_dual_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py -q`
   - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q`
   - `python -m pytest -q`
   - `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
3. 检查本机 PostgreSQL 工具：
   - `command -v initdb && command -v pg_ctl && command -v createdb && command -v psql`
4. 如果可用，启动 UTF8 临时 cluster，创建 `fin_ops_stage11_test`，运行真实 integration；测试结束必须 stop cluster 并删除 temp dir。
5. 使用 production PostgreSQL only-read smoke 确认阶段 10 事实没有回退。
6. 使用子代理并行完成以下任务：
   - Explorer A：梳理当前 production app storage source、部署形态、是否可以不重启服务完成 one-off read-only rehearsal；只读服务器检查，不写任何生产资源。
   - Explorer B：梳理 state-store read methods，定义阶段 11 可比对 domain 白名单、参数样本来源、忽略字段和 P0/P1/P2 分类。
   - Worker C：实现 shadow rehearsal domain runner / report builder / tests，只负责本地代码和 fake/integration tests。
   - Worker D：实现 production-safe CLI guard、redaction、JSON/Markdown report artifact，负责 CLI tests。
   - Explorer E：核验 PostgreSQL production counts/schema/preflight、阶段 10 回归项不回退、文档 Gate 证据。
   - Worker F：更新阶段 11 文档和 runbook，主线程最终整合。

推荐文件结构：

- Create: `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- Create: `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- Create: `tests/test_shadow_read_rehearsal.py`
- Create/Modify: `tests/test_shadow_state_store.py` only if production rehearsal needs wrapper behavior refinement.
- Modify: `backend/src/fin_ops_platform/services/state_store_factory.py` only if one-off rehearsal needs additional read-only guard; do not loosen existing `mongo` rejection unless you implement a read-only adapter and tests.
- Modify: `backend/src/fin_ops_platform/app/server.py` only if adding backward-compatible readiness extension; prefer CLI artifact over API contract changes.
- Create: `docs/database-migration/11-production-shadow-read-rehearsal.md`
- Modify: `docs/database-migration/README.md`
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md` only to link stage 11 outcome; do not rewrite cutover plan.

建议配置设计：

- `FIN_OPS_SHADOW_REHEARSAL_RUN_ID`
  - optional text id for report artifacts.
- `FIN_OPS_SHADOW_REHEARSAL_DOMAINS`
  - comma-separated domain whitelist; default should be a conservative safe list, not all methods.
- `FIN_OPS_SHADOW_REHEARSAL_LIMIT`
  - max sample count per domain; must validate positive integer.
- `FIN_OPS_SHADOW_REHEARSAL_OUTPUT`
  - optional local output path under `docs/database-migration/reports/` or temp dir.
- `FIN_OPS_SHADOW_COMPARE_SAMPLE_RATE`
  - reuse existing parsing; default `1.0` for deterministic CLI rehearsal unless production service-level sampling is later authorized.
- `FIN_OPS_PRIMARY_STORAGE_BACKEND`
  - explicit primary source for rehearsal. Allowed values must be fail-fast and safe.
- `FIN_OPS_SHADOW_STORAGE_BACKEND`
  - explicit shadow source, normally `postgres`.
- `FIN_OPS_POSTGRES_DATABASE_URL`
  - required only when selected backend is `postgres`; must never be printed raw.
- `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY`
  - required `1` for production rehearsal CLI; if absent, CLI refuses to run against production-like sources.

所有 config parsing 必须：

- fail fast on unknown/unsupported values;
- redact any URI in errors/logs;
- not instantiate PostgreSQL connection unless selected mode requires it;
- preserve existing default behavior when new env vars are absent;
- refuse production-like rehearsal unless read-only guard is explicit.

任务 11.0：安全基线和阶段文档

- [ ] 读完必读文档和代码。
- [ ] 记录 branch 和 dirty worktree。不要 revert 非 11 改动。
- [ ] 运行启动步骤中的基线测试。
- [ ] 创建 `docs/database-migration/11-production-shadow-read-rehearsal.md`。
- [ ] 文档记录阶段边界：11 不做 production cutover、不启用 production dual-write、不写生产 PostgreSQL、不写 app Mongo、不触碰 OA Mongo。
- [ ] 文档列出阶段 10 `PASS` 事实和本阶段目标。
- [ ] 确认没有任何命令触碰 `form_data_db.form_data`。

Acceptance:

- 文档存在。
- 基线结果已记录。
- 如果基线失败，先判断是否与 11 范围相关；相关则修复，不相关则记录风险。

任务 11.1：生产运行形态只读盘点

Requirements:

- [ ] 通过只读 SSH 命令确认生产服务状态、工作目录、当前环境变量来源、是否已部署阶段 10 代码。
- [ ] 不读取、不输出 secret；如必须看 env 文件，只能 grep key names 或用脱敏脚本输出 safe subset。
- [ ] 判断当前生产 app storage source：
  - `local_pickle`
  - app Mongo
  - PostgreSQL
  - unknown
- [ ] 判断是否可以在不重启服务、不修改配置、不部署新代码的情况下做 one-off shadow rehearsal。
- [ ] 判断如果需要部署/重启才能做 service-level shadow-read，标记为 `BLOCKED_FOR_SERVICE_LEVEL_SHADOW`，并继续尝试 one-off read-only rehearsal。

Recommended safe server checks:

- `systemctl is-active fin-ops.service`
- `systemctl show fin-ops.service --property=FragmentPath,DropInPaths,WorkingDirectory,ExecStart,EnvironmentFile --no-pager`
- `ps -eo pid,cmd | grep fin_ops_platform | grep -v grep`
- `sudo -u postgres psql -d fin_ops -Atc "select string_agg(version, ',' order by version) from public.schema_migrations;"`
- 仅在不会输出 secret 的前提下检查 key names；不要 cat 完整 env 文件。

Acceptance:

- 文档写明 production runtime source 和是否可做 one-off rehearsal。
- 没有生产写入。
- 没有 secret 输出。

任务 11.2：定义 shadow-read domain 白名单

Files:

- Create/Modify: `docs/database-migration/11-production-shadow-read-rehearsal.md`
- Create: `tests/test_shadow_read_rehearsal.py`
- Create: `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`

Requirements:

- [ ] 梳理可安全比对的 state-store read domains。初始白名单必须保守，优先选择无参数或可安全采样参数的 domains。
- [ ] 不把 OA read adapter 纳入 rehearsal。
- [ ] 不读取 file binary payload 做大体积 diff；文件 domain 只比较 metadata/reference/count/hash where already available。
- [ ] 每个 domain 必须记录：
  - method name
  - primary source
  - shadow source
  - parameters source
  - expected shape
  - ignored paths
  - severity mapping
  - max sample/limit
- [ ] 如果某个关键 domain 缺少安全参数样本来源，先标记 `blocked_domain`，不要猜参数。

建议初始 domains：

- `load_app_settings`
- `load_background_jobs`
- `load_app_health_alerts`
- `load_workbench_pair_relations`
- `load_no_oa_bank_batches`
- `load_bank_transaction_categories`
- `load_turnover_relations`
- `load_workbench_read_models` with safe month/scope samples only if discoverable from production PostgreSQL read-only counts.
- `load_workbench_candidate_matches` with safe month/scope samples only if discoverable.
- `load_cost_statistics_read_models`
- `load_tax_offset_read_models`
- tax/ETC domains only if parameterless or if safe samples are available from PostgreSQL formal tables.

Acceptance:

- 白名单 domain 有清晰参数来源。
- 未能比对的 domain 有明确 blocker，不 silent skip。
- tests 覆盖 domain whitelist validation。

任务 11.3：实现 ShadowReadRehearsalRunner

Files:

- Create: `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- Create: `tests/test_shadow_read_rehearsal.py`

Requirements:

- [ ] 实现数据结构：
  - `ShadowReadDomainSpec`
  - `ShadowReadDomainResult`
  - `ShadowReadRehearsalReport`
- [ ] 实现 `ShadowReadRehearsalRunner(primary_store, shadow_store, domain_specs, run_id, max_mismatches)`。
- [ ] Runner 只能调用白名单 read methods。禁止调用 `save*`、`store*`、`delete*`、`truncate*`、`confirm*`、`submit*`、`withdraw*`、`revert*` 等可能写入的方法。
- [ ] 每个 domain 调用 primary read 和 shadow read，然后用 `diff_state_snapshots()` 比对。
- [ ] shadow error 不阻断整个 rehearsal，但 domain result 必须记录 `status=shadow_error` 和脱敏 error。
- [ ] primary error 必须记录 `status=primary_error`，并根据 domain severity 影响 Gate。
- [ ] 每个 mismatch 必须按 P0/P1/P2/ignored 分类。
- [ ] Report 必须包含：
  - `run_id`
  - `started_at`
  - `completed_at`
  - `primary_backend`
  - `shadow_backend`
  - `domain_results`
  - `summary`
  - `gate_recommendation`
  - `redacted=true`
- [ ] Report 必须 JSON serializable，并不得包含 secret/full URI。

Acceptance:

- `python -m pytest tests/test_shadow_read_rehearsal.py -q` 通过。
- fake store tests 覆盖 match、mismatch、shadow error、primary error、forbidden method、redaction、severity summary。

任务 11.4：实现只读 rehearsal CLI

Files:

- Create: `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- Create/Modify: `tests/test_shadow_read_rehearsal.py`

Requirements:

- [ ] CLI 支持：
  - `--json`
  - `--markdown`
  - `--output <path>`
  - `--domains <csv>`
  - `--limit <n>`
  - `--primary-backend <backend>`
  - `--shadow-backend <backend>`
  - `--require-read-only-guard`
  - `--production`
- [ ] CLI 必须拒绝以下 flags：
  - `--cutover`
  - `--enable-dual-write`
  - `--dual-write`
  - `--write`
  - `--restart-service`
  - `--switch-backend`
- [ ] CLI 在 `--production` 时必须要求 `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`。
- [ ] CLI 不得默认连接生产 PostgreSQL；只有显式 shadow backend 为 postgres 且 URL env 存在时才构造连接。
- [ ] CLI 输出 artifact 默认写到 `docs/database-migration/reports/`，文件名包含 run id 和 `stage11.shadow-read`。
- [ ] artifact 内容必须脱敏。
- [ ] 如果 production app source 无法在本地构造，只能输出 `BLOCKED` report，说明需要在服务器 one-off 执行或需要部署授权。

Acceptance:

- CLI unit tests 通过。
- `python -m py_compile backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py` 通过。
- CLI fake checker/report tests 覆盖 JSON、Markdown、forbidden flags、read-only guard、redaction。

任务 11.5：本机真实 PostgreSQL rehearsal 验证

Requirements:

- [ ] 启动本机 UTF8 disposable PostgreSQL cluster。
- [ ] 创建 `fin_ops_stage11_test`。
- [ ] apply migrations。
- [ ] 用 fake/local primary + PostgreSQL shadow 或 PostgreSQL primary + PostgreSQL shadow 跑 rehearsal runner integration，证明 CLI/report 在真实 PostgreSQL connection 下可用。
- [ ] 测试结束 stop cluster 并删除 temp dir。

Acceptance:

- 真实 integration 通过。
- 文档记录命令和结果。
- 没有连接生产 DB 做 destructive test。

任务 11.6：生产只读 shadow-read rehearsal

Requirements:

- [ ] 先运行生产 PostgreSQL preflight CLI 或等价只读查询，确认 schema/counts/service 状态。
- [ ] 判断执行路径：
  - 如果阶段 11 代码未部署到服务器，且无法安全在本机连接到 production primary source，则记录 `BLOCKED_FOR_PRODUCTION_REHEARSAL_CODE_NOT_DEPLOYED`。
  - 如果可以通过 SSH 在服务器工作目录执行 one-off CLI，且无需修改配置/重启服务，则执行只读 rehearsal。
  - 如果必须修改 service env 或重启服务，停止并记录 `BLOCKED_REQUIRES_SERVICE_CHANGE_AUTHORIZATION`。
- [ ] 执行 production rehearsal 时必须：
  - 设置 explicit run id；
  - 设置 `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`；
  - 使用保守 domain whitelist；
  - 限制 sample count；
  - 输出脱敏 JSON/Markdown artifact；
  - 不输出 secret/full URI；
  - 不写 production PostgreSQL；
  - 不写 app Mongo；
  - 不触碰 OA Mongo。
- [ ] 如果执行失败，保留脱敏错误和 blocker，不做重试式破坏性排查。

Acceptance:

- 有 production shadow-read rehearsal report artifact，或明确 `BLOCKED/PARTIAL` 原因。
- 若有 mismatch，全部有 severity、domain、path、脱敏 payload 和人工解释状态。
- 若无法执行，文档明确用户需要做什么，例如授权部署 one-off CLI、提供只读 app primary source 访问方式、确认重启窗口等。

任务 11.7：mismatch 分析与 Gate

Files:

- Modify: `docs/database-migration/11-production-shadow-read-rehearsal.md`

Requirements:

- [ ] 汇总 domain results：
  - total domains
  - compared domains
  - matched domains
  - mismatched domains
  - skipped/blocked domains
  - shadow errors
  - primary errors
- [ ] 列出所有 P0/P1 mismatch，并说明是否解释清楚。
- [ ] P2 mismatch 只需分类汇总，避免暴露业务敏感 payload。
- [ ] 判断 Gate：
  - `PASS`: 生产 shadow-read rehearsal 已执行；关键白名单 domain 无未解释 P0/P1；默认测试和真实 PostgreSQL integration 通过；生产只读 smoke 通过。
  - `PARTIAL`: 本地/代码能力完成，但生产 rehearsal 只覆盖部分 domain，或存在可解释 P1/P2，需要后续扩大样本。
  - `BLOCKED`: 无法执行 production rehearsal、需要服务重启/部署授权、无法只读读取 primary source、存在未解释 P0/P1、或任一步需要写 OA/app Mongo/生产 PostgreSQL。
- [ ] 如果 Gate 不是 `PASS`，列出下一步需要用户做什么。
- [ ] 如果 Gate 为 `PASS`，建议下一阶段进入阶段 12：controlled dual-write / mirror-write rehearsal planning，不得直接 cutover。

Acceptance:

- 文档 Gate 判定清晰，不夸大。
- 下一步建议具体。

任务 11.8：最终验证矩阵

必须运行并记录：

- [ ] `python -m py_compile backend/src/fin_ops_platform/services/shadow_read_rehearsal.py backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py tests/test_shadow_read_rehearsal.py`
- [ ] `python -m pytest tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py -q`
- [ ] `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q`
- [ ] `python -m pytest -q`
- [ ] `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
- [ ] 本机 UTF8 disposable PostgreSQL integration，除非工具不可用；不可用时记录原因。
- [ ] 生产 PostgreSQL/service 只读 smoke。
- [ ] production shadow-read rehearsal CLI 或明确 blocker。

最终输出格式：

1. 阶段 11 Gate：`PASS` / `PARTIAL` / `BLOCKED`。
2. 生产 shadow-read 是否真实执行：是/否。
3. 如果否，无法完成原因，以及用户需要做什么。
4. 关键 changed files。
5. 测试和 smoke 结果。
6. production rehearsal report artifact 路径。
7. 是否触碰 OA Mongo：必须明确 `未触碰 form_data_db.form_data`。
8. 是否写 production PostgreSQL/app Mongo：必须明确没有，除非用户另行授权且实际发生；默认不允许。
9. 下一阶段建议。
```
