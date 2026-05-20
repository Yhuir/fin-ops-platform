# 13 阶段 Codex 执行 Prompt：Shadow mismatch remediation / backfill repair

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 13：基于阶段 12 `BLOCKED` 的真实 production one-off shadow-read report，修复或可审计解释所有阻断 controlled dual-write / mirror-write / cutover 的 P0/P1 mismatch，并重跑 production one-off shadow-read，直到 conservative domains 无未解释 P0/P1。阶段 13 必须补齐阶段 12 以及阶段 12 之前尚未完成的迁移 Gate：生产 shadow-read 必须真实执行并达到可进入下一阶段的结果；不能把仅本地测试、仅文档解释或仅部分 domain 修复包装成完成。

阶段 13 的核心目标：

1. 读取并分析阶段 12 final report：
   - `docs/database-migration/reports/stage12-shadow-read-20260520142049.stage12.shadow-read.json`
2. 将所有 mismatch 分为：
   - `adapter_shape_bug`: one-off `postgres_psql_json` adapter 与正式 `PostgresStateStore` 读取形态不一致；
   - `repository_load_shape_bug`: PostgreSQL repository load 返回形态与 `ApplicationStateStore` / service snapshot contract 不一致；
   - `transform_backfill_bug`: 阶段 03/04 export/transform/backfill 写入 PostgreSQL 的数据缺字段、字段形态错误、history/event 展开错误；
   - `runtime_drift`: 阶段 04 backfill 后 app Mongo primary 产生了新 runtime state，PostgreSQL 尚未 catch up；
   - `acceptable_runtime_noise`: 可解释 P2 运行态噪声，仅在证据充分时允许降级或从 Gate 中排除。
3. 修复本地代码和测试，确保本地 disposable PostgreSQL 中：
   - `PostgresStateStore` 与 `ApplicationStateStore` 的 7 个 conservative domains 可比对；
   - `PsqlShadowReadStore` 与 `PostgresStateStore` 对同一 PostgreSQL test DB 的 7 个 domains 输出等价；
   - mismatch report 继续脱敏，不包含业务原文 payload、secret、URI。
4. 生成 production repair plan：
   - app Mongo `fin_ops_platform_app` 仅作为 read-only source；
   - production PostgreSQL `fin_ops` 只允许修复 app-owned migration/backfill 数据；
   - 修复前必须有 PostgreSQL backup 或等价可回滚 snapshot；
   - 所有 production PostgreSQL 写入必须有 dry-run、row count bound、事务、回滚 SQL 或 restore path。
5. 在生产上执行受控修复或明确阻塞原因：
   - 可自动安全修复的 app-owned PostgreSQL 数据，执行事务化 repair；
   - 无法自动安全修复的 P0/P1，输出 `BLOCKED`，说明需要用户/业务确认什么。
6. 重跑 production one-off shadow-read：
   - 如果无未解释 P0/P1，Gate 可为 `PASS` 或 `PARTIAL`；
   - 如果仍有未解释 P0/P1，Gate 必须为 `BLOCKED`。
7. 更新阶段 13 执行文档和 report artifacts。

阶段 13 不是 dual-write，不是 mirror-write，不是 production cutover，不是切换读写事实源。阶段 13 完成后必须能清楚回答：

1. 阶段 12 的每个 P0/P1 mismatch 根因是什么。
2. 每个 mismatch 是已修复、已可审计解释、已降级，还是仍阻塞。
3. 是否修改了 production PostgreSQL；如果修改，修改了哪些 app-owned 表、多少行、如何回滚。
4. 是否重跑了真实 production one-off shadow-read；最终 report path 是什么。
5. 是否仍存在未解释 P0/P1。
6. 是否可以进入下一阶段 controlled dual-write / mirror-write rehearsal planning。

如果阶段 13 无法完全完成，最终输出和文档必须用 `BLOCKED` 标明原因，不得把“只解释了一部分 mismatch”“只修了本地 adapter”“只跑了本地测试”“只做了 production count smoke”包装成 shadow mismatch remediation 完成。

阶段 13 完成标准：

