# 阶段 07：Shadow / Dual-write / 生产切换和回滚

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for parallel work or `superpowers:executing-plans` for serial execution. 本阶段只在阶段 06 `PASS` 后执行，目标是把生产 app 自身数据事实源安全切换到 PostgreSQL，同时 OA Mongo 继续只读。

**Goal:** 通过 shadow read、受控 dual-write、差异监控、分步读切换和可回滚流程，让生产 app 使用 PostgreSQL 作为 app 数据主事实源。

**Architecture:** PostgreSQL 已完成 schema、backfill、reconciliation、真实测试库 integration 和 API smoke 后，生产切换不再做结构性大改。阶段 07 只增加运行时开关、shadow 比对、dual-write outbox/审计、切换 runbook、监控和回滚路径。切换过程必须可暂停、可回滚、可审计。

**Tech Stack:** Python 3, PostgreSQL 16, existing app backend, existing Mongo app state read path, `psycopg`, systemd/deploy scripts, smoke tests, structured logs.

---

## 当前生产切换状态

截至 `stage25-read-switch-execute-20260521005929`：

- Production `fin-ops.service` 已通过 systemd drop-in 切到 PostgreSQL mode。
- Live `/health` 返回 `storage.backend=postgres`、`storage.mode=postgres`、`postgres_schema_version=8`。
- Process env 已确认：
  - `FIN_OPS_APP_STORAGE_BACKEND=postgres`
  - `FIN_OPS_APP_READ_BACKEND=postgres`
  - `FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary`
  - `PYTHONPATH=/opt/fin-ops/releases/stage25B-workbench-candidate-snapshot-repair-20260521004245/src/backend/src`
- Post-switch full native `PostgresStateStore` shadow-read：`P0=0`、`P1=0`、read errors `0`，仅保留已接受的 `app_health_alerts` retention-only `P2=12`。
- Post-switch runtime policy：`PASS`，`blocked_unknown_count=0`。
- 回滚 artifact 位于服务器 `/opt/fin-ops/releases/stage25-read-switch-execute-20260521005929/backups/`。

当前仍处于 observation / rollback window。不得 contract/drop app Mongo；如需回滚，优先恢复 service drop-in，不得用旧 app Mongo 全量覆盖 PostgreSQL。

## 前置条件

- 阶段 00-04 gate 均为 `PASS`。
- 阶段 05 本地默认模式、Postgres 接入骨架和 contract tests 已完成。
- 阶段 06 gate 必须为 `PASS`：
  - real PostgreSQL test DB integration 通过。
  - Postgres mode API smoke 通过。
  - 关键 repository 写路径已写正式表并具备事务测试。
  - 生产只读 smoke 通过。
- 生产 app Mongo 仍可作为回滚读源。
- 已有最近可恢复 app Mongo backup 和 PostgreSQL backup。

## 阶段边界

允许：

- 增加 shadow read 比对逻辑。
- 增加 dual-write 或 controlled mirror write。
- 增加生产切换配置、readiness、health、metrics。
- 在生产 PostgreSQL 写 app 自身数据。
- 读取 app Mongo 作为 shadow/migration 对比源。
- 读取 OA Mongo 作为只读源。

禁止：

- 写 OA Mongo `form_data_db.form_data`。
- 在切换后用旧 app Mongo 全量覆盖 PostgreSQL。
- 无备份、无 smoke、无回滚命令时切生产。
- 一次性永久关闭 Mongo 回滚路径。
- 静默忽略 shadow mismatch。
- 在业务高峰执行不可逆 schema/data 操作。

## 切换原则

- PostgreSQL 成为 app 数据事实源后，只能通过增量补偿修复差异，不能用 Mongo dump 覆盖。
- 每一步切换都必须有：
  - 前置检查。
  - 执行命令。
  - 验证命令。
  - 回滚命令。
  - 停止条件。
- 生产配置必须以 feature flag 控制，避免代码发布即切换。
- 默认读写路径仍必须支持 local/Mongo fallback，直到 07 完成并观察期结束。

## 建议新增/修改文件

