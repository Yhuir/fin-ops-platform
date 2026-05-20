# 14 阶段 Codex 执行 Prompt：Runtime state policy / controlled mirror-write rehearsal planning

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 14：基于阶段 13 `PARTIAL` 但 `P0/P1=0` 的 production one-off shadow-read 结果，补齐 runtime state 策略并完成 controlled dual-write / mirror-write rehearsal planning 与本地/测试库验证。阶段 14 必须明确 `background_jobs` 和 `app_health_alerts` 中哪些状态需要 mirror-write、哪些可重建、哪些可清理或保留为可审计 P2；必须把阶段 13 以及阶段 13 之前所有未完成事项闭合到“无未解释 P0/P1、runtime P2 有明确策略、可进入受控 mirror-write 演练”的状态。

阶段 14 的核心目标：

1. 读取阶段 13 final artifacts，确认阶段 13 及之前遗留内容：
   - `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`
   - `docs/database-migration/reports/stage13-shadow-read-postrepair-20260520154127.stage13.shadow-read.json`
   - `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-dry-run.json`
   - `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-result.json`
   - `docs/database-migration/reports/stage12-shadow-read-20260520142049.stage12.shadow-read.json`
2. 证明阶段 13 及之前未完成项已经被处理：
   - 阶段 12/13 所有 P0/P1 已清零；
   - `app_settings`、`workbench_pair_relations`、`no_oa_bank_batches`、`bank_transaction_categories`、`turnover_relations` 已 matched；
   - 生产 PostgreSQL repair 有 dry-run、backup、row count bound、事务结果；
   - 仍存在的 `background_jobs` 与 `app_health_alerts` 只剩 P2 runtime policy 问题。
3. 梳理 runtime state 策略：
   - `background_jobs`：按 job status/type/生命周期判定哪些必须 mirror-write，哪些是 terminal/history 可清理或可不迁移，哪些需要 retry/compensation。
   - `app_health_alerts`：按 alert source/severity/status/lifecycle 判定哪些必须 mirror-write，哪些可由 health check 重建，哪些是 transient/current-state 可不迁移。
   - 策略必须落到代码可执行的分类器、文档表格和测试，不允许只有口头说明。
4. 加固 dual-write / mirror-write 基础设施：
   - `DualStateStore` 必须明确覆盖 `save_background_jobs` 和 `save_app_health_alerts` 的 mirror-write 语义；
   - non-strict mirror failure 不阻断 primary，但必须记录脱敏 summary；
   - strict mirror failure 必须阻断并抛出明确错误；
   - primary failure 时不得执行 mirror write；
   - file-byte writes 继续 primary-only，不能在阶段 14 突然镜像文件 bytes。
5. 建立 controlled rehearsal 计划和本地/测试库验证：
   - 默认不开启生产 dual-write；
   - 使用 fake stores 和 disposable PostgreSQL test DB 验证 runtime policy 与 mirror write；
   - 如使用本机 PostgreSQL，DB 名必须包含 `test`，或显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；
   - 不允许对 production app Mongo 执行写入；
   - 不允许修改/restart production `fin-ops.service`；
   - 不允许启用 production dual-write/mirror-write/cutover。
6. 产出阶段 14 文档、policy artifact 和 Gate 判定：
   - runtime state policy；
   - controlled mirror-write rehearsal runbook；
   - 本地/测试库验证结果；
   - final readiness：是否可以进入下一阶段“授权后的 production controlled mirror-write one-off rehearsal”。

阶段 14 不是 production cutover，不是把生产事实源切到 PostgreSQL，不是在生产服务中启用 dual-write。阶段 14 完成后必须能清楚回答：

1. 阶段 13 final report 中剩余 `background_jobs` P2 的每个类别是什么策略：mirror-write、rebuildable、cleanup/retention、blocked。
2. 阶段 13 final report 中剩余 `app_health_alerts` P2 的每个类别是什么策略：mirror-write、rebuildable、cleanup/retention、blocked。
3. 如果未来生产启用 mirror-write，哪些 state-store write methods 会被镜像，哪些 primary-only，失败语义是什么。
4. 是否需要 schema migration `0008`；默认答案应为“不需要”，除非代码和测试证明现有 `job.background_jobs` / `audit.app_health_alerts` 无法表达必须审计的数据。
5. 是否有 production PostgreSQL 写入；阶段 14 默认不得有。如确需生产写入，必须先记录 `BLOCKED_REQUIRES_USER_AUTHORIZATION`，不得自行执行。
6. 是否可以进入阶段 15：授权后的 production controlled mirror-write one-off rehearsal。