1. 阶段 12 report 中所有 P0/P1 mismatch 都有明确处理结果：
   - fixed；
   - explained-and-downgraded；
   - intentionally-excluded-with-evidence；
   - blocked-with-required-user-action。
2. 默认 local/Mongo 模式全量测试通过。
3. `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check` 仍显示默认 `storage.backend=local_pickle`。
4. 阶段 11/12 runner/CLI/adapter tests 通过。
5. 本机 UTF8 disposable PostgreSQL integration 和 local rehearsal smoke 通过。
6. `PsqlShadowReadStore` 与 `PostgresStateStore` 在同一 disposable PostgreSQL test DB 上输出等价，有测试覆盖。
7. 如执行 production PostgreSQL repair：
   - 有 repair dry-run artifact；
   - 有 backup/rollback 记录；
   - 只写 app-owned PostgreSQL 表；
   - 每条 SQL 是固定/白名单/参数化或由受控 JSON snapshot 生成；
   - 事务执行，row count 在预期 bounds 内；
   - 执行后有 post-repair count/hash smoke。
8. app Mongo `fin_ops_platform_app` 只允许只读读取；不得写入、清理、建索引、compact、repair 或 migration。
9. OA Mongo `form_data_db.form_data` 禁止触碰；不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
10. 生产服务 `fin-ops.service` 保持 active，且未被重启、未被修改。
11. 不修改 `/etc/systemd/*`、production release、生产配置、frontend DTO 或 API 返回结构。
12. 所有输出、文档、日志、测试快照、repair artifacts 和 report 不得包含密码、token、secret、完整 Mongo/PostgreSQL URI 或业务敏感原文 payload。
13. production one-off shadow-read final report 必须包含：
    - `run_id`
    - `primary_backend`
    - `shadow_backend`
    - compared domains
    - matched/mismatched/error summary
    - P0/P1/P2/ignored counts
    - bounded redacted mismatch samples
    - gate recommendation
14. 文档更新为阶段 13 执行记录、repair 记录和 Gate 判定。

你必须使用子代理并行完成可并行任务：

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- 主线程负责最终集成、生产命令执行、production PostgreSQL repair 决策、report 拉取、测试、文档和 Gate 判定。
- 子代理可以只读梳理，也可以作为 worker 修改本地代码/tests/docs；如果让 worker 写代码，必须给出明确文件所有权，避免多个 worker 修改同一文件。
- Worker 必须知道“不是独自在 codebase 中工作”，不得 revert 其他 worker 或用户改动。
- 如果当前 subagent 数量达到上限，先关闭不再需要的旧 agent。

硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. OA Mongo 只能继续作为现有 `MongoOAAdapter` 的只读源；阶段 13 不实现 OA 数据写回，也不把 OA adapter/OA source data 纳入 app shadow-read repair。
3. app Mongo `fin_ops_platform_app` 只能作为 app primary read-only source；不得执行任何写入、清理、建索引、compact、repair、migration、metadata ensure 或 schema 修改。
4. production PostgreSQL `fin_ops` 在阶段 13 可以被写入，但仅限 app-owned migration/backfill repair，且必须满足：
   - 先 dry-run；
   - 先 backup 或确认最近可恢复备份；
   - 固定白名单表；
   - 事务化；
   - row count bound；
   - rollback/restore path；
   - 不执行 cutover/dual-write/mirror-write。
