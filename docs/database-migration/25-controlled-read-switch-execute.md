# 阶段 25：Controlled Production Read Switch Execute

## 目标

阶段 25 的目标是在用户授权后进入 controlled production read switch execute：修改 production service 配置，使 live service 使用已修复的 release candidate、PostgreSQL runtime credential 和 PostgreSQL storage backend，并在 restart 后完成 smoke 与 rollback guard。

2026-05-21 重新执行阶段 25 时，阶段 25A/25B 的 blocker 已修复。same-run gates 通过后，production `fin-ops.service` 已切到 PostgreSQL read/write mode；OA Mongo 仍仅作为 OA 只读来源，未读取、写入或触碰 `form_data_db.form_data`。

## 授权范围

用户已回复“同意授权”，授权进入阶段 25。该授权允许在全部 gate 通过后执行：

- 修改 production service env/drop-in 或 release pointer。
- 使用 `/root/fin_ops_stage23_postgres_runtime.env` 作为 live service PostgreSQL credential source。
- 执行 `systemctl daemon-reload`。
- 执行 `systemctl restart fin-ops.service`。

但阶段 24 已要求：即使授权，执行前仍必须重新运行 same-run gates；只要出现 P0/P1/read error/`blocked_unknown`，必须停止。

## 执行 Prompt

阶段 25 Codex 执行 prompt：

- `prompts/25-controlled-read-switch-execute.prompt.md`

## 2026-05-21 重新执行结果

Run ID：

- `stage25-read-switch-execute-20260521005929`

Release / runtime：

- Release code：`/opt/fin-ops/releases/stage25B-workbench-candidate-snapshot-repair-20260521004245/src`
- Python venv：`/opt/fin-ops/releases/stage23-release-runtime-20260520233335/venv`
- Runtime credential file：`/root/fin_ops_stage23_postgres_runtime.env`
- Systemd drop-in：`/etc/systemd/system/fin-ops.service.d/20-postgres-read-switch.conf`

执行前 same-run gates：

| Gate | 结果 |
| --- | --- |
| Full native `PostgresStateStore` shadow-read | `PARTIAL`，`P0=0`、`P1=0`、read errors `0`、仅 `P2=12` |
| Conservative `postgres_psql_json` shadow-read | `PARTIAL`，`P0=0`、`P1=0`、read errors `0`、仅 `P2=12` |
| Runtime policy classification | `PASS`，`blocked_unknown_count=0` |
| No-traffic PostgreSQL mode check | `ready`，`storage.backend=postgres` |
| Cutover preflight | `pass`，schema version `0008`，`no_production_writes=enforced` |

执行动作：

- 写入新的 systemd drop-in `20-postgres-read-switch.conf`。
- 执行 `systemctl daemon-reload`。
- 执行 `systemctl restart fin-ops.service`。
- 第一次 restart 后发现 live process 的 `PYTHONPATH` 仍被原 env file 覆盖为 `/opt/fin-ops/current/backend/src`，导致 health 仍显示 `mongo_only`。该次 service 仍为 active，未造成 PostgreSQL cutover 成功假象。
- 修正 drop-in：在 `ExecStart=/usr/bin/env ...` 中显式设置 `PYTHONPATH`、`FIN_OPS_APP_STORAGE_BACKEND=postgres`、`FIN_OPS_APP_READ_BACKEND=postgres`、`FIN_OPS_POSTGRES_CUTOVER_PHASE=postgres_primary` 和 `FIN_OPS_DATA_DIR=/opt/fin-ops/data`。
- 再次执行 `systemctl daemon-reload` 和 `systemctl restart fin-ops.service`。

最终 live service 状态：

| 项 | 值 |
| --- | --- |
| `systemctl is-active fin-ops.service` | `active` |
| `/health.status` | `ready` |
| `/health.storage.backend` | `postgres` |
| `/health.storage.mode` | `postgres` |
| `/health.storage.postgres_database` | `fin_ops` |
| `/health.storage.postgres_schema_version` | `8` |
| `/health.storage.postgres_user` | `fin_ops_app_runtime` |
| Process `FIN_OPS_APP_STORAGE_BACKEND` | `postgres` |
| Process `FIN_OPS_APP_READ_BACKEND` | `postgres` |
| Process `FIN_OPS_POSTGRES_CUTOVER_PHASE` | `postgres_primary` |
| Process `PYTHONPATH` | `/opt/fin-ops/releases/stage25B-workbench-candidate-snapshot-repair-20260521004245/src/backend/src` |

HTTP smoke：

| Endpoint | HTTP |
| --- | --- |
| `/health` | `200` |
| `/api/session/me` | `401` |
| `/api/workbench/settings` | `401` |
| `/api/background-jobs/active` | `401` |
| `/api/etc/invoices` | `401` |

`401` 表示未带登录凭证的接口仍被鉴权保护，不是 service 5xx。

Post-switch validation：

| Gate | 结果 |
| --- | --- |
| Full native `PostgresStateStore` shadow-read | `PARTIAL`，`P0=0`、`P1=0`、read errors `0`、仅 `P2=12` |
| Runtime policy classification | `PASS`，`blocked_unknown_count=0` |

本阶段没有写 app Mongo，没有读取、写入或触碰 OA Mongo `form_data_db.form_data`。本阶段写入的 production 变更仅限 production service systemd drop-in/restart；业务数据写入由 live service 后续按 PostgreSQL runtime mode 执行。

回滚 artifact：