如果阶段 14 无法完全完成，最终输出和文档必须用 `BLOCKED` 标明原因，不得把“只写了策略文档”“只跑了本地假测试”“只忽略了 P2”包装成完成。

阶段 14 完成标准：

1. 读取并复核阶段 13 final report，确认 `P0=0`、`P1=0`。
2. `background_jobs` runtime policy 完整落地：
   - 有策略文档；
   - 有代码分类器或等价可执行规则；
   - 有 unit tests 覆盖 active/retryable/terminal/stale/unknown 等关键状态；
   - 明确哪些 job 状态需要 mirror-write。
3. `app_health_alerts` runtime policy 完整落地：
   - 有策略文档；
   - 有代码分类器或等价可执行规则；
   - 有 unit tests 覆盖 active/recovered/acknowledged/transient/current-state 等关键状态；
   - 明确哪些 alert 状态需要 mirror-write 或可由 health check 重建。
4. `DualStateStore` 对 `save_background_jobs` 和 `save_app_health_alerts` 的 mirror-write 行为有测试覆盖。
5. `ShadowReadRehearsalRunner` 或其配置文档必须明确 P2 runtime domains 的 gate 语义：P2 可产生 `PARTIAL`，但不阻塞下一阶段；P0/P1 才阻塞。
6. 本地默认全量测试通过。
7. `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check` 仍显示默认 `storage.backend=local_pickle`。
8. PostgreSQL 回归矩阵通过；无 test DB 时 integration 必须安全 skip，并记录。
9. 若本机 PostgreSQL 可用，使用 UTF8 disposable test DB 完成 runtime policy / mirror-write smoke；测试结束必须 stop cluster 并清理。
10. 不修改生产 systemd、生产 release、生产运行配置。
11. 不重启 `fin-ops.service`。
12. 不写 app Mongo `fin_ops_platform_app`。
13. 不触碰 OA Mongo `form_data_db.form_data`。
14. 不执行 production dual-write、mirror-write 或 cutover。
15. 所有输出、文档、测试快照、report 不得包含密码、token、secret、完整 Mongo/PostgreSQL URI 或业务敏感原文 payload。
16. 文档更新：
    - `docs/database-migration/14-runtime-state-policy-mirror-rehearsal.md`
    - `docs/database-migration/README.md`
    - 必要时更新 `docs/database-migration/07-shadow-dualwrite-production-cutover.md`，只链接阶段 14 结论，不重写历史。
17. 如仍有 blocker，必须明确用户需要做什么；不能默认进入阶段 15。

你必须使用子代理并行完成可并行任务：

- REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
- 主线程负责最终集成、代码合并、测试、文档、Gate 判定；生产命令如需执行也只能由主线程执行。
- 子代理可以只读梳理，也可以作为 worker 修改本地代码/tests/docs；如果让 worker 写代码，必须给出明确文件所有权，避免多个 worker 修改同一文件。
- Worker 必须知道“不是独自在 codebase 中工作”，不得 revert 其他 worker 或用户改动。
- 如果当前 subagent 数量达到上限，先关闭不再需要的旧 agent。

硬约束：