5. 禁止写 PostgreSQL `staging` 以外的非 app-owned schema，除非明确属于 app migration repair；禁止 drop/truncate/alter/seed 任意 production 表。
6. 阶段 13 不得修改或重启生产 `fin-ops.service`；不得修改 `/etc/systemd/system/fin-ops.service` 或 drop-in；不得修改生产运行配置；不得把生产 backend 切到 PostgreSQL/shadow/dual。
7. 阶段 13 允许写入服务器 `/tmp/finops-stage13-*` 临时目录、脱敏 report artifact、dry-run/repair artifact；不得写 `/opt/fin-ops/current`、不得覆盖 production release。
8. 所有 destructive integration test 必须使用 disposable PostgreSQL test DB。DB 名必须包含 `test`，否则必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；如果无法证明是 test DB，立即停止并记录 `BLOCKED`。
9. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码、prompt 或测试快照。所有 URI 输出必须脱敏。
10. 远端命令不得 `cat` 完整 env/config/secrets 文件。只允许输出 key names、安全状态、脱敏值或 redaction 处理后的 report。
11. PostgreSQL 模式下所有 SQL 必须参数化；只允许对受控 schema/table/domain 名使用白名单拼接。
12. 若 repair 需要从 app Mongo 生成 snapshot，不得输出原始业务 payload；artifact 只允许包含 counts、hash、schema/key summary、redacted mismatch summary 或用于 PostgreSQL 写入的本地临时文件，且本地临时文件不得提交到 docs。
13. 文件读取必须保持已有兼容：
    - app-owned local path
    - 旧 store：`gridfs://<file_id>/<name>`
    - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`
    但阶段 13 conservative rehearsal 仍禁止读取 file bytes；只允许 metadata/state domains。
14. 不修改前端 DTO、不改 API 返回结构。
15. 不新增 schema migration，除非证明不新增 migration 无法修复 P0/P1；如必须新增 `0008`，必须先记录 blocker、写 migration tests、rollback plan，并在生产 apply 前单独确认。
16. 不执行 dual-write、不执行 mirror-write、不执行 production cutover。
17. 不要在 prompt、文档或最终输出中写入 SSH 密码。

阶段 12 已完成事实：

- 阶段 12 Gate：`BLOCKED`。
- 真实 production one-off shadow-read 已执行。
- 最终 report：
  - `docs/database-migration/reports/stage12-shadow-read-20260520142049.stage12.shadow-read.json`
- 阶段 12 文档：
  - `docs/database-migration/12-production-shadow-read-oneoff.md`
- 阶段 12 production run：
  - `run_id=stage12-shadow-read-20260520142049`
  - `primary_backend=mongo`
  - `shadow_backend=postgres_psql_json`
  - `limit=10`
  - `total_domains=7`
  - `matched_domains=0`
  - `mismatched_domains=7`
  - `primary_errors=0`
  - `shadow_errors=0`
  - `severity_counts=P0:14,P1:8,P2:12,ignored:0`
  - `redaction_scan=passed`
- 生产服务未被修改或重启：
  - `service_before=active:251543`
  - `service_after=active:251543`
  - `service_after_cleanup=active:251543`
  - `WorkingDirectory=/opt/fin-ops/current`
- 生产 PostgreSQL schema/counts 只读 smoke：
  - `schema_migrations=0001,0002,0003,0004,0005,0006,0007`
  - counts 顺序为 `app.import_batches, app.import_batch_rows, app.import_files, app.invoices, app.bank_transactions, read_model.search_index_rows`
  - counts 为 `6,897,31,391,431,822`
- 阶段 12 修改：
  - `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
  - `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
  - `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
  - `tests/test_shadow_read_rehearsal.py`
  - `docs/database-migration/12-production-shadow-read-oneoff.md`
  - docs indexes / cutover doc
- 阶段 12 验证：
  - `python -m pytest tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py -q`
  - `44 passed, 13 subtests passed`
  - PostgreSQL 回归矩阵：`32 passed, 11 skipped, 5 warnings, 10 subtests passed`
  - 默认全量测试：`1199 passed, 16 skipped, 5 warnings, 30 subtests passed`
  - app check：`status=ready`, `storage.backend=local_pickle`
- 阶段 12 没有写 app Mongo，没有触碰 OA Mongo `form_data_db.form_data`，没有写 production PostgreSQL。
- 阶段 12 发现生产 venv 缺少 `psycopg`，因此 one-off 使用 `postgres_psql_json` adapter；该 adapter 不是长期 runtime backend。

阶段 12 final mismatch summary：

