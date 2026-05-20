# 15A 阶段 Codex 执行 Prompt：Workbench pair relations P0 remediation before mirror-write

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 15A：基于阶段 15 `BLOCKED_CONSERVATIVE_P0` 的 production read-only shadow-read 结果，专门解释或修复 `workbench_pair_relations` 新增 5 个 P0 mismatch，并重跑 production read-only shadow-read，直到 conservative domains 再次达到 `P0=0,P1=0`。阶段 15A 必须把阶段 15 以及阶段 15 之前未完成事项闭合到“workbench P0 已修复或可审计解释、runtime P2 仍有 policy classification、可以重新进入阶段 15 controlled mirror-write rehearsal”的状态。

阶段 15A 的核心目标：

1. 读取阶段 15 artifacts：
   - `docs/database-migration/15-production-controlled-mirror-write-rehearsal.md`
   - `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.readonly-preflight.json`
   - `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.runtime-policy.json`
   - `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.blocked-summary.json`
2. 证明阶段 15 及之前未完成项：
   - 阶段 14 及之前 P0/P1 曾已清零；
   - 阶段 15 runtime policy live classification 已 `PASS`，`blocked_unknown_count=0`；
   - 阶段 15 没有执行 mirror-write dry-run、backup、write 或 cutover；
   - 阶段 15 当前唯一 conservative blocker 是 `workbench_pair_relations` 的 `P0=5`。
3. 只读分析 `workbench_pair_relations` P0：
   - `pair_relation_history.length`
   - 4 个 `pair_relations.candidate:<hash>` `missing_in_shadow`
4. 判断根因：
   - `runtime_drift`: 阶段 13 repair 后 live app Mongo primary 又产生了新的 workbench relation/history；
   - `adapter_shape_bug`: `postgres_psql_json` adapter 输出形态与正式 `PostgresStateStore` 不一致；
   - `repository_load_shape_bug`: PostgreSQL repository load shape 与 app state contract 不一致；
   - `transform_backfill_bug`: 阶段 13 repair/backfill 逻辑漏写或形态错误；
   - `unexpected_data_contract`: primary/shadow 中出现阶段 13 未覆盖的新 shape。
5. 若可安全修复：
   - app Mongo `fin_ops_platform_app` 仅作为 read-only source；
   - production PostgreSQL 只允许修复 app-owned `workbench_pair_relations` 范围；
   - 必须先 dry-run、backup、row-count bound、事务化、生成 rollback plan；
   - 修复后重跑 production read-only shadow-read。
6. 若无法安全修复：
   - 输出 `BLOCKED_REQUIRES_USER_ACTION`；
   - 明确用户需要提供什么业务确认或授权。
7. 更新阶段 15A 文档和 reports，并说明是否可以重新进入阶段 15 mirror-write rehearsal。

阶段 15A 不是 mirror-write，不是 dual-write，不是 cutover，不是切换事实源。阶段 15A 不处理 `background_jobs` / `app_health_alerts` runtime mirror-write，只保留阶段 15 runtime policy classification 结论或必要时重跑只读分类。

## 你需要用户做什么

默认不需要用户先做任何操作。Codex 应先完成只读分析和 dry-run。

只有出现以下情况才需要用户授权或提供信息：

1. dry-run 证明必须写 production PostgreSQL `workbench_pair_relations` 范围时，需要用户确认执行 production repair。
2. row count 超出 bounds，需要用户确认是否扩大 bounds 或人工分析。
3. P0 涉及业务语义无法从 code/data contract 判断，需要用户确认这些 relation/history 是否应该存在。
4. 后续重新进入阶段 15 mirror-write 时，需要用户决定 production venv `psycopg` 临时依赖策略或授权安装依赖。

## 必须使用子代理并行

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- 主线程负责最终集成、生产命令执行、production PostgreSQL repair 决策、artifact 拉取、测试、文档和 Gate 判定。
- 子代理可以只读梳理，也可以作为 worker 修改本地代码/tests/docs；若让 worker 写代码，必须给出明确文件所有权，避免多个 worker 修改同一文件。
- Worker 必须知道“不是独自在 codebase 中工作”，不得 revert 其他 worker 或用户改动。
- 如果当前 subagent 数量达到上限，先关闭不再需要的旧 agent。