1. OA Mongo `form_data_db.form_data` 禁止触碰。不得读、写、建索引、修复、清洗、备份或迁移该库/集合。
2. OA Mongo 只能继续作为现有 `MongoOAAdapter` 的只读源；阶段 14 不实现 OA 数据写回，也不把 OA adapter/OA source data 纳入 mirror-write。
3. app Mongo `fin_ops_platform_app` 在阶段 14 只允许只读核验；不得执行任何写入、清理、建索引、compact、repair、migration、metadata ensure 或 schema 修改。
4. production PostgreSQL `fin_ops` 默认只允许只读核验；不得写库、不得 truncate/delete/update/insert、不得创建表或索引。阶段 14 若发现必须写生产库，立即 `BLOCKED_REQUIRES_USER_AUTHORIZATION`。
5. 阶段 14 不得修改或重启生产 `fin-ops.service`；不得修改 `/etc/systemd/system/fin-ops.service` 或 drop-in；不得修改生产运行配置；不得把生产 backend 切到 PostgreSQL/shadow/dual。
6. 不执行 production dual-write，不执行 production mirror-write，不执行 production cutover。
7. 所有 destructive integration test 必须使用 disposable PostgreSQL test DB。DB 名必须包含 `test`，否则必须显式设置 `FIN_OPS_ALLOW_POSTGRES_TEST_DB=1`；如果无法证明是 test DB，立即停止并记录 `BLOCKED`.
8. 禁止把服务器密码、Mongo 密码、PostgreSQL 密码、token、secret、完整 URI 写入文档、日志、代码、prompt 或测试快照。所有 URI 输出必须脱敏。
9. 远端命令不得 `cat` 完整 env/config/secrets 文件。只允许输出 key names、安全状态、脱敏值或 redaction 处理后的 report。
10. PostgreSQL 模式下所有 SQL 必须参数化；只允许对受控 schema/table/domain 名使用白名单拼接。
11. 文件读取必须保持已有兼容：
    - app-owned local path；
    - 旧 store：`gridfs://<file_id>/<name>`；
    - 阶段 04：`gridfs://<bucket>/<legacy_gridfs_id>`。
    阶段 14 rehearsal 仍不得读取 file bytes，除非是在本地 disposable test fixture 中验证 primary-only file-write guard。
12. 不修改前端 DTO、不改 API 返回结构。
13. 不新增 schema migration，除非证明现有 `job.background_jobs` / `audit.app_health_alerts` 不能表达必须持久化的 runtime state；如必须新增 `0008`，先记录 blocker、写 migration tests、rollback plan，并停止等待用户确认。
14. 不把 P2 runtime mismatch 静默改成 ignored；必须有可审计策略、分类规则和文档说明。
15. 不要在 prompt、文档或最终输出中写入 SSH 密码。

阶段 13 已完成事实：

- 阶段 13 Gate：`PARTIAL`。
- 阶段 13 final report：
  - `docs/database-migration/reports/stage13-shadow-read-postrepair-20260520154127.stage13.shadow-read.json`
- 阶段 13 repair artifacts：
  - `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-dry-run.json`
  - `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-result.json`
- 阶段 13 execution doc：
  - `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`
- 阶段 13 final summary：
  - `total_domains=7`
  - `compared_domains=7`
  - `matched_domains=5`
  - `mismatched_domains=2`
  - `primary_errors=0`
  - `shadow_errors=0`
  - `severity_counts=P0:0,P1:0,P2:13,ignored:0`
  - `gate=PARTIAL`
- matched domains：
  - `app_settings`
  - `workbench_pair_relations`
  - `no_oa_bank_batches`
  - `bank_transaction_categories`
  - `turnover_relations`
- remaining P2 domains：
  - `background_jobs`: 10 `missing_in_primary` job ids present in PostgreSQL shadow but absent in current app Mongo primary.
  - `app_health_alerts`: 3 `missing_in_shadow` current health alert records present in app Mongo primary but absent in PostgreSQL shadow.
- 阶段 13 production PostgreSQL repair：
  - only app-owned tables:
    - `app.app_settings`
    - `app.workbench_pair_relations`
    - `app.workbench_pair_relation_history`
  - dry-run counts:
    - `allowed_usernames_count=6`
    - `pair_relations_count=142`
    - `pair_relation_history_count=17`
  - repair result:
    - `app_settings_rows=2`
    - `pair_relations_count=142`
    - `pair_relation_history_count=17`
  - remote backup:
    - `/tmp/finops-stage13-shadow-read-stage13-shadow-read-20260520150138/reports/stage13-shadow-read-20260520150138.stage13.pg-backup.sql`
    - `backup_size_bytes=595301`
- 阶段 13 没有修改或重启 `fin-ops.service`，service PID 前后保持 `251543`。
- 阶段 13 没有触碰 OA Mongo `form_data_db.form_data`。
- 阶段 13 本地全量验证：
  - `python -m pytest -q`
  - `1203 passed, 16 skipped, 5 warnings, 30 subtests passed`