| Domain | Status | Mismatches | P0 | P1 | P2 | 主要问题 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `app_settings` | `mismatched` | 5 | 0 | 5 | 0 | `allowed_usernames` 长度和顺序/成员指纹不一致 |
| `background_jobs` | `mismatched` | 10 | 0 | 0 | 10 | PostgreSQL shadow 中存在 primary Mongo 当前未出现的 job ids |
| `app_health_alerts` | `mismatched` | 2 | 0 | 0 | 2 | primary 与 shadow health alert snapshot 形态不一致 |
| `workbench_pair_relations` | `mismatched` | 10 | 10 | 0 | 0 | pair relation history 数量和 event payload 形态不一致 |
| `no_oa_bank_batches` | `mismatched` | 1 | 1 | 0 | 0 | primary 有 `schema_version`，shadow 缺失 |
| `bank_transaction_categories` | `mismatched` | 3 | 0 | 3 | 0 | primary 有 `schema_version`、`audit_log`、`categories` snapshot，shadow 缺失或形态不一致 |
| `turnover_relations` | `mismatched` | 3 | 3 | 0 | 0 | primary 有 `schema_version`、`audit_log`、`relations` snapshot，shadow 缺失 |

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
- `docs/database-migration/10-shadow-dualwrite-cutover-preflight.md`
- `docs/database-migration/11-production-shadow-read-rehearsal.md`
- `docs/database-migration/12-production-shadow-read-oneoff.md`
- `docs/database-migration/reports/stage12-shadow-read-20260520142049.stage12.shadow-read.json`
- `docs/database-migration/reports/stage11-production-shadow-read-rehearsal.blocked.json`
- `docs/database-migration/reports/fin_ops_app_export_20260519235526_5a233544.stage04.reconciliation.json`
- `docs/database-migration/04-staging-transform-reconciliation.md`
- `docs/database-migration/08-postgresql-domain-repository-final-closure.md`
- `docs/database-migration/09-postgresql-repository-extraction-transaction-boundary.md`

必须先读的代码：

- `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `tests/test_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_connection.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/common.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- `backend/src/fin_ops_platform/tools/postgres_transform.py`
- `backend/src/fin_ops_platform/tools/export_app_mongo.py`
- `backend/src/fin_ops_platform/tools/import_postgres_staging.py`
- `backend/src/fin_ops_platform/tools/reconcile_postgres_migration.py`
- `backend/src/fin_ops_platform/tools/exporters/workbench.py`
- `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_postgres_transform.py`
- `tests/test_reconcile_postgres_migration.py`
- `tests/test_postgres_repositories_core.py`
- `tests/test_postgres_repositories_boundaries.py`
- `tests/test_postgres_state_store.py`
- `tests/test_postgres_state_store_integration.py`
- `tests/test_state_store_contract.py`

启动步骤：

1. 记录当前 git branch 和 `git status --short`。不要 revert 非本阶段改动。
2. 运行本地基线：
   - `python -m py_compile backend/src/fin_ops_platform/services/shadow_read_rehearsal.py backend/src/fin_ops_platform/services/shadow_read_psql_store.py backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py tests/test_shadow_read_rehearsal.py`
   - `python -m pytest tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_cutover_preflight.py tests/test_state_store_factory_preflight.py -q`
   - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q`
   - `python -m pytest -q`
   - `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
3. 检查本机 PostgreSQL 工具：
   - `command -v initdb && command -v pg_ctl && command -v createdb && command -v psql`
4. 如果可用，启动 UTF8 临时 cluster，创建 `fin_ops_stage13_test`，运行真实 integration 和 local rehearsal CLI；测试结束必须 stop cluster 并删除 temp dir。
5. 使用 production read-only smoke 重新确认：
   - `fin-ops.service` active；
   - `/health` 仍是 `mongo/mongo_only/fin_ops_platform_app`；
   - schema migrations 仍为 `0001..0007`；
   - core counts 没有异常回退；
   - 不输出 env values 或 secrets。
6. 使用子代理并行完成以下任务：
   - Explorer A：只读分析阶段 12 report，按 domain 建立 mismatch taxonomy，不写文件。
   - Explorer B：只读对比 `PostgresStateStore`、`PsqlShadowReadStore`、repository load methods，找出 adapter/repository shape bugs，不写文件。
   - Explorer C：只读分析 `postgres_transform.py` 和 exporters，定位 transform/backfill 缺陷，不写文件。
   - Worker D：补测试，覆盖 7 个 conservative domains 的 state-store shape contract 和 `PsqlShadowReadStore` 等价性；只改 tests。
   - Worker E：修复 adapter/repository/transform 代码；必须明确文件所有权，不得改生产命令或 docs。
   - Worker F：准备阶段 13 文档模板、repair report 模板和 Gate checklist；只改 docs。
   - 主线程：整合代码、运行测试、执行 production dry-run/repair/rehearsal、拉取 report、清理远端临时资源、最终 Gate。

