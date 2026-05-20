# 15 阶段 Codex 执行 Prompt：Production controlled mirror-write one-off rehearsal

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 15：基于阶段 14 `PASS_FOR_PLANNING` 的 runtime state policy，完成一次“用户已授权的 production controlled mirror-write one-off rehearsal”。阶段 15 必须先执行 production read-only preflight，并对 live `background_jobs` / `app_health_alerts` payload 运行阶段 14 分类器；只有没有 `blocked_unknown`，才允许执行受控、短窗口、可回滚的 runtime mirror-write one-off。阶段 15 必须把阶段 14 以及阶段 14 之前未完成事项闭合到“无未解释 P0/P1、runtime P2 有 live 分类、controlled mirror-write 已真实演练或明确 BLOCKED”的状态。

阶段 15 的授权范围仅限：

1. 在生产服务器临时目录部署或同步 one-off rehearsal 所需代码。
2. 只读读取 app primary state，用于 shadow-read、runtime policy classification、mirror-write dry-run。
3. 只读读取 production PostgreSQL，用于 preflight、backup verification、post-write shadow-read。
4. 在 dry-run、backup、row-count bound、policy classification 全部通过后，只写 production PostgreSQL 中 app-owned runtime mirror targets：
   - `job.background_jobs`
   - `audit.app_health_alerts`
   - `app.app_settings` 中 `settings_key in ('state:background_jobs','state:app_health_alerts')` 的 runtime snapshot rows
5. 取回脱敏 artifacts，更新本地阶段 15 文档和 reports。

阶段 15 明确不是 production cutover，不是切换读写事实源，不是修改生产服务配置，不是重启生产服务，不是开启长期 dual-write。阶段 15 完成后必须能回答：

1. 阶段 14 及之前是否仍有未完成 blocker。
2. production read-only preflight 是否真实执行，结果是什么。
3. live `background_jobs` 和 `app_health_alerts` 是否出现 `blocked_unknown`。
4. 若执行了 mirror-write，具体写了哪些 app-owned PostgreSQL runtime targets、写入/更新数量、backup/rollback 路径是什么。
5. mirror-write 前后 production one-off shadow-read 是否无 P0/P1。
6. 剩余 runtime P2 是否全部有 live policy classification。
7. 是否可以进入阶段 16：controlled dual-write observation / read-switch preflight，或必须先 remediation。

如果阶段 15 无法完全完成，最终输出和文档必须使用 `BLOCKED`、`BLOCKED_REQUIRES_USER_ACTION` 或 `PARTIAL` 标明原因，不得把“只写了文档”“只跑了本地测试”“只做了只读 preflight”“只做了 dry-run”包装成 controlled mirror-write rehearsal 完成。

## 必须使用子代理并行

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- 主线程负责最终集成、生产命令执行、production PostgreSQL 写入决策、artifact 拉取、测试、文档和 Gate 判定。
- 子代理可以只读梳理，也可以作为 worker 修改本地代码/tests/docs；若让 worker 写代码，必须给出明确文件所有权，避免多个 worker 修改同一文件。
- Worker 必须知道“不是独自在 codebase 中工作”，不得 revert 其他 worker 或用户改动。
- 如果当前 subagent 数量达到上限，先关闭不再需要的旧 agent。

建议并行任务：

1. Explorer A：只读核验阶段 14 artifacts、runtime policy 分类器、dual/shadow tests、阶段 13 final report，确认阶段 14 及之前无未完成 P0/P1。
2. Explorer B：只读梳理 production one-off mirror-write 安全边界、PostgreSQL target tables、backup/rollback 必需表和 rows。
3. Explorer C：只读核验远端生产服务状态、临时目录、Python/venv、psql/pg_dump 能力；不得输出 secret，不得读取 OA Mongo。
4. Worker D：如缺少 one-off runtime policy / mirror-write CLI，实现本地工具和测试；文件所有权限定在 `backend/src/fin_ops_platform/tools/`、`tests/test_*mirror*`、`tests/test_runtime_state_policy.py`。
5. Worker E：起草阶段 15 文档模板、report schema、redaction checklist；只改 `docs/database-migration/15-production-controlled-mirror-write-rehearsal.md` 草稿和 reports 模板，主线程最终整合。
6. 主线程：执行生产只读 preflight、dry-run、backup、受控 PostgreSQL runtime writes、post-write shadow-read、artifact 拉取、最终验证和 Gate。