- 阶段 13 app check：
  - `status=ready`
  - `storage.backend=local_pickle`

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
- `docs/database-migration/13-shadow-mismatch-remediation-backfill-repair.md`
- `docs/database-migration/reports/stage13-shadow-read-postrepair-20260520154127.stage13.shadow-read.json`
- `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-dry-run.json`
- `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-result.json`

必须先读的代码：

- `backend/src/fin_ops_platform/services/dual_state_store.py`
- `backend/src/fin_ops_platform/services/shadow_state_store.py`
- `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/shadow_read_psql_store.py`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/state_store_diff.py`
- `backend/src/fin_ops_platform/services/state_store_factory.py`
- `backend/src/fin_ops_platform/services/state_store_protocol.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- `backend/src/fin_ops_platform/services/background_job_service.py`
- `backend/src/fin_ops_platform/services/app_health_alert_service.py`
- `backend/src/fin_ops_platform/services/app_health_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_dual_state_store.py`
- `tests/test_shadow_state_store.py`
- `tests/test_shadow_read_rehearsal.py`
- `tests/test_state_store_diff.py`
- `tests/test_state_store_factory_preflight.py`
- `tests/test_cutover_preflight.py`
- `tests/test_postgres_state_store.py`
- `tests/test_postgres_state_store_integration.py`
- `tests/postgres_test_utils.py`

启动步骤：

1. 记录当前 git branch 和 `git status --short`。不要 revert 非本阶段改动。
2. 运行本地基线：
   - `python -m py_compile backend/src/fin_ops_platform/services/dual_state_store.py backend/src/fin_ops_platform/services/shadow_state_store.py backend/src/fin_ops_platform/services/shadow_read_rehearsal.py backend/src/fin_ops_platform/services/state_store_factory.py`
   - `python -m pytest tests/test_dual_state_store.py tests/test_shadow_state_store.py tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_state_store_factory_preflight.py tests/test_cutover_preflight.py -q`
   - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q`
   - `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
3. 读取 stage13 final report，生成本地 summary，确认 `P0=0,P1=0`。
4. 检查本机 PostgreSQL 工具：
   - `command -v initdb && command -v pg_ctl && command -v createdb && command -v psql`
5. 如可用，启动 UTF8 临时 cluster，创建 `fin_ops_stage14_test`，运行真实 integration；测试结束必须 stop cluster 并删除 temp dir。
6. 使用子代理并行完成以下任务：
   - Explorer A：只读梳理 `background_job_service.py`、相关 save/load 调用、job status/type/lifecycle，输出 runtime policy 候选。
   - Explorer B：只读梳理 `app_health_alert_service.py`、`app_health_service.py`、health alert save/load 调用，输出 runtime policy 候选。
   - Explorer C：只读梳理 `dual_state_store.py`、`shadow_state_store.py`、`state_store_factory.py` 当前 guard 和 tests，找出 controlled mirror rehearsal 缺口。
   - Worker D：实现 runtime policy 代码和 tests；文件所有权见下方推荐结构。
   - Worker E：补 dual/shadow/rehearsal tests；不得改 Worker D 文件，除非主线程协调。
   - Worker F：起草阶段 14 文档和 runbook；只改 docs，主线程最终整合。
   - 主线程：整合代码、运行测试、判断 Gate、更新最终文档。

推荐文件结构：

- Create: `backend/src/fin_ops_platform/services/runtime_state_policy.py`
- Create: `tests/test_runtime_state_policy.py`
- Modify: `backend/src/fin_ops_platform/services/dual_state_store.py`
  - 只在测试证明需要时修改；优先确认现有 `WRITE_METHODS` 已覆盖 `save_background_jobs` 和 `save_app_health_alerts`。
- Modify: `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
  - 只在需要把 runtime P2 policy 写入 spec/report metadata 时修改；不要把 P2 静默 ignored。
- Modify: `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
  - 只在需要输出 policy artifact 或 gate explanation 时修改。