| 路径 | 动作 | 责任 |
| --- | --- | --- |
| `backend/src/fin_ops_platform/services/state_store_factory.py` | Modify | 支持 `shadow`、`dual` 或显式 read/write backend 配置。 |
| `backend/src/fin_ops_platform/services/dual_state_store.py` | Create | Mongo/Postgres dual-write wrapper 或 controlled mirror write。 |
| `backend/src/fin_ops_platform/services/shadow_state_store.py` | Create | PostgreSQL primary read + Mongo shadow read 比对，或 Mongo primary + PostgreSQL shadow read。 |
| `backend/src/fin_ops_platform/services/state_store_diff.py` | Create | state snapshot/domain payload diff、忽略字段规则、差异摘要。 |
| `backend/src/fin_ops_platform/services/postgres_cutover_monitor.py` | Create | counts、schema version、lag、mismatch counters。 |
| `backend/src/fin_ops_platform/tools/verify_postgres_cutover.py` | Create | 生产切换前后只读验证脚本。 |
| `backend/src/fin_ops_platform/tools/reconcile_runtime_state.py` | Create | 切换期间 runtime state 差异对账/补偿。 |
| `deploy/oa/README.md` 或 operations doc | Modify | 增加生产配置和回滚 runbook。 |
| `docs/database-migration/07-shadow-dualwrite-production-cutover.md` | Modify | 执行记录和 gate。 |
| `tests/test_shadow_state_store.py` | Create | shadow mismatch、忽略字段、错误边界。 |
| `tests/test_dual_state_store.py` | Create | dual write 成功、局部失败、回滚/补偿。 |
| `tests/test_cutover_runbook.py` | Create | runbook helper、redaction、安全 guard。 |

## 配置设计

建议最终配置：

| 变量 | 值 | 阶段 |
| --- | --- | --- |
| `FIN_OPS_APP_STORAGE_BACKEND` | `local_pickle` / `mongo` / `postgres` / `dual` | 写路径事实源。 |
| `FIN_OPS_APP_READ_BACKEND` | `storage` / `mongo` / `postgres` / `shadow` | 读路径控制。 |
| `FIN_OPS_SHADOW_COMPARE_ENABLED` | `0` / `1` | 是否执行 shadow comparison。 |
| `FIN_OPS_SHADOW_COMPARE_SAMPLE_RATE` | `0.0`-`1.0` | 比对采样率，初期可 1.0。 |
| `FIN_OPS_DUAL_WRITE_STRICT` | `0` / `1` | mirror write 失败是否阻断主写。 |
| `FIN_OPS_POSTGRES_CUTOVER_PHASE` | `shadow_mongo_primary` / `dual_write` / `postgres_primary` / `rollback` | 生产阶段标识。 |
| `FIN_OPS_CUTOVER_RUN_ID` | text | 当前切换批次 id。 |

禁止输出完整：

- PostgreSQL URI。
- Mongo URI。
- OA token。
- DB password。
- 用户凭证。

## 分阶段执行

### 任务 7.1：切换前冻结点和备份

**Files:**

- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md`
- Modify/Create: operations runbook。

**Steps:**

- [ ] 记录当前 git commit、branch、部署版本。
- [ ] 生成 production PostgreSQL backup。
- [ ] 生成 app Mongo backup。
- [ ] 记录 backup path、sha256、时间、操作者。
- [ ] 只读检查 OA Mongo 配置，确认不会写 OA。
- [ ] 只读查询 PostgreSQL schema version 和核心 counts。
- [ ] 运行默认生产 app health/readiness。

**Acceptance:**

- 两端 backup 均可定位、校验。
- 回滚数据源存在。
- 未修改生产服务。

### 任务 7.2：Shadow read，Mongo primary / PostgreSQL shadow

**Goal:** 生产仍以现有 app Mongo/local 路径为主，后台对 PostgreSQL 读取结果做 diff。

**Files:**

- Create: `backend/src/fin_ops_platform/services/shadow_state_store.py`
- Create: `backend/src/fin_ops_platform/services/state_store_diff.py`
- Test: `tests/test_shadow_state_store.py`

**Steps:**

- [ ] 定义 shadow compare interface。
- [ ] 对核心 domains 实现 diff：
  - app settings
  - imports/invoices/bank transactions
  - import files/file refs
  - workbench pair relations
  - no OA batches
  - categories
  - read models/search
  - tax/ETC/jobs/health
- [ ] 定义忽略字段：
  - updated_at/generated_at 允许小范围差异。
  - internal UUID 不参与 DTO 等价。
  - raw payload 中 migration metadata 不参与业务等价。
- [ ] shadow mismatch 写结构化日志和 metrics，不阻断用户请求。
- [ ] 增加 `/health` 或 readiness 中的 shadow summary。
- [ ] 测试 mismatch redaction。

**Acceptance:**

- shadow mode 可在生产只读运行。
- mismatch 可定位到 domain/key/path。
- 无 URI/密码/token 泄漏。

### 任务 7.3：Shadow read，PostgreSQL primary dry run

**Goal:** 在不改变用户可见事实源的前提下，验证 PostgreSQL primary read 是否能满足 app 初始化和关键 read API。

**Files:**

- Modify: `backend/src/fin_ops_platform/services/state_store_factory.py`
- Test: `tests/test_app_postgres_mode_integration.py`

**Steps:**

- [ ] 在 staging 或单独进程中设置 `FIN_OPS_APP_STORAGE_BACKEND=postgres`。
- [ ] 保持生产主服务不变。
- [ ] 执行 app `--check`。
- [ ] 执行 read-only API smoke。
- [ ] 对比 smoke DTO 与当前生产响应。
- [ ] 记录 mismatch。

**Acceptance:**

- PostgreSQL primary read 的 dry-run app 能启动。
- 关键 read API 返回 200 且 DTO 符合现有契约。

### 任务 7.4：Dual-write / controlled mirror write

**Goal:** 主写仍按当前生产路径成功，PostgreSQL mirror write 同步记录 runtime 新增/变更数据。

**Files:**

- Create: `backend/src/fin_ops_platform/services/dual_state_store.py`
- Create: `backend/src/fin_ops_platform/tools/reconcile_runtime_state.py`
- Test: `tests/test_dual_state_store.py`

**Steps:**

- [ ] 定义 primary store 和 mirror store。
- [ ] 实现 mirror write 的 idempotency key。
- [ ] 实现 dual write 结果记录：
  - success
  - mirror_failed
  - primary_failed
  - retry_pending
- [ ] 非 strict 模式：primary 成功、mirror 失败时用户请求仍可成功，但必须记录 retry/alert。
- [ ] strict 模式：mirror 失败阻断写入，仅用于切换前短窗口验证。
- [ ] 增加 mirror write retry 工具。
- [ ] 增加 runtime diff/reconcile 工具。
- [ ] 测试 mirror failure 不破坏 primary。
- [ ] 测试 retry 后幂等。

**Acceptance:**

- dual write 能在生产观测窗口运行。
- mirror failure 可发现、可重试、可审计。
- 不写 OA Mongo。

### 任务 7.5：生产切 PostgreSQL primary

**Goal:** 将 app 主读写切到 PostgreSQL。

**Files:**

- Modify: deployment env/runbook。
- Modify: `docs/database-migration/07-shadow-dualwrite-production-cutover.md`

**Steps:**

- [ ] 确认 7.1-7.4 均通过。
- [ ] 冻结短时间写入或进入低流量窗口。
- [ ] 执行最后一次 runtime reconciliation。
- [ ] 备份 PostgreSQL。
- [ ] 设置：
  - `FIN_OPS_APP_STORAGE_BACKEND=postgres`
  - `FIN_OPS_APP_READ_BACKEND=postgres`
  - `FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary`
- [ ] 重启/滚动重启服务。
- [ ] 执行 readiness。
- [ ] 执行关键 API smoke。
- [ ] 检查 logs/metrics/mismatch。
- [ ] 解除写入冻结。

**Acceptance:**

- 生产 app 主读写为 PostgreSQL。
- OA Mongo 仍只读。
- API smoke 全部通过。
- 无新增 mismatch 或 P0/P1 error。

### 任务 7.6：回滚流程

**Goal:** 在切换失败时恢复到切换前稳定状态，且不丢失已确认业务变更。

**Files:**

- Create/Modify: operations rollback runbook。
- Test: `tests/test_cutover_runbook.py`

**Rollback paths:**

1. 配置回滚：
   - 恢复 `FIN_OPS_APP_STORAGE_BACKEND=mongo` 或原默认配置。
   - 恢复 `FIN_OPS_APP_READ_BACKEND=storage`。
   - 重启服务。
2. 数据补偿：
   - 如果切换期间 PostgreSQL primary 接收了新写入，必须导出 runtime delta。
   - 由补偿脚本决定是否回写旧 app Mongo 或人工重放。
   - 禁止用旧 Mongo 全量覆盖 PostgreSQL。
3. PostgreSQL 回滚：
   - 仅在 schema/data corruption 时使用备份恢复到新库或新 schema。
   - 不直接破坏当前生产库，除非有明确批准。

**Acceptance:**

- 回滚命令可执行。
- 回滚后 app readiness/API smoke 通过。
- 切换窗口内新增写入有清单和处理状态。

### 任务 7.7：观察期和收尾

**Goal:** 切换后持续验证，最后降低对旧 app Mongo 的依赖。

**Steps:**

- [ ] 观察 24-72 小时：
  - error rate
  - Postgres connection errors
  - slow queries
  - mismatch count
  - background jobs health
  - import/file retry
  - workbench/search freshness
- [ ] 每日执行 counts/reconciliation smoke。
- [ ] 保留 app Mongo read-only fallback 到观察期结束。
- [ ] 观察期结束后将 app Mongo 标记为 historical fallback。
- [ ] 更新 README、ARCHITECTURE、operations docs。
- [ ] 记录最终迁移完成报告。

**Acceptance:**

- 观察期无未解释 mismatch。
- 业务关键 API 正常。
- 回滚窗口、备份保留策略明确。
- 文档明确 PostgreSQL 为 app 数据事实源，OA Mongo 仍为 OA 只读源。

## 生产 smoke 清单

切换前：

```bash
python -m pytest -q
```

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

服务器：

```bash
ssh root@139.155.5.132 'systemctl status fin-ops.service --no-pager'
```

PostgreSQL counts：

```sql
select 'app.import_batches', count(*) from app.import_batches
union all select 'app.import_files', count(*) from app.import_files
union all select 'app.invoices', count(*) from app.invoices
union all select 'app.bank_transactions', count(*) from app.bank_transactions
union all select 'read_model.search_index_rows', count(*) from read_model.search_index_rows;
```

API smoke：

- `GET /health`
- `GET /api/session/me`
- `GET /api/workbench/settings`
- `GET /api/workbench?month=<known-month>`
- `GET /api/search?q=<known-keyword>`
- `GET /api/no-oa-bank-batches`
- `GET /api/background-jobs/active`
- `GET /api/tax-offset`
- `GET /api/etc/invoices`

## Gate

阶段 10 preflight 执行记录见 `10-shadow-dualwrite-cutover-preflight.md`。阶段 10 已完成 shadow diff、dual wrapper、factory guard 和 cutover preflight CLI，但没有执行生产 shadow-read 观测窗口、生产 dual-write 或 cutover。本文件仍作为后续生产演练和切换规划使用。

阶段 11 production shadow-read rehearsal 执行记录见 `11-production-shadow-read-rehearsal.md`。阶段 11 已完成本地 runner/CLI 和生产只读盘点，但生产服务器尚未部署阶段 10/11 代码，因此没有执行真实 production shadow-read rehearsal；进入 dual-write 前仍需先完成只读 rehearsal report。

阶段 12 production one-off shadow-read 执行记录见 `12-production-shadow-read-oneoff.md`。阶段 12 已真实执行 production rehearsal，report artifact 为 `reports/stage12-shadow-read-20260520142049.stage12.shadow-read.json`，但 Gate 为 `BLOCKED`：7/7 conservative domains mismatched，存在未解释 `P0=14`、`P1=8`。在这些 mismatch 被修复或可审计解释前，不能进入 controlled dual-write、mirror-write 或 production cutover。

阶段 13 production mismatch remediation 执行记录见 `13-shadow-mismatch-remediation-backfill-repair.md`。阶段 13 已清零 P0/P1，并通过 production PostgreSQL app-owned repair 让 5 个 conservative business domains matched；剩余 `background_jobs` 与 `app_health_alerts` 为 runtime P2。

阶段 14 runtime state policy 执行记录见 `14-runtime-state-policy-mirror-rehearsal.md`。阶段 14 已把 `background_jobs` 和 `app_health_alerts` 的 mirror-write、rebuildable、retention、cleanup、blocked_unknown 策略落到代码分类器、policy artifact 和测试。进入 controlled mirror-write 前仍需要用户单独授权阶段 15 production one-off rehearsal，且不能直接 cutover。

阶段 15 production controlled mirror-write one-off rehearsal 执行记录见 `15-production-controlled-mirror-write-rehearsal.md`。阶段 15 已完成 production read-only preflight 和 live runtime policy classification；runtime classification 无 `blocked_unknown`，但 read-only shadow-read 在 `workbench_pair_relations` 发现新的 `P0=5`，因此 Gate 为 `BLOCKED_CONSERVATIVE_P0`，没有执行 production mirror-write dry-run、backup、write 或 cutover。进入 mirror-write 前必须先修复或解释该 conservative P0，并解决 one-off runner 所需 `psycopg` 依赖策略。

阶段 15A workbench P0 remediation 执行记录见 `15A-workbench-p0-remediation.md`。阶段 15A 已在用户授权后完成 production PostgreSQL workbench repair，并在 post-main revalidation 后重新执行 repair；`workbench_pair_relations` conservative P0 已清零。后续阶段发现 main fresh export 与 production PostgreSQL repair rows 存在 transform natural-key 语义差异，因此进入阶段 19/19A。

阶段 19 fresh production import/reconcile 执行记录见 `19-main-production-fresh-import-reconcile.md`。阶段 19 已完成 fresh app Mongo export 和 production staging import，但 transform 在 `workbench_pair_relations.case_id` natural key 冲突处回滚，需要阶段 19A 修复 transform refresh/upsert 语义。

阶段 19A production transform natural-key remediation 执行记录见 `19A-production-transform-natural-key-remediation.md`。阶段 19A 已完成 production transform retry、reconcile、read-only shadow-read 和 runtime policy closure；conservative domains 无 P0/P1。剩余 `background_jobs` P2 已由 runtime policy 分类为 11 条 shadow-only terminal `cleanup_candidate`，作为已解释、可审计 runtime P2 接受，不阻断下一阶段规划或受控执行前置检查。进入任何执行型 cutover/mirror-write 阶段前仍必须重新运行 production read-only shadow-read 和 runtime policy classification；若出现 P0/P1/read error/`blocked_unknown`，必须停止。

阶段 20 production controlled runtime mirror-write rehearsal 执行记录见 `20-production-controlled-runtime-mirror-write-rehearsal.md`。阶段 20 prompt 已生成，本地 targeted tests 通过，并在用户授权后通过 `/tmp` 临时 virtualenv 安装 `psycopg[binary]`，完成 production same-run read-only gate、正式 `run_controlled_mirror_write_rehearsal --dry-run --mirror-backend postgres`，以及用户单独授权后的 controlled runtime mirror-write execute。execute Gate 为 `EXECUTE_PASS_REQUIRES_POST_EXECUTE_REVIEW`，`executed=true`，写入方法仅为 `save_background_jobs` 和 `save_app_health_alerts`，写入范围限制在 `job.background_jobs`、`audit.app_health_alerts`、`app.app_settings[state:background_jobs,state:app_health_alerts]`。post-execute validation 无 P0/P1/read error/`blocked_unknown`，但 `app_health_alerts` 仍有 retention-only P2。阶段 20 没有写 app Mongo、没有触碰 OA Mongo、没有修改或重启 service。继续 read switch 或 cutover 前必须重新执行 production read-only shadow-read 与 runtime policy classification。

阶段 21 pre-cutover read-only validation 执行记录见 `21-precutover-readonly-p2-closure.md`。阶段 21 在阶段 20 execute 后重新执行 production read-only shadow-read 和 runtime policy classification；当前 conservative domains 无 P0/P1/read error，runtime policy 无 `blocked_unknown`。唯一剩余差异为 `app_health_alerts` retention-only P2，primary/shadow 均为 11 条 alert，已作为 runtime/retention state 明确接受。阶段 21 没有执行 read switch、cutover 或任何生产写入。进入任何执行型 read switch、cutover 或 service 配置变更前仍必须再次重新执行 production read-only shadow-read 与 runtime policy classification。

阶段 22 read switch / cutover planning 执行记录见 `22-production-read-switch-cutover-plan.md`。阶段 22 没有执行 production service 配置变更、release deploy、venv 修改、PostgreSQL role/secret 修改、service restart 或 read switch。阶段 22 明确当前不能直接 cutover：必须先完成 release readiness、production runtime dependency、service 可用 PostgreSQL DSN/最小权限 role、same-run read-only gate、backup/freeze 和 no-traffic PostgreSQL mode smoke。正式执行建议拆为阶段 23 release/runtime credential preparation 和阶段 24 controlled production read switch。

阶段 23 release/runtime credential preparation 执行记录见 `23-release-runtime-credential-prep.md`。阶段 23 已创建独立 release candidate `/opt/fin-ops/releases/stage23-release-runtime-20260520233335`，使用 release candidate venv 安装 `backend/requirements.txt`，准备 production PostgreSQL runtime role `fin_ops_app_runtime` 和 root-only credential file `/root/fin_ops_stage23_postgres_runtime.env`，并通过 no-traffic PostgreSQL mode `--check`。阶段 23 期间修复了 PostgreSQL repository 读取 ETC formal table 时误读历史 `current_state:*` 聚合快照行的问题。Gate 为 `PASS_RELEASE_RUNTIME_CREDENTIAL_READY_REQUIRES_READ_SWITCH_AUTHORIZATION`。本阶段没有修改 `/opt/fin-ops/current`、没有修改 `/opt/fin-ops/venv`、没有修改 live systemd/env、没有重启 service、没有 read switch、没有写 app Mongo、没有触碰 OA Mongo。进入阶段 24 前仍需 same-run production read-only shadow-read、runtime policy classification 和 no-traffic PostgreSQL check；任何 production service 配置变更或 restart 都需要用户单独授权。

阶段 24 controlled production read switch rehearsal 执行记录见 `24-controlled-read-switch-rehearsal.md`。阶段 24 使用阶段 23 release candidate 与 `fin_ops_app_runtime` credential 完成 same-run production read-only shadow-read、runtime policy classification、no-traffic PostgreSQL mode check 和 read-only cutover preflight。Gate 为 `PASS_READ_SWITCH_REHEARSAL_READY_REQUIRES_EXECUTE_AUTHORIZATION`：shadow-read 无 P0/P1/read error，仅 `app_health_alerts` 保留已解释 retention-only P2；runtime policy `PASS` 且 `blocked_unknown=0`；PostgreSQL mode check `ready`；cutover preflight `pass`。本阶段没有修改 `/opt/fin-ops/current`、没有修改 `/opt/fin-ops/venv`、没有修改 live systemd/env、没有重启 service、没有 read switch、没有写 app Mongo、没有触碰 OA Mongo。下一步正式 read switch execute 必须由用户单独授权，并且执行前仍要重新跑 same-run gates。

阶段 25 controlled production read switch execute 执行记录见 `25-controlled-read-switch-execute.md`。用户已授权进入 execute，但执行前新增了更接近 live runtime 的 full-domain `PostgresStateStore` shadow-read；该 gate 发现 `P0=20`、`P1=77`、`P2=3`，因此 Gate 为 `BLOCKED_FULL_POSTGRES_STORE_SHADOW_READ`。阶段 25 未修改 `/opt/fin-ops/current`、未修改 `/opt/fin-ops/venv`、未修改 live systemd/env、未写 drop-in、未执行 `daemon-reload`、未重启 service、未 read switch、未写 production PostgreSQL business/runtime data、未写 app Mongo、未触碰 OA Mongo。下一步必须先做阶段 25A actual PostgreSQL store shadow remediation，修复真实 runtime backend 的 P0/P1 后才能重新申请 execute 授权。

阶段 25A/25B 执行记录见 `25A-actual-postgres-store-shadow-remediation.md` 和 `25B-workbench-candidate-runtime-snapshot-repair.md`。阶段 25A 修复真实 `PostgresStateStore` runtime backend 的代码层 shape 差异；阶段 25B 在用户授权后仅写 production PostgreSQL `app.app_settings` 中 `settings_key='state:workbench_candidate_matches'` 的一行，补齐 workbench candidate runtime snapshot。25B 后 full-domain native `PostgresStateStore` shadow-read 已无 P0/P1/read error，仅保留阶段 21 已接受的 `app_health_alerts` retention-only P2；conservative psql JSON shadow-read PASS；runtime policy PASS 且 `blocked_unknown=0`；no-traffic PostgreSQL mode check ready；read-only cutover preflight pass。阶段 25B 未修改或重启 production service，未写 app Mongo，未触碰 OA Mongo。可以重新申请阶段 25 controlled read switch execute 授权；执行前仍必须 same-run 重跑 gates。

`PASS` 条件：

- 07.1 backup/freeze point 完成。
- shadow read 运行并无阻断 mismatch。
- dual-write 观测窗口通过，mirror failure 可审计且无未处理 backlog。
- PostgreSQL primary production switch 成功。
- 切换后 smoke 全部通过。
- 回滚 runbook 已验证。
- 观察期无未解释 P0/P1。
- 文档更新 PostgreSQL 为 app 数据事实源。
- OA Mongo 仍只读。

`BLOCKED` 条件：

- 阶段 06 未 PASS。
- 无可用备份或备份校验失败。
- shadow mismatch 无法解释。
- dual-write backlog 无法清零。
- PostgreSQL primary read/write smoke 不通过。
- 回滚路径不可执行。
- 任一流程需要写 OA Mongo。

## 阶段产物

- shadow read/diff 工具。
- dual-write/mirror-write 工具。
- production cutover runbook。
- rollback runbook。
- production smoke 和观察期报告。
- 最终迁移完成报告。