建议并行任务：

1. Explorer A：只读分析阶段 15 readonly-preflight report 中 `workbench_pair_relations` P0 paths，和阶段 13 final report 对比，判断是新 drift 还是旧问题复发。
2. Explorer B：只读梳理 `workbench_pair_relations` app Mongo primary load/export、PostgreSQL repository、`PsqlShadowReadStore` adapter、stage13 repair 逻辑，定位可能 shape bug。
3. Explorer C：只读梳理 production repair 安全边界、目标表、backup/rollback、row-count bound，禁止执行生产命令。
4. Worker D：如需要，补本地 test 覆盖 workbench relation/history shape、adapter 等价、candidate key hash mismatch 分类；文件所有权限定在 `tests/test_shadow_read_rehearsal.py`、`tests/test_postgres_repositories_*`、`tests/test_postgres_transform.py`、必要的 workbench repository/adapter 文件。
5. Worker E：起草阶段 15A 文档和 report schema；只改 docs 草稿，主线程最终整合。
6. 主线程：执行生产只读 diagnostics、repair dry-run、如授权则 repair、重跑 shadow-read、最终验证和 Gate。

## 硬约束

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. OA Mongo 只能继续作为现有 `MongoOAAdapter` 的只读源；阶段 15A 不实现 OA 数据写回，也不把 OA source data 纳入 repair。
3. app Mongo `fin_ops_platform_app` 只允许只读读取，用作 app primary state source。不得写入、清理、建索引、compact、repair、migration、metadata ensure 或 schema 修改。
4. production PostgreSQL `fin_ops` 默认只读；只有在 root cause 明确、dry-run 通过、backup 完成、row-count bound 通过后，才允许写入本阶段白名单 app-owned repair targets。
5. production PostgreSQL 白名单 repair target 仅限 workbench pair relation 范围：
   - `app.workbench_pair_relations`
   - `app.workbench_pair_relation_history`
   - 如且仅如代码证明 snapshot fallback 必须同步，允许 `app.app_settings` 中 `settings_key='state:workbench_pair_relations'`。