- Modify: `tests/test_dual_state_store.py`
- Modify: `tests/test_shadow_read_rehearsal.py`
- Modify: `tests/test_state_store_factory_preflight.py`
- Create: `docs/database-migration/14-runtime-state-policy-mirror-rehearsal.md`
- Create: `docs/database-migration/reports/stage14-runtime-state-policy.json`
- Modify: `docs/database-migration/README.md`
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md` only if linking stage 14 outcome is useful.

Runtime policy 设计要求：

1. `background_jobs` policy 必须至少输出以下分类：
   - `mirror_write_required`: active/running/queued/scheduled/retryable/attention-needed 等会影响用户可见进度或后续补偿的 job。
   - `rebuildable`: 可由当前业务状态重新生成的 derived job/projection job。
   - `retention_only`: completed/succeeded/failed/cancelled/superseded 等历史 terminal job，仅保留审计/排障，不应阻塞 cutover。
   - `cleanup_candidate`: shadow 中存在但 primary 当前没有、且超过 retention policy 或 terminal 的 stale job。
   - `blocked_unknown`: status/type 无法分类，必须阻塞进入生产 mirror-write。
2. `app_health_alerts` policy 必须至少输出以下分类：
   - `mirror_write_required`: active/unacknowledged/high-severity/current user-visible alert。
   - `rebuildable`: 可由 health checks 重新生成的 current-state alert。
   - `retention_only`: recovered/acknowledged/resolved historical alert。
   - `cleanup_candidate`: shadow stale 或 primary transient 但不需要迁移的 alert。
   - `blocked_unknown`: severity/status/source 无法分类，必须阻塞进入生产 mirror-write。
3. Policy 函数必须只接受已经脱敏或业务内存 payload，不读取数据库、不执行 IO。
4. Policy artifact 只能包含 counts、status/type keys、hash/fingerprint、classification summary；不得输出业务敏感原文。
5. 未识别状态必须 fail closed：分类为 `blocked_unknown`。

Controlled mirror-write rehearsal 要求：

1. 本阶段只做 local/fake/disposable PostgreSQL controlled rehearsal，不启用生产服务 dual-write。
2. 测试必须覆盖：
   - `save_background_jobs` primary success + mirror success。
   - `save_app_health_alerts` primary success + mirror success。
   - mirror failure non-strict：primary success，summary 记录脱敏错误，不抛出。
   - mirror failure strict：抛出 `DualWriteMirrorError`，summary 记录 strict failure。
   - primary failure：mirror 不执行。
   - file write primary-only 行为不回退。
3. 如果需要 CLI/runbook：
   - 只生成 dry-run plan；
   - 不连接 production app Mongo write path；
   - 不写 production PostgreSQL；
   - 不修改 systemd。
4. `state_store_factory.py` default behavior 必须保持：
   - 不设置新 env 时仍为原行为；
   - `app --check` 仍显示 `storage.backend=local_pickle`；
   - `FIN_OPS_APP_STORAGE_BACKEND=dual` 必须继续 require `FIN_OPS_CUTOVER_PREFLIGHT_ONLY=1`。

任务 14.0：阶段 13 closure 复核

- [ ] 读完必读文档和代码。
- [ ] 记录 branch 和 dirty worktree；不得 revert 非 14 改动。
- [ ] 运行启动步骤中的本地基线。
- [ ] 解析 `stage13-shadow-read-postrepair-20260520154127.stage13.shadow-read.json`。
- [ ] 在阶段 14 文档中记录：
  - stage13 final gate；
  - P0/P1 已清零；
  - remaining P2 domains；
  - stage13 production repair scope 和 backup path。
- [ ] 如果发现 P0/P1 非 0，立即 `BLOCKED_STAGE13_REGRESSION`，不得继续 mirror-write planning。

Acceptance:

- 阶段 14 文档初稿存在。
- stage13 closure 表格完整。
- P0/P1=0 被自动/脚本或人工解析结果支持。

任务 14.1：`background_jobs` runtime policy

Files:

- Create/Modify: `backend/src/fin_ops_platform/services/runtime_state_policy.py`
- Create/Modify: `tests/test_runtime_state_policy.py`

Requirements:

- [ ] 先写 failing tests：
  - active/running/queued/scheduled/retryable -> `mirror_write_required`
  - completed/succeeded/cancelled/superseded -> `retention_only`
  - stale terminal shadow-only job -> `cleanup_candidate`
  - known derived/rebuildable job type -> `rebuildable` only if code evidence proves it can be rebuilt
  - unknown status/type -> `blocked_unknown`
- [ ] 实现最小 policy 代码。
- [ ] Policy output 必须包含：
  - `classification`
  - `reason`
  - `mirror_write_required`
  - `cutover_blocking`
  - safe `status`/`job_type` labels only
- [ ] 不输出 job payload 原文。
- [ ] 更新文档中的 `background_jobs` policy table。

Acceptance:

- `python -m pytest tests/test_runtime_state_policy.py -q` 通过。
- 文档明确哪些 job 需要 mirror-write。

任务 14.2：`app_health_alerts` runtime policy

Files:

- Modify: `backend/src/fin_ops_platform/services/runtime_state_policy.py`
- Modify: `tests/test_runtime_state_policy.py`

Requirements:

- [ ] 先写 failing tests：
  - active/high/error/current visible alert -> `mirror_write_required`
  - recovered/resolved/acknowledged alert -> `retention_only`
  - generated health current-state alert with rebuildable source -> `rebuildable`
  - stale shadow-only recovered alert -> `cleanup_candidate`
  - unknown status/severity/source -> `blocked_unknown`
- [ ] 实现最小 policy 代码。
- [ ] Policy output 必须包含：
  - `classification`
  - `reason`
  - `mirror_write_required`
  - `cutover_blocking`
  - safe `status`/`severity` labels only
- [ ] 不输出 alert payload 原文。
- [ ] 更新文档中的 `app_health_alerts` policy table。

Acceptance:

- `python -m pytest tests/test_runtime_state_policy.py -q` 通过。
- 文档明确哪些 alert 需要 mirror-write、哪些可重建。

任务 14.3：Policy artifact 生成

Files:

- Modify/Create as needed: `backend/src/fin_ops_platform/tools/` script only if justified.
- Create: `docs/database-migration/reports/stage14-runtime-state-policy.json`
- Modify: `docs/database-migration/14-runtime-state-policy-mirror-rehearsal.md`

Requirements:

- [ ] 基于阶段 13 final report 的 P2 paths 和可用的脱敏信息生成 policy artifact。
- [ ] Artifact 只包含：
  - `run_id`
  - source report path
  - domain counts
  - classification counts
  - blocked_unknown count
  - policy version
  - redaction flag
- [ ] 不包含 job/alert 原始 payload。
- [ ] 如果因为 stage13 report 脱敏样本不足无法分类单个 job/alert，artifact 必须标注 `requires_live_rehearsal_classification=true`，但仍要给出代码层策略。

Acceptance:

- JSON parse 通过。
- 不包含 secret/URI/payload。
- 若 `blocked_unknown > 0`，阶段 14 Gate 必须 `BLOCKED`。

任务 14.4：DualStateStore runtime mirror-write tests

Files:

- Modify: `tests/test_dual_state_store.py`
- Modify: `backend/src/fin_ops_platform/services/dual_state_store.py` only if tests show a real gap.

Requirements:

- [ ] 测试 `save_background_jobs` 被 mirror。
- [ ] 测试 `save_app_health_alerts` 被 mirror。
- [ ] 测试 mirror failure non-strict 不阻断 primary。
- [ ] 测试 mirror failure strict 抛出 `DualWriteMirrorError`。
- [ ] 测试 primary failure 不执行 mirror。
- [ ] 测试 error summary 脱敏。
- [ ] 测试 file write 仍 primary-only。

Acceptance:

- `python -m pytest tests/test_dual_state_store.py -q` 通过。
- 不改变默认 local/Mongo 行为。

任务 14.5：Shadow / rehearsal gate 语义加固

Files:

- Modify: `backend/src/fin_ops_platform/services/shadow_read_rehearsal.py` only if required.
- Modify: `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py` only if required.
- Modify: `tests/test_shadow_read_rehearsal.py`

Requirements:

- [ ] 明确 P2-only mismatch 的 gate 语义：
  - P0/P1 -> `BLOCKED`
  - P2-only -> `PARTIAL`
  - all matched/ignored -> `PASS`
- [ ] Tests 覆盖 P2-only report 不阻塞下一阶段 readiness，但仍不是 `PASS`。
- [ ] Report 必须继续脱敏。
- [ ] 不把 P2 静默改成 ignored。

Acceptance:

- `python -m pytest tests/test_shadow_read_rehearsal.py -q` 通过。
- 阶段 14 文档说明 `PARTIAL` 与下一阶段 readiness 的关系。

任务 14.6：Controlled mirror-write rehearsal local smoke

Files:

- Modify tests only unless a code gap is found:
  - `tests/test_dual_state_store.py`
  - `tests/test_state_store_factory_preflight.py`
  - `tests/test_app_postgres_mode_integration.py`

Requirements:

- [ ] 使用 fake stores 做 deterministic mirror-write rehearsal。
- [ ] 如果 disposable PostgreSQL 可用，创建 `fin_ops_stage14_test`，验证 `PostgresStateStore` 可作为 mirror store 保存：
  - `save_background_jobs`
  - `save_app_health_alerts`
  - 至少一个已 matched 的 domain，如 `save_app_settings`
- [ ] 不写生产 PostgreSQL。
- [ ] 不写 app Mongo。
- [ ] 测试后清理 test DB/cluster。

Acceptance:

- fake rehearsal tests 通过。
- 如本机 PostgreSQL 可用，真实 test DB smoke 通过；不可用则记录 skip 原因。

任务 14.7：阶段 14 文档和 runbook

Files:

- Create: `docs/database-migration/14-runtime-state-policy-mirror-rehearsal.md`
- Modify: `docs/database-migration/README.md`
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md` only if useful.