推荐文件结构：

- Create: `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`
- Create: `docs/database-migration/reports/<run_id>.stage13.shadow-read.json`
- Create: `docs/database-migration/reports/<run_id>.stage13.repair-plan.json`
- Create: `docs/database-migration/reports/<run_id>.stage13.repair-result.json` if production PostgreSQL repair is executed.
- Modify: `docs/database-migration/README.md`
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md` only to link stage 13 outcome.
- Modify: `backend/src/fin_ops_platform/services/shadow_read_psql_store.py` if adapter shape differs from `PostgresStateStore`.
- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py` if load fallback/shape contract is wrong.
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py` for workbench/category/no-OA/turnover load/save shape issues.
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py` for settings/background jobs/app health load/save shape issues.
- Modify: `backend/src/fin_ops_platform/tools/postgres_transform.py` for backfill transform shape issues.
- Modify: `backend/src/fin_ops_platform/tools/exporters/workbench.py` and/or `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py` only if export shape is proven wrong.
- Create or Modify: `backend/src/fin_ops_platform/tools/repair_shadow_mismatches.py` only if a reusable repair/dry-run CLI is needed.
- Create or Modify: `tests/test_shadow_read_rehearsal.py`
- Create: `tests/test_shadow_mismatch_remediation.py` if new repair CLI or domain-specific regression cases are added.
- Modify: `tests/test_postgres_transform.py`
- Modify: `tests/test_postgres_state_store.py`
- Modify: `tests/test_postgres_repositories_core.py`
- Modify: `tests/test_postgres_repositories_boundaries.py`

任务 13.0：阶段文档、基线和安全确认

- [ ] 读完必读文档和代码。
- [ ] 记录 branch 和 dirty worktree。不要 revert 非 13 改动。
- [ ] 创建 `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`。
- [ ] 文档记录阶段边界：13 只做 mismatch remediation / app-owned PostgreSQL repair / one-off shadow-read rerun；不做 dual-write、mirror-write、cutover、服务配置修改或重启。
- [ ] 运行启动步骤中的本地基线。
- [ ] 如果基线失败，先判断是否与 13 范围相关；相关则修复，不相关则记录风险。

Acceptance:

- 文档存在。
- 基线结果已记录。
- 未触碰 OA Mongo `form_data_db.form_data`。
- 没有写 app Mongo 或 production PostgreSQL。

任务 13.1：阶段 12 report triage 和 mismatch taxonomy

Files:

- Create/Modify: `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`
- Read: `docs/database-migration/reports/stage12-shadow-read-20260520142049.stage12.shadow-read.json`

Requirements:

- [ ] 解析 stage12 report，输出每个 domain 的：
  - mismatch paths；
  - kind；
  - severity；
  - primary/shadow shape summary；
  - 初步 root-cause category；
  - 是否 P0/P1 blocker。
- [ ] 严禁输出 raw payload values；只允许 counts/hash/type/key names。
- [ ] 对 7 个 domains 建立处理矩阵：
  - `app_settings`
  - `background_jobs`
  - `app_health_alerts`
  - `workbench_pair_relations`
  - `no_oa_bank_batches`
  - `bank_transaction_categories`
  - `turnover_relations`
- [ ] 明确哪些 mismatch 可能是 adapter shape bug，哪些必须修复生产 PostgreSQL 数据。

Acceptance:

- 文档中有完整 taxonomy 表。
- 所有 P0/P1 都有初步处理方向。
- 没有泄漏业务原文或 secret。

任务 13.2：本地 adapter/repository 等价性测试

Files:

- Modify: `tests/test_shadow_read_rehearsal.py`
- Create/Modify: `tests/test_shadow_mismatch_remediation.py`
- Modify: `backend/src/fin_ops_platform/services/shadow_read_psql_store.py` only if tests prove it is needed.

