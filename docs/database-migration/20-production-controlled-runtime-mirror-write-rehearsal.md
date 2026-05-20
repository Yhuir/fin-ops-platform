# 阶段 20：Production controlled runtime mirror-write rehearsal

执行时间：2026-05-20

Gate：`EXECUTE_PASS_REQUIRES_POST_EXECUTE_REVIEW`

## 阶段边界

- 本阶段目标是执行 production controlled runtime mirror-write rehearsal 的前置检查、dry-run 和用户单独授权后的 execute。
- 本阶段先执行 dry-run；execute 仅在用户单独授权后执行。
- 本阶段 execute 只写 production PostgreSQL 授权范围：`job.background_jobs`、`audit.app_health_alerts`、`app.app_settings[state:background_jobs,state:app_health_alerts]`。
- 本阶段没有写 app Mongo `fin_ops_platform_app`。
- 本阶段没有读取、写入或触碰 OA Mongo `form_data_db.form_data`。
- 本阶段没有修改或重启 production `fin-ops.service`。
- 本阶段没有切换 read/write backend，没有启用 dual-write、mirror-write 或 cutover flag。

## Prompt

- `docs/database-migration/prompts/20-production-controlled-runtime-mirror-write-rehearsal.prompt.md`

## Local verification

Command：

```bash
PYTHONPATH=backend/src pytest -q \
  tests/test_runtime_state_policy.py \
  tests/test_stage15_runtime_tools.py \
  tests/test_shadow_read_rehearsal.py
```

Result：

```text
35 passed, 20 subtests passed
```

## Latest same-run read-only gate

在执行 dry-run 前已完成一次生产只读 gate：

- shadow-read artifact：`docs/database-migration/reports/stage20-preflight-20260520210456.shadow-read.json`
- runtime-policy artifact：`docs/database-migration/reports/stage20-preflight-20260520210456.runtime-policy.json`

Result：

| Check | Result |
| --- | --- |
| shadow-read gate | `PARTIAL` |
| shadow-read P0/P1/P2 | `0/0/11` |
| primary errors | `0` |
| shadow errors | `0` |
| runtime-policy gate | `PASS` |
| `blocked_unknown_count` | `0` |
| `background_jobs` classification | `cleanup_candidate=11`, `rebuildable=114`, `retention_only=23` |
| `app_health_alerts` classification | `retention_only=11` |

该结果符合阶段 19A 的 runtime P2 接受策略：剩余 11 条 `background_jobs` 是 shadow-only terminal `cleanup_candidate`，不是 active/attention runtime。

## Production dependency check

Run id：

- `stage20-mirror-dryrun-20260520211501`

Artifact：

- `docs/database-migration/reports/stage20-mirror-dryrun-20260520211501.blocked-summary.json`

Service state：

| Field | Value |
| --- | --- |
| `MainPID` | `452671` |
| `ExecMainStartTimestamp` | `Wed 2026-05-20 16:07:52 CST` |
| `WorkingDirectory` | `/opt/fin-ops/current` |
| `ActiveState` | `active` |
| `SubState` | `running` |

Production tool availability：

| Tool/import | Result |
| --- | --- |
| `fin_ops_platform.tools.run_shadow_read_rehearsal` | `OK` |
| `fin_ops_platform.tools.run_runtime_state_policy_preflight` | `OK` |
| `fin_ops_platform.tools.run_controlled_mirror_write_rehearsal` | `OK` |
| `psycopg` | `FAIL: ModuleNotFoundError` |
| `psql` | `/usr/bin/psql` |
| `pg_dump` | `/usr/bin/pg_dump` |

## Blocker

`run_controlled_mirror_write_rehearsal` 的 `postgres` mirror backend 使用 `PostgresStateStore` / `PostgresConnection`，即使 `--dry-run` 也会构造 mirror store 并读取 target counts/runtime policy，因此 production runner 需要 `psycopg`。

当前 `/opt/fin-ops/venv` 无法 import `psycopg`。阶段 20 因此在 controlled mirror-write dry-run 前停止，未执行 dry-run，也未执行任何 production PostgreSQL 写入。

## Recommended user action

已按用户授权采用临时 one-off dependency strategy 继续执行 dry-run；本节保留此前 blocker 的处理背景。

采用策略：

1. 在服务器 `/tmp/stage20-mirror-dryrun-deps-20260520213647/venv` 创建临时 virtualenv。
2. 只在临时 venv 安装 `psycopg[binary]`。
3. 使用 `/tmp/stage19A-production-retry-20260520202738/backend/src` 临时代码执行 one-off runner。
4. PostgreSQL native mirror store 使用 Unix socket DSN，由 OS 用户 `postgres` 运行 dry-run；未写入任何业务表。
5. 不修改 `/opt/fin-ops/current`。
6. 不修改 `/opt/fin-ops/venv`。
7. 不重启 `fin-ops.service`。