Requirements:

- [ ] 文档包含阶段边界。
- [ ] 文档包含 stage13 closure 事实。
- [ ] 文档包含 background jobs policy 表。
- [ ] 文档包含 app health alerts policy 表。
- [ ] 文档包含 controlled mirror-write rehearsal runbook：
  - preconditions
  - env flags
  - dry-run / local smoke
  - production forbidden actions
  - rollback / stop condition
- [ ] 文档包含 Gate 判定。
- [ ] 文档不得包含 secret、URI、业务 payload。

Acceptance:

- 文档路径正确。
- README 索引更新。
- 阶段 14 能独立说明下一阶段需要什么授权。

任务 14.8：最终验证

- [ ] 运行：
  - `python -m py_compile backend/src/fin_ops_platform/services/runtime_state_policy.py backend/src/fin_ops_platform/services/dual_state_store.py backend/src/fin_ops_platform/services/shadow_read_rehearsal.py`
  - `python -m pytest tests/test_runtime_state_policy.py tests/test_dual_state_store.py tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_shadow_state_store.py tests/test_state_store_factory_preflight.py tests/test_cutover_preflight.py -q`
  - `python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q`
  - `PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check`
  - `python -m pytest -q`
- [ ] 扫描新增 docs/report：
  - 不包含 SSH password；
  - 不包含 `mongodb://`、`postgresql://` 完整 URI；
  - 不包含 token/secret/password 明文。
