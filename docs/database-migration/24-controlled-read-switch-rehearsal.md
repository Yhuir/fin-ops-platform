# 阶段 24：Controlled Production Read Switch Rehearsal

## 目标

阶段 24 的目标是在不修改生产 service 配置、不重启 `fin-ops.service`、不执行正式 read switch 的前提下，基于阶段 23 release candidate 和 runtime credential 完成同一轮 production read-only gate、runtime policy classification、no-traffic PostgreSQL mode check、cutover preflight，并生成下一步 read switch execute 授权所需的 dry-run runbook。

本阶段不是 cutover，不让 live service 使用 PostgreSQL DSN。

## 执行边界

- 未修改 `/opt/fin-ops/current`。
- 未修改 `/opt/fin-ops/venv`。
- 未修改 systemd unit、drop-in 或 live env。
- 未重启 `fin-ops.service`。
- 未执行 read switch 或 cutover。
- 未写 production PostgreSQL business/runtime data。
- 未写 app Mongo。
- 未读取、写入或触碰 OA Mongo `form_data_db.form_data`。

## Prompt

阶段 24 Codex 执行 prompt：

- `prompts/24-controlled-read-switch-rehearsal.prompt.md`

最终 Gate：

- `PASS_READ_SWITCH_REHEARSAL_READY_REQUIRES_EXECUTE_AUTHORIZATION`

## 本地验证

本地 targeted tests：

```bash
PYTHONPATH=backend/src pytest -q tests/test_postgres_state_store.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py tests/test_runtime_state_policy.py tests/test_shadow_read_rehearsal.py tests/test_stage15_runtime_tools.py tests/test_state_store_factory_preflight.py tests/test_cutover_preflight.py tests/test_app_postgres_mode.py
```

结果：

- `68 passed, 5 warnings, 29 subtests passed in 0.65s`

本地 default app check：

```bash
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
```

结果：

- `status=ready`
- `storage.backend=local_pickle`

## Production Rehearsal

Run ID：

- `stage24-read-switch-rehearsal-20260520233932`

使用阶段 23 release：

- Release ID：`stage23-release-runtime-20260520233335`
- Release base：`/opt/fin-ops/releases/stage23-release-runtime-20260520233335`
- Release source：`/opt/fin-ops/releases/stage23-release-runtime-20260520233335/src`
- Release venv：`/opt/fin-ops/releases/stage23-release-runtime-20260520233335/venv`
- Stage 24 data dir：`/opt/fin-ops/releases/stage23-release-runtime-20260520233335/stage24-read-switch-rehearsal-20260520233932-data`
- Credential file：`/root/fin_ops_stage23_postgres_runtime.env`
- Redacted DSN：`postgresql://fin_ops_app_runtime:***@127.0.0.1:5432/fin_ops`

### Service Metadata Guard

`service-before.txt` 与 `service-after.txt` diff 为空。

采集结果保持：

- `MainPID=452671`
- `ExecMainStartTimestamp=Wed 2026-05-20 16:07:52 CST`
- `ExecStart=/opt/fin-ops/venv/bin/python -m fin_ops_platform.app.main --host 127.0.0.1 --port 18001`
- `WorkingDirectory=/opt/fin-ops/current`
- `User=root`
- `ActiveState=active`
- `SubState=running`

### Same-run Shadow-read

结果：

- Gate：`PARTIAL`
- Compared domains：`8`
- Matched domains：`7`
- Mismatched domains：`1`
- Primary errors：`0`
- Shadow errors：`0`
- P0：`0`
- P1：`0`
- P2：`12`

Domain 明细：

- `app_settings`：matched
- `pending_invoice_commands`：matched
- `background_jobs`：matched
- `app_health_alerts`：mismatched，`P2=12`
- `workbench_pair_relations`：matched
- `no_oa_bank_batches`：matched
- `bank_transaction_categories`：matched
- `turnover_relations`：matched