## Authorized temp dependency dry-run

Run id：

- `stage20-mirror-dryrun-deps-20260520213647`

Artifacts：

- `docs/database-migration/reports/stage20-mirror-dryrun-deps-20260520213647.dependency-imports.txt`
- `docs/database-migration/reports/stage20-mirror-dryrun-deps-20260520213647.shadow-read.json`
- `docs/database-migration/reports/stage20-mirror-dryrun-deps-20260520213647.runtime-policy.json`
- `docs/database-migration/reports/stage20-mirror-dryrun-deps-20260520213647.mirror-write-dry-run.json`
- `docs/database-migration/reports/stage20-mirror-dryrun-deps-20260520213647.stage20-summary.json`
- `docs/database-migration/reports/stage20-mirror-dryrun-deps-20260520213647.service-before.txt`
- `docs/database-migration/reports/stage20-mirror-dryrun-deps-20260520213647.service-after.txt`

Dependency result：

| Import | Result |
| --- | --- |
| `psycopg` | `OK` from temp venv |
| `run_shadow_read_rehearsal` | `OK` from `/tmp/stage19A-production-retry-20260520202738/backend/src` |
| `run_runtime_state_policy_preflight` | `OK` from `/tmp/stage19A-production-retry-20260520202738/backend/src` |
| `run_controlled_mirror_write_rehearsal` | `OK` from `/tmp/stage19A-production-retry-20260520202738/backend/src` |

Same-run read-only gate：

| Check | Result |
| --- | --- |
| shadow-read gate | `PARTIAL` |
| shadow-read P0/P1/P2 | `0/0/11` |
| primary errors | `0` |
| shadow errors | `0` |
| mismatched domains | `1` (`background_jobs`) |
| runtime-policy gate | `PASS` |
| `blocked_unknown_count` | `0` |
| runtime classification | `cleanup_candidate=11`, `rebuildable=114`, `retention_only=34` |

Controlled mirror-write dry-run：

| Check | Result |
| --- | --- |
| dry-run gate | `DRY_RUN_PASS` |
| wrapper gate | `DRY_RUN_PASS_REQUIRES_EXECUTE_AUTHORIZATION` |
| mode | `dry_run` |
| `executed` | `false` |
| `plan.bound_status` | `pass` |
| planned `background_jobs` | `137` / max `5000` |
| planned `app_health_alerts` | `11` / max `200` |
| planned runtime settings rows | `2` / max `2` |
| `policy_summary.blocked_unknown_count` | `0` |
| target tables | `job.background_jobs`, `audit.app_health_alerts`, `app.app_settings[state:background_jobs,state:app_health_alerts]` |

Target counts did not change:

| Target | Before | After |
| --- | ---: | ---: |
| `job.background_jobs` | `148` | `148` |
| `audit.app_health_alerts` | `1` | `1` |
| `app.app_settings.runtime_state` | `0` | `0` |

Service state before/after had no diff:

| Field | Value |
| --- | --- |
| `MainPID` | `452671` |
| `ExecMainStartTimestamp` | `Wed 2026-05-20 16:07:52 CST` |
| `WorkingDirectory` | `/opt/fin-ops/current` |
| `ActiveState` | `active` |
| `SubState` | `running` |

## Execution boundary for next step

阶段 20 已完成到 dry-run。下一步如果要真正执行 runtime mirror-write，必须由用户另行授权，且授权范围应明确限制为：

- 允许写 production PostgreSQL：
  - `job.background_jobs`
  - `audit.app_health_alerts`
  - `app.app_settings` 中 `settings_key in ('state:background_jobs', 'state:app_health_alerts')` 的行
- 仍然禁止写 app Mongo。
- 仍然禁止读取、写入或触碰 OA Mongo `form_data_db.form_data`。
- 仍然禁止修改 `/opt/fin-ops/current`。
- 仍然禁止修改 `/opt/fin-ops/venv`。
- 仍然禁止重启 `fin-ops.service`。
- execute 前必须重新跑 same-run production read-only shadow-read 和 runtime policy classification；若出现 P0/P1/read error/`blocked_unknown`，停止执行。

## Authorized execute

用户已单独授权阶段 20 controlled runtime mirror-write execute，授权范围限制为：

- `job.background_jobs`
- `audit.app_health_alerts`
- `app.app_settings` 中 `settings_key in ('state:background_jobs', 'state:app_health_alerts')` 的行

### Blocked execute attempt

Run id：

- `stage20-mirror-execute-20260520224717`

结果：

- same-run read-only gate 通过：P0=`0`，P1=`0`，read errors=`0`，runtime policy `PASS`，`blocked_unknown_count=0`。
- 在目标表备份阶段停止，原因是 `postgres` 用户无法写入备份目录。
- 未执行 `--execute`。
- 未写 production PostgreSQL。
- 未写 app Mongo。
- 未触碰 OA Mongo `form_data_db.form_data`。
- 未修改或重启 `fin-ops.service`。