- [ ] 确认 production service 未重启/未修改；如没有执行任何远端命令，也在文档中说明“阶段 14 无生产操作”。

Acceptance:

- 所有相关测试通过。
- 全量测试通过；如果失败，必须说明是否与阶段 14 相关并修复相关失败。
- app check 仍为 `local_pickle`。

任务 14.9：Gate 判定

Gate rules:

- `PASS`：
  - Stage13 P0/P1 复核为 0；
  - runtime policy 代码和文档完整；
  - `blocked_unknown=0`；
  - mirror-write tests 和默认全量测试通过；
  - 无生产 forbidden action；
  - 可进入阶段 15：授权后的 production controlled mirror-write one-off rehearsal。
- `PARTIAL`：
  - 代码和文档基本完成；
  - 仍有非阻塞验证缺口，例如本机没有 disposable PostgreSQL 工具导致真实 test DB smoke skip；
  - 无 `blocked_unknown`；
  - 不得进入生产启用，只能进入补验证或授权前准备。
- `BLOCKED`：
  - Stage13 P0/P1 回归；
  - runtime policy 出现 `blocked_unknown > 0`；
  - 发现需要 schema migration 或生产写入但未授权；
  - 测试失败且与阶段 14 相关；
  - 任何 forbidden action 被需要或发生。

最终输出必须包含：

1. 阶段 14 Gate。
2. runtime policy artifact path。
3. 阶段 14 文档 path。
4. 修改了哪些代码/tests/docs。
5. 哪些 job/alert 需要 mirror-write，哪些可重建/清理/保留。
6. 是否执行了任何生产命令；如果执行，说明只读范围和服务状态。
7. 测试结果。
8. 是否可以进入阶段 15。
```
```