## 硬约束

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. OA Mongo 只能继续作为现有 `MongoOAAdapter` 的只读源；阶段 15 不实现 OA 数据写回，也不把 OA adapter/OA source data 纳入 mirror-write。
3. app Mongo `fin_ops_platform_app` 只允许只读读取，用作 app primary state source。不得写入、清理、建索引、compact、repair、migration、metadata ensure 或 schema 修改。
4. production PostgreSQL `fin_ops` 默认只读；只有在 runtime policy preflight 无 `blocked_unknown`、dry-run 通过、backup 完成、row-count bound 通过后，才允许写入本阶段白名单 runtime targets。
5. production PostgreSQL 白名单写入范围仅限：
   - `job.background_jobs` upsert current primary runtime snapshot records；
   - `audit.app_health_alerts` upsert current primary runtime alert records；
   - `app.app_settings` 中 `settings_key='state:background_jobs'` 和 `settings_key='state:app_health_alerts'` 的 snapshot rows。
6. 禁止 `drop`、`truncate`、`alter`、`delete` production 表；阶段 15 不做 cleanup shadow-only runtime history。若 cleanup 看似必要，记录为阶段 16/后续 blocker，停止等待用户确认。
7. 禁止修改或重启 production `fin-ops.service`。不得修改 `/etc/systemd/system/fin-ops.service`、drop-in、生产运行配置或 `/opt/fin-ops/current`。
8. 禁止启用长期 production dual-write、mirror-write、shadow compare 或 cutover flag。不得把 production backend 切到 PostgreSQL、shadow 或 dual。
9. 阶段 15 允许写服务器 `/tmp/finops-stage15-*` 临时目录、脱敏 artifacts、backup 文件和临时代码；不得覆盖 production release。
10. 所有 destructive local/integration test 必须使用 disposable PostgreSQL test DB。DB 名必须包含 `test`，否则必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；无法证明是 test DB 时立即停止并记录 `BLOCKED`。
11. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 Mongo/PostgreSQL URI 写入文档、日志、代码、prompt 或测试快照。所有 URI 输出必须脱敏。
12. 远端命令不得 `cat` 完整 env/config/secrets 文件。只允许输出 key names、安全状态、脱敏值或 redaction 处理后的 report。
13. PostgreSQL 模式下所有 SQL 必须参数化；只允许对受控 schema/table/domain 名使用白名单拼接。
14. 不读取 file bytes；文件读取兼容策略仍保持：
    - app-owned local path；
    - 旧 store：`gridfs://<file_id>/<name>`；
    - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`。
15. 不修改前端 DTO，不改 API 返回结构。
16. 不新增 schema migration，除非证明现有 `job.background_jobs` / `audit.app_health_alerts` / `app.app_settings` runtime rows 无法表达本阶段必须写入的数据。若必须新增 `0008`，先记录 blocker、写 migration tests、rollback plan，并停止等待用户确认。
17. 不把 runtime P2 静默改成 ignored；必须输出 live 分类规则、classification counts 和可审计 explanation。
18. 不要在 prompt、文档或最终输出中写入 SSH 密码。

## 阶段 14 已完成事实

- 阶段 14 Gate：`PASS_FOR_PLANNING`。
- 阶段 14 execution doc：
  - `docs/database-migration/14-runtime-state-policy-mirror-rehearsal.md`
- 阶段 14 policy artifact：
  - `docs/database-migration/reports/stage14-runtime-state-policy.json`
- 新增 runtime state classifier：
  - `backend/src/fin_ops_platform/services/runtime_state_policy.py`
- 新增 classifier tests：
  - `tests/test_runtime_state_policy.py`
- 补强 tests：
  - `tests/test_dual_state_store.py`
  - `tests/test_shadow_read_rehearsal.py`
- 阶段 14 已确认：
  - 阶段 13 及之前 P0/P1 已清零。
  - `app_settings`、`workbench_pair_relations`、`no_oa_bank_batches`、`bank_transaction_categories`、`turnover_relations` 已 matched。
  - 剩余 `background_jobs` 和 `app_health_alerts` 是 runtime P2。
  - `save_background_jobs` 与 `save_app_health_alerts` 已在 `DualStateStore.WRITE_METHODS`。
  - file-byte writes 保持 primary-only。
  - P2-only shadow-read gate 为 `PARTIAL`，P0/P1 或 read error 才 `BLOCKED`。
  - 不需要 schema migration `0008`。
  - 阶段 14 没有生产写入、没有触碰 OA Mongo、没有写 app Mongo、没有修改或重启 service。
- 阶段 14 验证：
  - targeted：`65 passed, 33 subtests passed`
  - disposable PostgreSQL integration：`11 passed, 5 warnings, 16 subtests passed`
  - PostgreSQL 回归矩阵：`32 passed, 11 skipped, 5 warnings, 10 subtests passed`
  - full test：`1215 passed, 16 skipped, 5 warnings, 50 subtests passed`
  - app check：`status=ready`, `storage.backend=local_pickle`

## 阶段 13 final facts

- Final report：
  - `docs/database-migration/reports/stage13-shadow-read-postrepair-20260520154127.stage13.shadow-read.json`
- Gate：`PARTIAL`
- Summary：
  - `total_domains=7`
  - `compared_domains=7`
  - `matched_domains=5`
  - `mismatched_domains=2`
  - `primary_errors=0`
  - `shadow_errors=0`
  - `severity_counts=P0:0,P1:0,P2:13,ignored:0`
- matched domains：
  - `app_settings`
  - `workbench_pair_relations`
  - `no_oa_bank_batches`
  - `bank_transaction_categories`
  - `turnover_relations`
- remaining P2：
  - `background_jobs`: 10 `missing_in_primary`
  - `app_health_alerts`: 3 `missing_in_shadow`
- Stage 13 production PostgreSQL repair 已完成且只写 app-owned 表：
  - `app.app_settings`
  - `app.workbench_pair_relations`
  - `app.workbench_pair_relation_history`
- Stage 13 repair 有 dry-run、backup、row count bound、事务结果：
  - dry-run artifact：`docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-dry-run.json`
  - result artifact：`docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-result.json`
- Stage 13 没有修改或重启 `fin-ops.service`，没有触碰 OA Mongo。

## 必须先读的文档

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
- `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`
- `docs/database-migration/14-runtime-state-policy-mirror-rehearsal.md`
- `docs/database-migration/reports/stage14-runtime-state-policy.json`
- `docs/database-migration/reports/stage13-shadow-read-postrepair-20260520154127.stage13.shadow-read.json`
- `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-dry-run.json`
- `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-result.json`

## 必须先读的代码

- `backend/src/fin_ops_platform/services/runtime_state_policy.py`
- `backend/src/fin_ops_platform/services/dual_state_store.py`
- `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_connection.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/common.py`
- `backend/src/fin_ops_platform/services/state_store_diff.py`
- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/state_store_protocol.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/background_job_service.py`
- `backend/src/fin_ops_platform/services/app_health_alert_service.py`
- `backend/src/fin_ops_platform/services/app_health_service.py`
- `tests/test_runtime_state_policy.py`
- `tests/test_dual_state_store.py`
- `tests/test_shadow_read_rehearsal.py`
- `tests/test_state_store_factory_preflight.py`
- `tests/test_postgres_state_store_integration.py`
- `tests/test_app_postgres_mode_integration.py`
- `tests/postgres_test_utils.py`