Requirements:

- [ ] 在 fake 或 disposable PostgreSQL 连接上构造 7 个 conservative domains 的样本。
- [ ] 验证 `PsqlShadowReadStore` 输出与 `PostgresStateStore` 对同一 PostgreSQL state 的输出等价。
- [ ] 覆盖 `state:<key>` fallback 行为：
  - `state:background_jobs`
  - `state:app_health_alerts`
  - `state:workbench_pair_relations`
  - `state:no_oa_bank_batches`
  - `state:bank_transaction_categories`
  - `state:turnover_relations`
- [ ] 覆盖空 snapshot 仍需保留 service contract keys 的 domains：
  - `schema_version`
  - `audit_log`
  - `categories`
  - `relations`
  - `batches`
- [ ] 覆盖 mismatch sample redaction，只保留摘要和 sha256。

Acceptance:

- 新测试先能复现阶段 12 adapter/repository shape 风险。
- 修复后测试通过。
- 如果证明 `PsqlShadowReadStore` 非根因，文档记录证据。

任务 13.3：修复 repository load shape contract

Files:

- Modify: `backend/src/fin_ops_platform/services/postgres_state_store.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- Modify: `tests/test_postgres_state_store.py`
- Modify: `tests/test_postgres_repositories_core.py`
- Modify: `tests/test_postgres_repositories_boundaries.py`

Requirements:

- [ ] 对照 `ApplicationStateStore` 和 runtime services 的 snapshot contract，修复 PostgreSQL load shape：
  - `load_app_settings()` 必须与当前 app settings contract 等价，特别是 user lists 的语义、排序、去重或顺序保留规则。
  - `load_workbench_pair_relations()` 必须返回 `pair_relations` 和 `pair_relation_history` 的正确形态，不能把整个 snapshot 嵌套进单个 event payload。
  - `load_no_oa_bank_batches()` 必须保留 service snapshot 需要的 `schema_version` / `batches` / `audit_log` 语义，或文档证明该字段可忽略。
  - `load_bank_transaction_categories()` 必须保留 `schema_version` / `categories` / `audit_log` 语义，空 categories 也应与 app snapshot 等价。
  - `load_turnover_relations()` 必须保留 `schema_version` / `relations` / `audit_log` 语义，空 relations 也应与 app snapshot 等价。
  - `load_app_health_alerts()` 必须与 `AppHealthAlertService.snapshot()` 形态一致，避免 `current_state:alerts:1` 这类 wrapper 噪声。
  - `load_background_jobs()` 需要明确 runtime jobs 是否属于必须等价的 state；如属于 P2 runtime noise，必须从 Gate 中降级或排除，并有证据。
- [ ] 不通过宽泛 ignored_paths 掩盖真实 P0/P1。
- [ ] 若某字段是 runtime metadata，不应作为 P0/P1 blocker；需要测试和文档解释。

Acceptance:

- Repository/state-store tests 覆盖修复。
- 7 个 domains 的本地 contract tests 通过。
- 文档说明每个 P0/P1 是否由 load shape contract 修复。

任务 13.4：修复 transform/backfill 缺陷

Files:

- Modify: `backend/src/fin_ops_platform/tools/postgres_transform.py`
- Modify: `backend/src/fin_ops_platform/tools/exporters/workbench.py` only if export shape is proven wrong.
- Modify: `backend/src/fin_ops_platform/tools/exporters/ops_tax_etc.py` only if export shape is proven wrong.
- Modify: `tests/test_postgres_transform.py`
- Modify: `tests/test_reconcile_postgres_migration.py`
- Modify: `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`

Requirements:

- [ ] 针对阶段 12 P0/P1 根因补 transform tests：
  - `workbench_pair_relations_meta` 或 history source 不应被写成单个 nested `pair_relation_history` payload；
  - `no_oa_bank_batches_meta` 的 `schema_version` / audit shape 要么写入兼容 snapshot，要么被明确解释；
  - `bank_transaction_categories_meta` 的 `schema_version` / audit shape 要么写入兼容 snapshot，要么被明确解释；
  - `turnover_relations` 的空 list、audit log、schema_version 要么写入兼容 snapshot，要么被明确解释；
  - `app_settings.allowed_usernames` 应与当前 production app Mongo primary 一致，不能使用过期 export 值。
- [ ] 修复 transform 代码，使后续 full backfill 不再产生同类 mismatch。
- [ ] 不新增 schema migration，除非明确证明现有 schema 无法表达修复。

Acceptance:

- Transform tests 通过。
- 文档列出 transform 修复与 stage12 mismatch 的对应关系。
- 如果某项不应在 transform 修复而应 runtime catch-up，明确记录。

任务 13.5：生产只读诊断和 repair plan

Files:

- Create: `docs/database-migration/reports/<run_id>.stage13.repair-plan.json`
- Modify: `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`

Requirements:

- [ ] 只读确认生产服务状态和 storage 仍为 `mongo/mongo_only/fin_ops_platform_app`。
- [ ] 只读确认 production PostgreSQL schema/counts。
- [ ] 只读从 app Mongo primary 获取 7 个 domains 的 safe summary：
  - counts；
  - top-level key names；
  - deterministic hashes；
  - 不输出 raw payload。
- [ ] 只读从 production PostgreSQL 获取对应 domains 的 safe summary。
- [ ] 生成 repair plan JSON，包含：
  - run_id；
  - domain；
  - root_cause_category；
  - repair_action；
  - target_tables；
  - expected_row_counts；
  - risk_level；
  - rollback_strategy；
  - whether_requires_user_confirmation。
- [ ] 如果无法安全生成 production repair SQL/plan，标记 `BLOCKED_REPAIR_PLAN_UNSAFE`。

Acceptance:

- repair plan artifact 可 JSON parse。
- repair plan 不包含 secret、URI、业务原文 payload。
- 每个 P0/P1 都有 repair action 或 blocker。

任务 13.6：本地 disposable PostgreSQL repair rehearsal

Files:

- Create/Modify: `backend/src/fin_ops_platform/tools/repair_shadow_mismatches.py` if needed.
- Create/Modify: `tests/test_shadow_mismatch_remediation.py`
- Modify: `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`

Requirements:

- [ ] 在 disposable PostgreSQL test DB 上重放阶段 13 repair 逻辑。
- [ ] repair 前制造与阶段 12 同类 mismatch。
- [ ] dry-run 输出 expected statements/row counts，但不写。
- [ ] apply 模式在 test DB 中事务化修复。
- [ ] repair 后 local shadow-read 7 个 conservative domains 无 P0/P1。
- [ ] 验证 rollback 或 restore path。

Acceptance:

- Test DB 名包含 `test`。
- 本地 repair rehearsal 通过。
- 不依赖 production data 原文。

任务 13.7：production PostgreSQL backup / dry-run / repair

Files:

- Create: `docs/database-migration/reports/<run_id>.stage13.repair-result.json` if repair is executed.
- Modify: `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`

Requirements:

- [ ] 在生产写入前，确认有 PostgreSQL backup 或创建可恢复 backup。
  - 只记录 backup path、时间、sha256/size、命令摘要；
  - 不记录 secrets。
- [ ] 确认 repair SQL 只涉及 app-owned tables，例如：
  - `app.app_settings`
  - `job.background_jobs`
  - `audit.app_health_alerts`
  - `app.workbench_pair_relations`
  - `app.workbench_pair_relation_history`
  - `app.no_oa_bank_batches`
  - `app.no_oa_bank_batch_events`
  - `app.bank_transaction_categories`
  - `app.bank_transaction_category_events`
  - `app.turnover_relations`
  - `app.turnover_relation_events`
- [ ] 先 dry-run，记录 expected row counts。
- [ ] 如果 dry-run row counts 超出 repair plan bounds，停止并标记 `BLOCKED_REPAIR_ROW_COUNT_OUT_OF_BOUNDS`。
- [ ] 如安全，执行 production PostgreSQL transaction repair。
- [ ] 执行后只读验证 target tables counts/hashes。
- [ ] 生产服务 before/after active 且 PID 不变。
- [ ] 远端临时 repair files 清理或记录保留路径。

Acceptance:

- 如果执行了 production repair，有 repair-result JSON。
- repair-result JSON 不包含 raw payload 或 secret。
- 生产 PostgreSQL 写入范围与 repair plan 一致。
- app Mongo 没有写入。
- OA Mongo `form_data_db.form_data` 未触碰。
- 生产服务未改动、未重启。

任务 13.8：重跑 production one-off shadow-read

Files:

- Create: `docs/database-migration/reports/<run_id>.stage13.shadow-read.json`
- Create: `docs/database-migration/reports/<run_id>.stage13.shadow-read.md` if useful.
- Modify: `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`

Requirements:

- [ ] 使用阶段 12 已验证的 one-off 临时代码同步模式，或修复后的同等安全模式。
- [ ] 远端只写 `/tmp/finops-stage13-shadow-read-<run_id>/`。
- [ ] 使用：
  - `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`
  - `primary_backend=mongo_readonly`
  - `shadow_backend=postgres_psql_json` or native `postgres` if production venv now safely supports it
  - `--production`
  - `--limit 10` or documented bounded limit
  - conservative domains:
    - `app_settings`
    - `background_jobs`
    - `app_health_alerts`
    - `workbench_pair_relations`
    - `no_oa_bank_batches`
    - `bank_transaction_categories`
    - `turnover_relations`
- [ ] Pull report back to local `docs/database-migration/reports/`.
- [ ] Validate:
  - JSON parse；
  - `redacted=true`；
  - no password/token/secret/URI；
  - no OA Mongo domain；
  - no raw payload。
- [ ] Clean remote temp dir after report is safely pulled.

Acceptance:

- 有真实 production stage13 shadow-read report。
- 服务 before/after active 且 PID 不变。
- report 无未解释 P0/P1 才能进入下一阶段。

任务 13.9：Gate 判定和文档更新

Files:

- Create/Modify: `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`
- Modify: `docs/database-migration/README.md`
- Modify: `docs/index.md` if needed.
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md`