6. 禁止写除上述白名单外的 production PostgreSQL 表。
7. 禁止 `drop`、`truncate`、`alter` 任意 production 表。若 repair 需要 delete/rebuild 白名单表，必须 dry-run、backup、row-count bound、事务化，并在执行前明确说明删除/重建范围。
8. 阶段 15A 不得修改或重启 production `fin-ops.service`；不得修改 `/etc/systemd/system/fin-ops.service`、drop-in、生产运行配置或 `/opt/fin-ops/current`。
9. 阶段 15A 不得启用 production dual-write、mirror-write、shadow compare、read switch 或 cutover flag。
10. 阶段 15A 允许写服务器 `/tmp/finops-stage15A-*` 临时目录、脱敏 artifacts、backup 文件和临时代码；不得覆盖 production release。
11. 所有 destructive local/integration test 必须使用 disposable PostgreSQL test DB。DB 名必须包含 `test`，否则必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；无法证明是 test DB 时立即停止并记录 `BLOCKED`。
12. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 Mongo/PostgreSQL URI 写入文档、日志、代码、prompt 或测试快照。所有 URI 输出必须脱敏。
13. 远端命令不得 `cat` 完整 env/config/secrets 文件。只允许输出 key names、安全状态、脱敏值或 redaction 处理后的 report。
14. PostgreSQL 模式下所有 SQL 必须参数化；只允许对受控 schema/table/domain 名使用白名单拼接。
15. 不读取 file bytes；文件读取兼容策略仍保持：
    - app-owned local path；
    - 旧 store：`gridfs://<file_id>/<name>`；
    - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`。
16. 不修改前端 DTO，不改 API 返回结构。
17. 不新增 schema migration，除非证明不新增 migration 无法表达 workbench repair；如必须新增 `0008`，先记录 blocker、写 migration tests、rollback plan，并停止等待用户确认。
18. 不把 P0/P1 静默降级为 P2 或 ignored；必须有代码证据和生产 report 证据。
19. 不要在 prompt、文档或最终输出中写入 SSH 密码。

## 阶段 15 已完成事实

- 阶段 15 Gate：`BLOCKED_CONSERVATIVE_P0`。
- 阶段 15 execution doc：
  - `docs/database-migration/15-production-controlled-mirror-write-rehearsal.md`
- 阶段 15 reports：
  - `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.readonly-preflight.json`
  - `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.runtime-policy.json`
  - `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.blocked-summary.json`
- Production read-only shadow-read:
  - `gate=BLOCKED`
  - `matched_domains=4`
  - `mismatched_domains=3`
  - `primary_errors=0`
  - `shadow_errors=0`
  - `severity_counts=P0:5,P1:0,P2:13,ignored:0`
- Blocking domain:
  - `workbench_pair_relations`
  - `pair_relation_history.length`
  - 4 个 `pair_relations.candidate:<hash>` `missing_in_shadow`
- Runtime live policy:
  - `gate=PASS`
  - `blocked_unknown_count=0`
  - `background_jobs`: `cleanup_candidate=11`, `rebuildable=112`, `retention_only=23`
  - `app_health_alerts`: `retention_only=11`
- 阶段 15 production service:
  - `ActiveState=active`
  - `MainPID=452671`
  - `WorkingDirectory=/opt/fin-ops/current`
- 阶段 15 远端能力：
  - `psql` available
  - `pg_dump` available
  - production venv 缺少 `psycopg`
- 阶段 15 没有执行：
  - production mirror-write dry-run
  - production backup
  - production controlled mirror-write
  - post-write shadow-read
  - cutover
- 阶段 15 没有写 app Mongo，没有触碰 OA Mongo，没有写 production PostgreSQL，没有修改或重启 service。
- 阶段 15 本地验证：
  - targeted：`51 passed, 30 subtests passed`
  - PostgreSQL regression：`32 passed, 11 skipped, 5 warnings, 10 subtests passed`
  - full：`1224 passed, 16 skipped, 5 warnings, 50 subtests passed`
  - app check：`status=ready`, `storage.backend=local_pickle`

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
- `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`
- `docs/database-migration/14-runtime-state-policy-mirror-rehearsal.md`
- `docs/database-migration/15-production-controlled-mirror-write-rehearsal.md`
- `docs/database-migration/reports/stage13-shadow-read-postrepair-20260520154127.stage13.shadow-read.json`
- `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.readonly-preflight.json`
- `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.runtime-policy.json`
- `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.blocked-summary.json`

## 必须先读的代码

- `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/common.py`
- `backend/src/fin_ops_platform/services/postgres_snapshot_contracts.py`
- `backend/src/fin_ops_platform/tools/exporters/workbench.py`
- `backend/src/fin_ops_platform/tools/postgres_transform.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_shadow_read_rehearsal.py`
- `tests/test_postgres_repositories_core.py`
- `tests/test_postgres_repositories_boundaries.py`
- `tests/test_postgres_transform.py`
- `tests/test_export_app_mongo.py`
- `tests/test_state_store_diff.py`
- `tests/postgres_test_utils.py`

## 推荐新增/修改文件

- Create: `docs/database-migration/15A-workbench-p0-remediation.md`
- Create reports:
  - `docs/database-migration/reports/<run_id>.stage15A.workbench-diagnostics.json`
  - `docs/database-migration/reports/<run_id>.stage15A.repair-dry-run.json`
  - `docs/database-migration/reports/<run_id>.stage15A.pg-backup.json` if repair is executed
  - `docs/database-migration/reports/<run_id>.stage15A.repair-result.json` if repair is executed
  - `docs/database-migration/reports/<run_id>.stage15A.shadow-read-after.json`
- Modify tests only if code fix is needed:
  - `tests/test_shadow_read_rehearsal.py`
  - `tests/test_postgres_repositories_core.py`
  - `tests/test_postgres_repositories_boundaries.py`
  - `tests/test_postgres_transform.py`
  - `tests/test_export_app_mongo.py`
- Modify code only if a local bug is proven:
  - `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
  - `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
  - `backend/src/fin_ops_platform/tools/exporters/workbench.py`
  - `backend/src/fin_ops_platform/tools/postgres_transform.py`
- Modify docs:
  - `docs/database-migration/README.md`
  - `docs/database-migration/07-shadow-dualwrite-production-cutover.md`

## 启动步骤

1. 记录当前 git branch 和 `git status --short`。不要 revert 非本阶段改动。
2. 关闭不再需要的旧 subagents；启动阶段 15A 子代理。
3. 读取全部必读文档和代码。
4. 复核阶段 15 artifacts：
   - JSON parse readonly preflight/runtime-policy/blocked-summary。
   - 确认 runtime policy `blocked_unknown_count=0`。
   - 确认 production mirror-write 未执行。
   - 确认 blocker 是 `workbench_pair_relations` P0=5。
5. 运行本地基线：
   - `python -m py_compile backend/src/fin_ops_platform/services/shadow_read_rehearsal.py backend/src/fin_ops_platform/services/shadow_read_psql_store.py backend/src/fin_ops_platform/services/postgres_repositories/workbench.py backend/src/fin_ops_platform/tools/postgres_transform.py`
   - `python -m pytest tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_postgres_transform.py tests/test_export_app_mongo.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q`
   - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q`
   - `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
6. 检查本机 PostgreSQL 工具：
   - `command -v initdb && command -v pg_ctl && command -v createdb && command -v psql`
7. 若工具可用，启动 UTF8 临时 cluster，创建 `fin_ops_stage15a_test`，运行 workbench transform/repository/adapter 等价 smoke；测试结束必须 stop cluster 并清理。

## Production read-only diagnostics

必须先做 read-only diagnostics，不得直接 repair。

Diagnostics 要求：

1. 使用生产 app Mongo read-only primary 读取当前 `workbench_pair_relations` snapshot：
   - relation count
   - history count
   - candidate keys/hash summary
   - no raw payload
2. 使用 production PostgreSQL read-only shadow 读取当前 `workbench_pair_relations`：
   - `app.workbench_pair_relations` count
   - `app.workbench_pair_relation_history` count
   - `state:workbench_pair_relations` snapshot row exists/count/hash if applicable
   - no raw payload
3. 对 stage15 P0 paths 做 targeted comparison：
   - `pair_relation_history.length`
   - 4 个 `pair_relations.candidate:<hash>` missing-in-shadow
4. 输出 diagnostics artifact：
   - run id
   - redacted=true
   - service active/PID before
   - primary/shadow counts
   - hash-only sample keys
   - root cause classification
   - recommended action
5. 若 diagnostics 显示 P0 已自然消失，直接重跑 production read-only shadow-read；不得执行 repair。

## Repair dry-run 要求

只有 root cause 指向 production PostgreSQL 落后于 app Mongo primary，且可以从 current app Mongo read-only snapshot 安全重建 workbench pair relations 时，才能做 repair dry-run。

Dry-run 必须：

1. 从 app Mongo read-only primary 生成 current workbench pair relations snapshot。
2. 不输出 raw relation/history payload，只输出：
   - pair relation count
   - pair relation history count
   - candidate key hash summary
   - snapshot hash
   - target tables
   - planned insert/update/delete/rebuild counts
3. 检查 row count bounds。
4. 输出 dry-run artifact。
5. 如果超出 bounds，停止并记录 `BLOCKED_ROW_COUNT_BOUND`。

建议 bounds：

- pair relations count <= 10000
- pair relation history count <= 50000
- app settings snapshot rows <= 1

如实际数量超过 bounds，不要自行扩大；记录 blocker 并询问用户。

## Production backup / rollback 要求

执行 production PostgreSQL repair 前必须备份：

1. `pg_dump --data-only --column-inserts` 或等价方式备份：
   - `app.workbench_pair_relations`
   - `app.workbench_pair_relation_history`
   - 如会写 snapshot fallback，则备份 `app.app_settings` 或 `settings_key='state:workbench_pair_relations'` row。
2. Backup artifact 保留在远端 `/tmp/finops-stage15A-<run_id>/backup/` 或 `reports/`。
3. 本地只记录：
   - path
   - size
   - sha256
   - included tables/rows
   - created_at
4. 不提交 raw SQL dump。
5. backup 失败则停止，Gate=`BLOCKED_BACKUP_FAILED`。

Rollback plan 必须写入阶段 15A 文档：

- restore workbench pair relation tables/snapshot from backup；
- rerun read-only shadow-read；
- no service restart unless separately authorized。

## Production repair execute 要求

执行前必须同时满足：

- root cause 明确；
- dry-run artifact complete；
- backup complete；
- row-count bound passed；
- target table whitelist verified；
- service active/PID captured before；
- no OA Mongo access；
- no app Mongo write；
- command environment does not print secrets。

执行策略：

1. 使用远端临时目录 `/tmp/finops-stage15A-<run_id>/`。
2. 使用固定白名单 SQL 或正式 repository/transform 工具。
3. 所有写入在事务内执行。
4. 只写白名单 workbench repair targets。
5. 捕获 before/after counts。
6. 捕获 service active/PID after。
7. 输出 repair-result artifact。
8. 如果失败：
   - 不重试破坏性命令；
   - 记录 failure；
   - 判断是否需要 rollback；
   - final Gate=`BLOCKED_REPAIR_FAILED`。

## Post-repair shadow-read 要求

repair 后或 diagnostics 显示 P0 自然消失后，必须重跑 production read-only shadow-read：

1. 使用 conservative domains：
   - `app_settings`
   - `background_jobs`
   - `app_health_alerts`
   - `workbench_pair_relations`
   - `no_oa_bank_batches`
   - `bank_transaction_categories`
   - `turnover_relations`
2. 输出：
   - `docs/database-migration/reports/<run_id>.stage15A.shadow-read-after.json`
3. Gate 判定：
   - any primary/shadow error => `BLOCKED`
   - any P0/P1 => `BLOCKED`
   - only runtime P2 with existing stage15 classification => `PARTIAL_READY_FOR_STAGE15_RETRY`
   - zero mismatch => `PASS_READY_FOR_STAGE15_RETRY`
4. 若仍有 `workbench_pair_relations` P0，必须输出 remaining blocker，不得进入 mirror-write。

## 任务分解

### 15A.0 Safety baseline and previous-stage closure

- [ ] 读完必读文档和代码。
- [ ] 记录 branch 和 dirty worktree。
- [ ] 复核阶段 15 artifacts 和 Gate。
- [ ] 运行本地 baseline tests。
- [ ] 创建 `docs/database-migration/15A-workbench-p0-remediation.md`。
- [ ] 文档记录阶段边界：15A 不做 mirror-write、不做 cutover、不写 app Mongo、不触碰 OA Mongo。

### 15A.1 Root cause analysis

- [ ] 对比阶段 13 final report 和阶段 15 readonly preflight。
- [ ] 定位新增 P0 path。
- [ ] 读取 workbench repository/adapter/exporter/transform code。
- [ ] 判断是 drift、adapter bug、repository bug、transform/backfill bug 还是 data contract 变化。
- [ ] 如是本地代码 bug，先写 failing test，再修代码。
- [ ] 如是 production drift，进入 repair dry-run。

### 15A.2 Production read-only diagnostics

- [ ] 生成 run id：`stage15A-workbench-remediation-<timestamp>`。
- [ ] 同步 one-off diagnostics code 到远端临时目录。
- [ ] 只读读取 app Mongo primary workbench snapshot counts/hash。
- [ ] 只读读取 PostgreSQL workbench tables/snapshot counts/hash。
- [ ] 输出 diagnostics artifact。
- [ ] 拉取 artifact 到 `docs/database-migration/reports/`。
- [ ] 做 JSON parse 和 redaction scan。

### 15A.3 Repair dry-run

- [ ] 仅在 diagnostics 证明 production PostgreSQL 落后且可安全从 app Mongo current snapshot 重建时继续。
- [ ] 生成 repair dry-run artifact。
- [ ] 检查 row-count bounds。
- [ ] 如果 bounds 超限，停止。
- [ ] 如果 dry-run 显示无需 repair，重跑 shadow-read。

### 15A.4 Backup and repair execute

- [ ] 仅在 dry-run 通过且用户授权后继续。
- [ ] 执行 production PostgreSQL backup。
- [ ] 记录 backup metadata。
- [ ] 执行事务化 repair。
- [ ] 捕获 before/after counts。
- [ ] 拉取 repair-result artifact。
- [ ] service PID 前后必须记录。

### 15A.5 Post-repair validation

- [ ] 重跑 production read-only shadow-read。
- [ ] 拉取 final report。
- [ ] 确认 P0=0、P1=0。
- [ ] 确认 runtime P2 与阶段 15 live classification 不冲突；必要时重跑 runtime policy classification。
- [ ] 更新阶段 15A docs、README、cutover doc。

### 15A.6 Final verification

- [ ] 运行 targeted tests。
- [ ] 运行 PostgreSQL regression matrix。
- [ ] 运行 `python -m pytest -q`。
- [ ] 运行 `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`。
- [ ] 最终输出 Gate、reports、production actions、remaining blockers、下一步。

## Report redaction checklist

所有 stage15A report 必须：

- [ ] `redacted=true`
- [ ] 不包含服务器密码、Mongo/PostgreSQL 密码、token、secret。
- [ ] 不包含完整 URI。
- [ ] 不包含 raw business payload。
- [ ] 不包含 OA Mongo `form_data_db.form_data` 内容或采样。
- [ ] workbench relation/history 只允许 counts、hash、bounded id/hash、root cause category。
- [ ] PostgreSQL backup SQL dump 不提交到 repo。

## Gate 定义

`PASS_READY_FOR_STAGE15_RETRY`：

- workbench P0/P1 清零；
- production read-only shadow-read zero mismatch or only accepted runtime P2；
- no app Mongo write；
- no OA Mongo touch；
- no service restart/config change；
- docs/reports updated。

`PARTIAL_READY_FOR_STAGE15_RETRY`：

- workbench P0/P1 清零；
- remaining mismatch only runtime P2；
- runtime P2 already has stage15 live classification or refreshed classification；
- ready to retry stage15 mirror-write rehearsal。

`BLOCKED_ROOT_CAUSE_UNKNOWN`：

- 无法解释 workbench P0 根因；
- no production repair executed。

`BLOCKED_ROW_COUNT_BOUND`：

- dry-run planned counts exceed bounds；
- no production repair executed。

`BLOCKED_BACKUP_FAILED`：

- backup failed；
- no production repair executed。

`BLOCKED_REPAIR_REQUIRES_USER_AUTHORIZATION`：

- dry-run safe but production write requires explicit user confirmation；
- no production repair executed yet。

`BLOCKED_REPAIR_FAILED`：

- production repair attempted and failed；
- must document rollback status and required user action。

`BLOCKED_STILL_P0`：

- post-repair or rerun shadow-read still has P0/P1。

`BLOCKED_PRODUCTION_SAFETY`：

- any step would require app Mongo write, OA Mongo touch, service restart, systemd/release modification, secret exposure, or non-whitelisted production table write。

## 最终输出要求

最终回答必须包含：

1. 阶段 15A Gate。
2. 是否执行了 production PostgreSQL repair。
3. 若执行，写入范围和 row count 摘要。
4. Backup artifact path、size、sha256 摘要，不输出 dump 内容。
5. Diagnostics、dry-run、repair、final shadow-read artifact paths。
6. P0/P1/P2 summary。
7. workbench root cause summary。
8. service before/after 状态。
9. 本地验证命令和结果。
10. 是否可以重新进入阶段 15。
11. 如果 BLOCKED，明确用户需要做什么。

不要在最终输出中写入 SSH 密码、DB 密码、token、secret 或完整 URI。
```