## 推荐新增/修改文件

- Create if missing: `backend/src/fin_ops_platform/tools/run_runtime_state_policy_preflight.py`
  - 只读读取 primary/shadow runtime snapshots；
  - 对 live payload 执行 `classify_background_job()` / `classify_app_health_alert()`；
  - 输出脱敏 JSON report；
  - 不写任何数据库。
- Create if missing: `backend/src/fin_ops_platform/tools/run_controlled_mirror_write_rehearsal.py`
  - 支持 `--dry-run`；
  - 支持 `--execute`，但必须要求明确 env guard；
  - 只写白名单 runtime targets；
  - 输出脱敏 report 和 row counts；
  - 禁止 cutover / restart / service config flags。
- Create/modify tests:
  - `tests/test_runtime_state_policy.py`
  - `tests/test_controlled_mirror_write_rehearsal.py`
  - `tests/test_shadow_read_rehearsal.py`
  - `tests/test_dual_state_store.py`
- Create: `docs/database-migration/15-production-controlled-mirror-write-rehearsal.md`
- Create reports:
  - `docs/database-migration/reports/<run_id>.stage15.readonly-preflight.json`
  - `docs/database-migration/reports/<run_id>.stage15.runtime-policy.json`
  - `docs/database-migration/reports/<run_id>.stage15.mirror-write-dry-run.json`
  - `docs/database-migration/reports/<run_id>.stage15.pg-backup.json`
  - `docs/database-migration/reports/<run_id>.stage15.mirror-write-result.json`
  - `docs/database-migration/reports/<run_id>.stage15.shadow-read-after.json`