Requirements:

- [ ] 文档记录：
  - 阶段 12 blocker；
  - 每个 P0/P1 的 root cause；
  - 本地代码/test 修复；
  - production repair plan；
  - production repair result or blocker；
  - final production shadow-read report；
  - service before/after；
  - remote cleanup；
  - tests；
  - Gate。
- [ ] Gate 规则：
  - `PASS`: stage13 production one-off shadow-read 已真实执行；7 个 conservative domains 无未解释 P0/P1；production repair 如执行则有 backup/dry-run/result；服务未改动/未重启；app Mongo 未写；OA Mongo 未触碰；全量测试通过。
  - `PARTIAL`: 无未解释 P0，但仍有可解释 P1/P2 或 runtime noise 需要扩大样本；不得进入 production cutover，但可规划更窄范围 mirror-write rehearsal。
  - `BLOCKED`: 仍存在未解释 P0/P1；repair plan unsafe；production repair 需要额外人工授权；无法重跑 production one-off；任何步骤需要写 app Mongo/OA Mongo 或重启/改生产服务。
- [ ] 如果 Gate 为 `PASS`，下一阶段建议生成 14：controlled dual-write / mirror-write rehearsal planning。
- [ ] 如果 Gate 不是 `PASS`，列出用户需要做什么。

最终输出格式：

1. 阶段 13 Gate：`PASS` / `PARTIAL` / `BLOCKED`。
2. 阶段 12 未完成内容是否已完成：逐项说明。
3. production repair 是否执行：是/否；如果是，列出 app-owned tables 和 row counts；如果否，说明原因。
4. final production one-off shadow-read 是否真实执行：是/否。
5. final report artifact 本地路径。
6. P0/P1/P2 summary。
7. 如果无法完成，原因和用户需要做什么。
8. changed files。
9. 测试和 smoke 结果。
10. 是否触碰 OA Mongo：必须明确 `未触碰 form_data_db.form_data`。
11. 是否写 app Mongo：必须明确没有。
12. 是否修改/重启生产服务：必须明确没有。
13. 下一阶段建议。
```