### Successful execute

Run id：

- `stage20-mirror-execute-20260520225530`

Artifacts：

- `docs/database-migration/reports/stage20-mirror-execute-20260520225530.pre-shadow-read.json`
- `docs/database-migration/reports/stage20-mirror-execute-20260520225530.pre-runtime-policy.json`
- `docs/database-migration/reports/stage20-mirror-execute-20260520225530.mirror-write-execute.json`
- `docs/database-migration/reports/stage20-mirror-execute-20260520225530.post-shadow-read.json`
- `docs/database-migration/reports/stage20-mirror-execute-20260520225530.post-runtime-policy.json`
- `docs/database-migration/reports/stage20-mirror-execute-20260520225530.stage20-execute-summary.json`
- `docs/database-migration/reports/stage20-mirror-execute-20260520225530.runtime-targets.dump.sha256`
- `docs/database-migration/reports/stage20-mirror-execute-20260520225530.runtime-targets.dump.size`

Pre-execute read-only gate：

| Check | Result |
| --- | --- |
| shadow-read gate | `PARTIAL` |
| shadow-read P0/P1/P2 | `0/0/23` |
| primary errors | `0` |
| shadow errors | `0` |
| runtime-policy gate | `PASS` |
| `blocked_unknown_count` | `0` |
| runtime classification | `cleanup_candidate=11`, `rebuildable=114`, `retention_only=34` |

Backup：

| Field | Value |
| --- | --- |
| backup file | `/data/backups/postgres/stage20-mirror-execute-20260520225530/stage20-mirror-execute-20260520225530.runtime-targets.dump` |
| bytes | `95070` |
| sha256 | `ea6b5335d77a5e07bfee0908e2b022fe0fe89b4fdcde1428c429265ee6219911` |

Execute result：

| Check | Result |
| --- | --- |
| execute gate | `PASS` |
| wrapper gate | `EXECUTE_PASS_REQUIRES_POST_EXECUTE_REVIEW` |
| mode | `execute` |
| `executed` | `true` |
| `write_methods_called` | `save_background_jobs`, `save_app_health_alerts` |
| `policy_summary.blocked_unknown_count` | `0` |
| target tables | `job.background_jobs`, `audit.app_health_alerts`, `app.app_settings[state:background_jobs,state:app_health_alerts]` |

Target counts：

| Target | Before | After |
| --- | ---: | ---: |
| `job.background_jobs` | `148` | `148` |
| `audit.app_health_alerts` | `1` | `12` |
| `app.app_settings.runtime_state` | `0` | `2` |

Post-execute read-only validation：

| Check | Result |
| --- | --- |
| shadow-read gate | `PARTIAL` |
| shadow-read P0/P1/P2 | `0/0/12` |
| primary errors | `0` |
| shadow errors | `0` |
| mismatched domains | `1` (`app_health_alerts`) |
| runtime-policy gate | `PASS` |
| `blocked_unknown_count` | `0` |
| `background_jobs` classification | `rebuildable=114`, `retention_only=23` |
| `app_health_alerts` classification | `retention_only=11` |

Post-execute P2 说明：

- `background_jobs` 已 matched，P2 从 execute 前的 runtime shadow-only cleanup 差异清零。
- `app_health_alerts` 仍有 P2 value mismatch，集中在 retention-only alert 的 timestamp/message 字段。
- runtime policy 对 `app_health_alerts` 的 primary/shadow union count 均为 `11`，无 missing、无 `blocked_unknown`，分类为 `retention_only=11`。

Service state before/after had no diff：

| Field | Value |
| --- | --- |
| `MainPID` | `452671` |
| `ExecMainStartTimestamp` | `Wed 2026-05-20 16:07:52 CST` |
| `WorkingDirectory` | `/opt/fin-ops/current` |
| `ActiveState` | `active` |
| `SubState` | `running` |

## Gate

`EXECUTE_PASS_REQUIRES_POST_EXECUTE_REVIEW`

阶段 20 prompt 已生成，本地验证通过，production read-only gate 当前可接受，授权后的临时 dependency strategy 已完成正式 controlled runtime mirror-write dry-run。用户单独授权后已执行 controlled runtime mirror-write execute：`execute_gate=PASS`、`executed=true`、写入方法仅为 `save_background_jobs` 和 `save_app_health_alerts`，写入范围限制在授权 target tables。post-execute validation 无 P0/P1/read error/`blocked_unknown`，但仍保留 `app_health_alerts` retention-only P2，需要在后续切换前继续观察或清理。阶段 20 没有写 app Mongo、没有触碰 OA Mongo、没有修改或重启 service。