- Modify: `docs/database-migration/README.md`
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md` only to link stage 15 outcome.

## 启动步骤

1. 记录当前 git branch 和 `git status --short`。不要 revert 非本阶段改动。
2. 关闭不再需要的旧 subagents；启动阶段 15 子代理。
3. 读取全部必读文档和代码。
4. 复核阶段 14 artifacts：
   - JSON parse `docs/database-migration/reports/stage14-runtime-state-policy.json`
   - 确认 `stage14_gate=PASS_FOR_PLANNING`
   - 确认 `production_dual_write_enabled=false`
   - 确认 `production_cutover_enabled=false`
   - 确认 `production_writes_performed=false`
   - 确认 `oa_mongo_touched=false`
   - 确认 `app_mongo_written=false`
   - 确认 `schema_migration_required=false`
5. 复核阶段 13 final report：
   - `P0=0`
   - `P1=0`
   - matched domains 为 5 个 conservative business domains
   - 剩余 P2 仅 `background_jobs` 和 `app_health_alerts`
6. 运行本地基线：
   - `python -m py_compile backend/src/fin_ops_platform/services/runtime_state_policy.py backend/src/fin_ops_platform/services/dual_state_store.py backend/src/fin_ops_platform/services/shadow_read_rehearsal.py backend/src/fin_ops_platform/services/state_store_factory.py`
   - `python -m pytest tests/test_runtime_state_policy.py tests/test_dual_state_store.py tests/test_shadow_state_store.py tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_state_store_factory_preflight.py tests/test_cutover_preflight.py -q`
   - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q`
   - `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
7. 检查本机 PostgreSQL 工具：
   - `command -v initdb && command -v pg_ctl && command -v createdb && command -v psql`
8. 若工具可用，启动 UTF8 临时 cluster，创建 `fin_ops_stage15_test`，运行 PostgreSQL integration 和 mirror-write rehearsal tests；测试结束必须 stop cluster 并清理。
9. 如果任何阶段 14 或更早 artifact 缺失/不一致，先修复本地文档、report 或测试，再进入生产步骤。

## Runtime policy preflight 要求

必须先做 read-only runtime policy preflight，不能直接写 production PostgreSQL。

Read-only preflight 必须：

1. 只读读取 primary app state：
   - `load_background_jobs()`
   - `load_app_health_alerts()`
2. 只读读取 PostgreSQL shadow：
   - `load_background_jobs()`
   - `load_app_health_alerts()`
3. 对 primary-only、shadow-only、different-value runtime records 执行分类：
   - `classify_background_job(payload, present_in_primary=..., present_in_shadow=...)`
   - `classify_app_health_alert(payload, present_in_primary=..., present_in_shadow=...)`
4. 输出脱敏 report，不包含原始 payload：
   - run id
   - redacted=true
   - primary/shadow backend
   - domain counts
   - classification counts
   - `blocked_unknown_count`
   - `mirror_write_required_count`
   - bounded sample ids 或 hashed ids
   - reason summaries
   - no secret / no URI scan result
5. 若任一 domain 出现 `blocked_unknown_count > 0`：
   - 不执行 mirror-write；
   - 写 `BLOCKED_RUNTIME_POLICY_UNKNOWN`；
   - 文档说明需要用户/开发处理的具体 status/type/kind/severity category；
   - 结束阶段 15 或先进入本地 remediation。

## Mirror-write dry-run 要求

只有 read-only preflight 无 `blocked_unknown` 时才能进入 dry-run。

Dry-run 必须：

1. 计算计划写入的 runtime snapshot：
   - `background_jobs`: current primary `load_background_jobs()` snapshot
   - `app_health_alerts`: current primary `load_app_health_alerts()` snapshot
2. 不输出 payload，只输出：
   - job count
   - alert record count
   - active/attention/terminal/recovered counts
   - classification counts
   - target tables
   - row count bounds
   - payload hash
3. 检查 target tables 当前 row counts：
   - `job.background_jobs`
   - `audit.app_health_alerts`
   - `app.app_settings` rows for `state:background_jobs`, `state:app_health_alerts`
4. 生成 dry-run artifact：
   - `docs/database-migration/reports/<run_id>.stage15.mirror-write-dry-run.json`
5. 如果预计写入数量超出合理 bounds，停止并记录 `BLOCKED_ROW_COUNT_BOUND`。

建议初始 bounds：

- `background_jobs` primary current snapshot count <= 5000
- `app_health_alerts` records count <= 200
- `app.app_settings` runtime snapshot rows to upsert <= 2

如实际数量超过 bounds，不要自行扩大；记录 blocker 并询问用户。

## Production backup / rollback 要求

执行 production PostgreSQL runtime write 前必须备份：

1. 使用 `pg_dump --data-only --column-inserts` 或等价只备份白名单 targets：
   - `job.background_jobs`
   - `audit.app_health_alerts`
   - `app.app_settings` filtered rows cannot be directly filtered by pg_dump table selection, so either:
     - backup whole `app.app_settings` table; or
     - produce transaction-safe SQL copy for only `settings_key in ('state:background_jobs','state:app_health_alerts')`.
2. Backup artifact 保留在远端 `/tmp/finops-stage15-<run_id>/reports/`，本地只记录路径、size、sha256，不提交 SQL dump 内容。
3. 备份完成后输出脱敏 backup report：
   - backup path
   - backup size
   - sha256
   - included tables/rows
   - created_at
4. 如果备份失败，停止，记录 `BLOCKED_BACKUP_FAILED`。
5. rollback plan 必须写入阶段 15 文档：
   - stop using rehearsal writes；
   - restore runtime tables/rows from backup；
   - rerun shadow-read；
   - do not restart service unless separately authorized。

## Production execute 要求

执行前必须同时满足：

- 用户已同意阶段 15 controlled mirror-write one-off rehearsal。
- 阶段 14 policy artifact valid。
- production read-only preflight complete。
- `blocked_unknown_count=0`。
- dry-run complete。
- backup complete。
- service active and PID captured before execution。
- no OA Mongo access。
- no app Mongo write。
- target table whitelist verified。
- command environment does not print secrets。

执行方式：

1. 在远端临时目录运行 one-off script。
2. 设置显式 guard，例如：
   - `FIN_OPS_STAGE15_CONTROLLED_MIRROR_WRITE=1`
   - `FIN_OPS_STAGE15_RUN_ID=<run_id>`
   - `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1` for read-only phases only
3. 执行只允许调用：
   - `PostgresStateStore.save_background_jobs(primary_background_jobs_snapshot)`
   - `PostgresStateStore.save_app_health_alerts(primary_app_health_alerts_snapshot)`
4. 不调用 generic `save()`，避免写入非 runtime domains。
5. 不删除 shadow-only background jobs。
6. 不 cleanup recovered alerts。
7. 捕获 row count before/after：
   - `job.background_jobs`
   - `audit.app_health_alerts`
   - app settings runtime rows
8. 捕获 result artifact：
   - run id
   - target table names
   - before/after counts
   - upsert attempted counts
   - mirror success/failure summary
   - no raw payload
   - redacted=true
9. 如果写入失败：
   - 不重试破坏性命令；
   - 记录 failure；
   - 使用 backup/rollback plan 判定是否需要人工授权恢复；
   - rerun read-only smoke if possible；
   - final Gate 为 `BLOCKED_MIRROR_WRITE_FAILED`。

## Post-write shadow-read 要求

执行 mirror-write 后必须运行 production one-off shadow-read：

1. 使用 conservative domains：
   - `app_settings`
   - `background_jobs`
   - `app_health_alerts`
   - `workbench_pair_relations`
   - `no_oa_bank_batches`
   - `bank_transaction_categories`
   - `turnover_relations`
2. 输出：
   - `docs/database-migration/reports/<run_id>.stage15.shadow-read-after.json`
   - optional markdown summary
3. Gate 判定：
   - 任意 `primary_errors` 或 `shadow_errors` => `BLOCKED`
   - 任意 P0/P1 => `BLOCKED`
   - P2 只允许在 runtime policy artifact 中有 live classification；否则 `BLOCKED_RUNTIME_P2_UNCLASSIFIED`
   - P2-only 且 all classified => `PARTIAL_ACCEPTED_RUNTIME_POLICY`
   - zero mismatch => `PASS`
4. 若 `app_health_alerts` active missing-in-shadow 仍存在：
   - 如果 mirror write 已执行且没有 failure，记录为 `BLOCKED_MIRROR_WRITE_PARITY_FAILED`；
   - 不得静默忽略。
5. 若 `background_jobs` shadow-only terminal P2 仍存在：
   - 若 live classifier 归为 `cleanup_candidate` 或 `retention_only`，记录为 accepted runtime P2；
   - 不执行 cleanup。

## 生产临时目录建议

- `/tmp/finops-stage15-<run_id>/`
- 子目录：
  - `code/`
  - `reports/`
  - `backup/`
  - `logs/`

远端临时代码同步：

1. 本地打包最小执行代码：
   - include `backend/src/fin_ops_platform/`
   - include tests only if remote verification needs them
   - exclude `__pycache__`, `.pytest_cache`, local reports, secrets, `.env`, raw dumps
2. 上传到远端临时目录。
3. 使用远端 existing venv：
   - `/opt/fin-ops/venv/bin/python`
4. 不写 `/opt/fin-ops/current`。
5. 不修改 `/etc/systemd/*`。
6. 执行结束后，如果本地已取回 report，可清理远端临时代码；backup 可按文档保留或按用户确认清理。

## 任务分解

### 15.0 Safety baseline and previous-stage closure

- [ ] 读完必读文档和代码。
- [ ] 记录 branch 和 `git status --short`。
- [ ] 关闭旧 subagents，启动阶段 15 子代理。
- [ ] 复核阶段 14 policy artifact JSON。
- [ ] 复核阶段 13 final report，确认 P0/P1=0。
- [ ] 运行本地 baseline tests。
- [ ] 如发现阶段 14 或之前 artifact 缺失/不一致，先修复并记录。

### 15.1 Local tool/test readiness

- [ ] 检查是否已有 runtime policy preflight / mirror-write rehearsal CLI。
- [ ] 如果没有，先写 failing tests。
- [ ] 实现只读 runtime policy preflight CLI。
- [ ] 实现 controlled mirror-write rehearsal CLI，默认 `--dry-run`，`--execute` 必须有 explicit guard。
- [ ] 测试 CLI 拒绝 forbidden flags：`--cutover`、`--restart-service`、`--enable-dual-write`、`--write-all`、未知 domain。
- [ ] 测试 dry-run 不写 store。
- [ ] 测试 execute 只调用 `save_background_jobs` / `save_app_health_alerts`。
- [ ] 测试 report redaction，不包含 secret、URI、raw payload。
- [ ] 测试 `blocked_unknown` 阻止 execute。
- [ ] 跑 targeted tests。

### 15.2 Disposable PostgreSQL smoke

- [ ] 启动本机 UTF8 temporary PostgreSQL cluster。
- [ ] 创建 `fin_ops_stage15_test`。
- [ ] apply migrations。
- [ ] 用 fake/local primary snapshot 执行 dry-run。
- [ ] 用 test DB 执行 controlled mirror-write execute。
- [ ] 跑 post-write shadow-read。
- [ ] 确认 no P0/P1，runtime P2 gate 语义正确。
- [ ] stop cluster 并清理 temp dir。
- [ ] 将结果写入阶段 15 文档。

### 15.3 Production read-only preflight

- [ ] 生成 `run_id=stage15-mirror-write-<timestamp>`。
- [ ] 只读检查 production service active 和 PID。
- [ ] 只读检查 production storage backend/mode/database，输出脱敏摘要。
- [ ] 只读检查 production PostgreSQL schema_migrations 和 target row counts。
- [ ] 不读取 OA Mongo。
- [ ] 不写 app Mongo。
- [ ] 上传/同步 one-off read-only code 到 `/tmp/finops-stage15-<run_id>/code/`。
- [ ] 执行 production read-only shadow-read baseline，保存 artifact。
- [ ] 拉取 artifact 到 `docs/database-migration/reports/`。

### 15.4 Live runtime policy classification

- [ ] 在 production 临时目录执行 runtime policy preflight。
- [ ] 分类 live `background_jobs` primary/shadow mismatch。
- [ ] 分类 live `app_health_alerts` primary/shadow mismatch。
- [ ] 输出 `blocked_unknown_count`、`mirror_write_required_count`、`retention_only_count`、`rebuildable_count`、`cleanup_candidate_count`。
- [ ] 拉取 `stage15.runtime-policy.json`。
- [ ] 本地 JSON parse 和 redaction scan。
- [ ] 若 `blocked_unknown_count > 0`，停止；更新文档 Gate 为 `BLOCKED_RUNTIME_POLICY_UNKNOWN`。

### 15.5 Mirror-write dry-run and backup

- [ ] 仅在 `blocked_unknown_count=0` 时继续。
- [ ] 执行 mirror-write dry-run。
- [ ] 记录 target counts、bounds、payload hash、planned upsert counts。
- [ ] 拉取 dry-run artifact。
- [ ] 若 row count 超出 bounds，停止并记录 `BLOCKED_ROW_COUNT_BOUND`。
- [ ] 执行 production PostgreSQL backup。
- [ ] 记录 backup path、size、sha256、included tables/rows。
- [ ] 拉取 backup metadata artifact，不拉取或提交 raw SQL dump。
- [ ] 写 rollback plan 到阶段 15 文档。

### 15.6 Controlled production runtime mirror-write execute

- [ ] 捕获 service PID before。
- [ ] 确认不修改/restart service。
- [ ] 设置 explicit execute guard。
- [ ] 执行 only runtime mirror-write one-off。
- [ ] 写入范围只允许 `save_background_jobs` / `save_app_health_alerts` 对应 PostgreSQL targets。
- [ ] 捕获 row counts before/after。
- [ ] 捕获 service PID after，必须 unchanged 或至少 service 未重启；如 PID 变更，记录异常并调查。
- [ ] 拉取 result artifact。
- [ ] 本地 redaction scan。

### 15.7 Post-write shadow-read and Gate

- [ ] 执行 production post-write one-off shadow-read。
- [ ] 拉取 final shadow-read report。
- [ ] JSON parse 并校验 redacted。
- [ ] 确认 no primary/shadow errors。
- [ ] 确认 P0=0、P1=0。
- [ ] 对所有 runtime P2 引用 live classification artifact。
- [ ] 如果 active `app_health_alerts` 仍 missing-in-shadow，Gate 为 `BLOCKED_MIRROR_WRITE_PARITY_FAILED`。
- [ ] 如果只剩 classified runtime P2，Gate 为 `PARTIAL_ACCEPTED_RUNTIME_POLICY`。
- [ ] 如果全部 matched，Gate 为 `PASS`。

### 15.8 Docs, cleanup and final verification

- [ ] 更新 `docs/database-migration/15-production-controlled-mirror-write-rehearsal.md`。
- [ ] 更新 `docs/database-migration/README.md`。
- [ ] 更新 `docs/database-migration/07-shadow-dualwrite-production-cutover.md`，只链接阶段 15 结论。
- [ ] 记录远端临时目录 cleanup 状态。
- [ ] 记录 backup 保留路径。
- [ ] 运行本地 targeted tests。
- [ ] 运行 PostgreSQL 回归矩阵。
- [ ] 运行 `python -m pytest -q`。
- [ ] 运行 `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`，确认默认 `storage.backend=local_pickle`。
- [ ] 最终输出 changed files、reports、production actions、Gate、remaining blockers。

## Report redaction checklist

所有 stage15 report 必须通过：

- [ ] `redacted=true`
- [ ] 不包含服务器密码、Mongo 密码、PostgreSQL 密码、token、secret。
- [ ] 不包含完整 URI。
- [ ] 不包含 raw business payload。
- [ ] 不包含 OA Mongo `form_data_db.form_data` 内容或采样。
- [ ] runtime records 只允许 bounded id/hash、counts、classification、reason summary。
- [ ] PostgreSQL backup SQL dump 不提交到 repo。

## Gate 定义

`PASS`：

- 阶段 14 及之前 artifacts valid。
- production read-only preflight completed。
- live runtime policy classification `blocked_unknown_count=0`。
- mirror-write dry-run completed。
- backup completed。
- controlled runtime mirror-write executed successfully。
- post-write shadow-read no errors。
- P0=0、P1=0。
- no unclassified runtime P2。
- service not modified/restarted。
- no app Mongo write。
- no OA Mongo touch。
- final docs/reports updated。

`PARTIAL_ACCEPTED_RUNTIME_POLICY`：

- mirror-write executed successfully。
- post-write shadow-read P0=0、P1=0。
- still has P2, but every P2 is classified as `retention_only`、`rebuildable` or `cleanup_candidate` with live evidence.
- no active `app_health_alerts` missing-in-shadow after mirror-write.

`BLOCKED_RUNTIME_POLICY_UNKNOWN`：

- live runtime classifier finds `blocked_unknown`.
- No production mirror-write executed.

`BLOCKED_BACKUP_FAILED`：

- dry-run passed but backup failed.
- No production mirror-write executed.

`BLOCKED_ROW_COUNT_BOUND`：

- planned writes exceed configured bounds.
- No production mirror-write executed.

`BLOCKED_MIRROR_WRITE_FAILED`：

- production runtime mirror-write attempted and failed.
- Must document whether rollback is required and what user must authorize.

`BLOCKED_MIRROR_WRITE_PARITY_FAILED`：

- mirror-write reports success but post-write shadow-read still shows unclassified P2 or active `app_health_alerts` missing-in-shadow.

`BLOCKED_PRODUCTION_SAFETY`：

- service state changed unexpectedly, secrets would need to be exposed, required target cannot be whitelisted, or any step requires app Mongo/OA Mongo write.

## 最终输出要求

最终回答必须包含：

1. 阶段 15 Gate。
2. 是否执行了 production mirror-write。
3. 若执行，写入范围和 row count 摘要。
4. Backup artifact path、size、sha256 摘要，不输出 dump 内容。
5. Report artifact paths。
6. P0/P1/P2 summary。
7. runtime policy classification summary。
8. service before/after 状态。
9. 本地验证命令和结果。
10. 如果 BLOCKED，明确用户需要做什么。

不要在最终输出中写入 SSH 密码、DB 密码、token、secret 或完整 URI。
```