- Remote backup dir：`/opt/fin-ops/releases/stage25-read-switch-execute-20260521005929/backups`
- Remote rollback script：`/opt/fin-ops/releases/stage25-read-switch-execute-20260521005929/backups/stage25-read-switch-execute-20260521005929.rollback.sh`

主要报告：

- `reports/stage25-read-switch-execute-20260521005929.full-shadow-read-postgres.json`
- `reports/stage25-read-switch-execute-20260521005929.conservative-shadow-read.json`
- `reports/stage25-read-switch-execute-20260521005929.runtime-policy.json`
- `reports/stage25-read-switch-execute-20260521005929.postgres-mode-check.stdout.json`
- `reports/stage25-read-switch-execute-20260521005929.cutover-preflight.json`
- `reports/stage25-read-switch-execute-20260521005929.health-r2.json`
- `reports/stage25-read-switch-execute-20260521005929.post-switch-full-shadow-read-postgres.json`
- `reports/stage25-read-switch-execute-20260521005929.post-switch-runtime-policy.json`

## 执行前检查

### Production Service Metadata

阶段 25 停止后再次确认 production service 未变化：

- `MainPID=452671`
- `ExecMainStartTimestamp=Wed 2026-05-20 16:07:52 CST`
- `ExecStart=/opt/fin-ops/venv/bin/python -m fin_ops_platform.app.main --host 127.0.0.1 --port 18001`
- `WorkingDirectory=/opt/fin-ops/current`
- `User=root`
- `ActiveState=active`
- `SubState=running`

### Conservative psql JSON Shadow-read 说明

阶段 24 已证明保守 8 个 domain 在 `postgres_psql_json` shadow backend 下可通过 read switch rehearsal gate；但阶段 25 在正式修改 service 前增加了更接近 live runtime 的真实 `PostgresStateStore` full-domain shadow-read。

该附加检查是必须的，因为 live service 切到 PostgreSQL 后使用的是 `PostgresStateStore`，不是 `PsqlShadowReadStore`。

## 首次执行 Blocker：Full-domain PostgresStateStore Shadow-read

Precheck Run ID：

- `stage25-full-shadow-postgres-precheck-20260520235831`

命令语义：

- Primary：app Mongo readonly `ApplicationStateStore`
- Shadow：真实 PostgreSQL `PostgresStateStore`
- Release：`/opt/fin-ops/releases/stage23-release-runtime-20260520233335`
- Credential：`/root/fin_ops_stage23_postgres_runtime.env`
- Guard：`FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`

结果：

- Gate：`BLOCKED`
- Total domains：`20`
- Compared domains：`20`
- Matched domains：`10`
- Mismatched domains：`10`
- Primary errors：`0`
- Shadow errors：`0`
- P0：`20`
- P1：`77`
- P2：`3`

受影响 domain：

- `workbench_pair_relations`：`P0=20`
- `turnover_ledger_extras`：`P1=2`
- `workbench_read_models`：`P1=6`
- `workbench_candidate_matches`：`P1=20`
- `cost_statistics_read_models`：`P1=20`
- `tax_offset_read_models`：`P1=1`
- `etc_state`：`P1=20`
- `etc_reconciliation_state`：`P1=4`
- `historical_etc_repair_parsed_seeds`：`P2=3`
- `historical_etc_repair_states`：`P1=4`

报告：

- `reports/stage25-full-shadow-postgres-precheck-20260520235831.stage25.full-shadow-read-postgres.json`
- `reports/stage25-full-shadow-postgres-precheck-20260520235831.stage25.full-shadow-read-postgres.stdout.json`
- `reports/stage25-full-shadow-postgres-precheck-20260520235831.stage25.full-shadow-read-postgres.stderr.txt`

## 首次执行为什么停止

阶段 24 的 `postgres_psql_json` rehearsal 验证的是受控保守 domain 和 SQL JSON projection；阶段 25 的 `postgres` backend precheck 验证的是切换后 live app 实际使用的 `PostgresStateStore` repository shape。

真实 runtime backend 仍存在 P0/P1，说明现在直接把 live service 切到 PostgreSQL 可能造成业务状态读取差异。因此必须停止，不能修改 service、不能 `daemon-reload`、不能 restart。

## 首次执行未执行事项

- 未修改 `/opt/fin-ops/current`。
- 未修改 `/opt/fin-ops/venv`。
- 未修改 `/opt/fin-ops/fin-ops.env`。
- 未修改 `/etc/systemd/system/fin-ops.service`。
- 未写入新的 service drop-in。
- 未执行 `systemctl daemon-reload`。
- 未执行 `systemctl restart fin-ops.service`。
- 未执行 read switch。
- 未写 production PostgreSQL business/runtime data。
- 未写 app Mongo。
- 未读取、写入或触碰 OA Mongo `form_data_db.form_data`。

## Gate

阶段 25 Gate：

- `PASS_READ_SWITCH_EXECUTED_POSTGRES_PRIMARY`

## 下一步

下一步进入 production observation / rollback window：

- 持续观察 `fin-ops.service` health、journal 和业务 smoke。
- 继续保留 app Mongo 回滚读源，不做 contract/drop Mongo。
- 在观察期内如出现 PostgreSQL runtime 读写问题，优先执行 drop-in rollback，而不是用旧 app Mongo 覆盖 PostgreSQL。
- 任何后续生产写路径策略调整、contract、清理 app Mongo 前，仍必须重新运行 read-only shadow-read、runtime policy 和 rollback readiness。