`app_health_alerts` 的 `P2=12` 延续阶段 21 已接受的 retention-only runtime state，不构成 read switch rehearsal 阻断。阶段 24 的 gate 只允许已解释 P2 继续；任意 P0/P1/read error 仍必须停止。

### Runtime Policy Classification

结果：

- Gate：`PASS`
- `blocked_unknown_count=0`
- Domains：`2`
- Classification counts：
  - `rebuildable=114`
  - `retention_only=34`
- Mismatch counts：
  - `different=0`
  - `missing_in_primary=0`
  - `missing_in_shadow=0`

### No-traffic PostgreSQL Mode Check

结果：

- Exit code：`0`
- App status：`ready`
- Storage backend：`postgres`
- Storage mode：`postgres`
- PostgreSQL status：`ready`
- PostgreSQL database：`fin_ops`
- PostgreSQL user：`fin_ops_app_runtime`
- PostgreSQL schema version：`8`
- stderr：`0 bytes`

### Read-only Cutover Preflight

结果：

- Status：`pass`
- PostgreSQL connectivity：`ready`
- PostgreSQL schema version：`0008`
- `schema_migrations_table=public.schema_migrations`
- Runtime DB user：`fin_ops_app_runtime`
- Guard：`no_production_writes=enforced`
- Forbidden actions refused：
  - `cutover`
  - `enable_dual_write`
  - `production_write`
  - `restart_service`

Core counts：

- `app.import_batches=6`
- `app.import_batch_rows=897`
- `app.import_files=31`
- `app.invoices=391`
- `app.bank_transactions=431`
- `read_model.search_index_rows=822`

## 报告产物

关键 reports：

- `reports/stage24-read-switch-rehearsal-20260520233932.stage24-summary.json`
- `reports/stage24-read-switch-rehearsal-20260520233932.stage24.shadow-read.json`
- `reports/stage24-read-switch-rehearsal-20260520233932.stage24.runtime-policy.json`
- `reports/stage24-read-switch-rehearsal-20260520233932.stage24.postgres-mode-check.stdout.json`
- `reports/stage24-read-switch-rehearsal-20260520233932.stage24.cutover-preflight.json`
- `reports/stage24-read-switch-rehearsal-20260520233932.stage24.read-switch-execute-plan.md`
- `reports/stage24-read-switch-rehearsal-20260520233932.service-before.txt`
- `reports/stage24-read-switch-rehearsal-20260520233932.service-after.txt`

所有 stderr artifact 均为 `0 bytes`。

## Gate

阶段 24 Gate：

- `PASS_READ_SWITCH_REHEARSAL_READY_REQUIRES_EXECUTE_AUTHORIZATION`

含义：

- 本地 targeted tests 通过。
- 本地 default app check 通过。
- production service metadata 前后未变化。
- same-run shadow-read 无 P0/P1/read error。
- runtime policy `PASS` 且 `blocked_unknown=0`。
- no-traffic PostgreSQL mode app check 通过。
- read-only cutover preflight 通过。
- read switch execute dry-run plan 已生成。
- production service 未修改、未重启、未切换。
- app Mongo 未写入。
- OA Mongo `form_data_db.form_data` 未触碰。

## 下一步

下一步可以进入阶段 25：controlled production read switch execute authorization。

阶段 25 不应自动执行，必须先由用户单独授权，授权范围需要明确：

- 是否允许修改 production service env/drop-in 或 release pointer。
- 是否允许使用 `/root/fin_ops_stage23_postgres_runtime.env` 作为 live service PostgreSQL credential source。
- 是否允许 `systemctl daemon-reload`。
- 是否允许 `systemctl restart fin-ops.service`。
- 修改前 backup/freeze 范围。
- rollback 命令和观察窗口。

即使用户授权阶段 25，执行前仍必须重新运行 same-run read-only shadow-read、runtime policy classification、no-traffic PostgreSQL mode check 和 service metadata guard；只要出现 P0/P1/read error/`blocked_unknown`，必须停止。
