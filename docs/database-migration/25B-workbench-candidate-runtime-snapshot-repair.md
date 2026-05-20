# 阶段 25B：Workbench Candidate Runtime Snapshot Repair

## 目标

阶段 25B 根据用户授权，修复阶段 25A 剩余的唯一 P1 blocker：production PostgreSQL 缺少 `state:workbench_candidate_matches` runtime snapshot。

本阶段不是 read switch，不修改生产服务，不重启 `fin-ops.service`。

## 执行边界

本阶段唯一 production PostgreSQL 写入：

- `app.app_settings`
- `settings_key='state:workbench_candidate_matches'`
- affected rows：`1`

未执行：

- 未写 app Mongo。
- 未读取、写入或触碰 OA Mongo `form_data_db.form_data`。
- 未清理 `read_model.workbench_candidate_matches`。
- 未修改 `/opt/fin-ops/current`。
- 未修改 `/opt/fin-ops/venv`。
- 未修改 systemd unit/drop-in/env。
- 未执行 `systemctl daemon-reload`。
- 未重启 `fin-ops.service`。
- 未执行 read switch/cutover。

## Prompt

阶段 25B Codex 执行 prompt：

- `prompts/25B-workbench-candidate-runtime-snapshot-repair.prompt.md`

## 本地验证

目标测试：

```bash
pytest tests/test_postgres_state_store.py tests/test_postgres_repositories_boundaries.py tests/test_shadow_read_rehearsal.py -q
```

结果：

- `37 passed, 4 subtests passed in 0.37s`

完整测试：

```bash
PYTHONPATH=. pytest -q
```

结果：

- `1278 passed, 21 skipped, 5 warnings, 50 subtests passed in 5.69s`

## Production Repair

Run ID：

- `stage25B-workbench-candidate-snapshot-repair-20260521004245`

One-off release 目录：

- `/opt/fin-ops/releases/stage25B-workbench-candidate-snapshot-repair-20260521004245`

Repair runner：

- `backend/src/fin_ops_platform/tools/repair_workbench_candidate_snapshot.py`

Dry-run 结果：

- app Mongo read-only snapshot 校验通过。
- `candidate_count=1883`
- `scope_run_count=26`
- `schema_version=2026-05-exception-candidate-lifecycle`
- `sha256=d05a8f8a6a7b8ddb088c09555714828c35d126056b1d17c4d0fd6ff4b4cbbe4c`
- `read_model.workbench_candidate_matches` 当前行数：`5281`
- dry-run 未写库。

Execute 结果：

- 写入执行：`true`
- affected rows：`1`
- 写入后 PostgreSQL `state:workbench_candidate_matches`：
  - `candidate_count=1883`
  - `scope_run_count=26`
  - `schema_version=2026-05-exception-candidate-lifecycle`
  - `sha256=d05a8f8a6a7b8ddb088c09555714828c35d126056b1d17c4d0fd6ff4b4cbbe4c`
  - `version=1`

未清理 `read_model.workbench_candidate_matches`，因为阶段 25A 已让 `PostgresStateStore.load_workbench_candidate_matches()` 在 runtime snapshot 存在时优先读取 `app.app_settings`。

## Production Gates

### Full-domain Native PostgresStateStore Shadow-read

Report：

- `reports/stage25B-workbench-candidate-snapshot-repair-20260521004245.full-shadow-read-postgres.json`

结果：

- Gate：`PARTIAL`
- Compared domains：`20`
- Matched domains：`19`
- Mismatched domains：`1`
- Primary errors：`0`
- Shadow errors：`0`
- P0：`0`
- P1：`0`
- P2：`12`

唯一 mismatch：

- `app_health_alerts`：`P2=12`

该 P2 是阶段 21 已接受的 retention-only runtime state，不构成 read switch blocker。

### Conservative Psql JSON Shadow-read

Report：

- `reports/stage25B-workbench-candidate-snapshot-repair-20260521004245.conservative-shadow-read.json`

结果：

- Gate：`PASS`
- Compared domains：`8`
- Matched domains：`8`
- P0：`0`
- P1：`0`
- P2：`0`
- read errors：`0`

### Runtime Policy

Report：

- `reports/stage25B-workbench-candidate-snapshot-repair-20260521004245.runtime-policy.json`

结果：

- Gate：`PASS`
- `blocked_unknown_count=0`
- Classification：
  - `rebuildable=114`
  - `retention_only=34`
- Mismatch counts：
  - `different=3`
  - `missing_in_primary=0`
  - `missing_in_shadow=0`

### No-traffic PostgreSQL Mode Check

Report：

- `reports/stage25B-workbench-candidate-snapshot-repair-20260521004245.postgres-mode-check.stdout.json`

结果：

- status：`ready`
- storage mode：`postgres`
- storage backend：`postgres`
- PostgreSQL status：`ready`
- PostgreSQL database：`fin_ops`
- PostgreSQL user：`fin_ops_app_runtime`
- PostgreSQL schema version：`8`
- stderr：`0 bytes`

### Read-only Cutover Preflight

Report：

- `reports/stage25B-workbench-candidate-snapshot-repair-20260521004245.cutover-preflight.json`

结果：

- status：`pass`
- PostgreSQL connectivity：`ready`
- schema version：`0008`
- runtime user：`fin_ops_app_runtime`
- guards：
  - `no_production_writes=enforced`
  - forbidden `cutover` / `enable_dual_write` / `production_write` / `restart_service` refused
- stderr：`0 bytes`

### Service Metadata Guard

Reports：

- `reports/stage25B-workbench-candidate-snapshot-repair-20260521004245.service-before.txt`
- `reports/stage25B-workbench-candidate-snapshot-repair-20260521004245.service-after.txt`
- `reports/stage25B-workbench-candidate-snapshot-repair-20260521004245.service-before-after.diff`

结果：

- diff：`0 bytes`
- production service metadata unchanged。

## Gate

阶段 25B Gate：

- `PASS_WORKBENCH_CANDIDATE_RUNTIME_SNAPSHOT_REPAIR_READY_FOR_READ_SWITCH_AUTHORIZATION`

含义：

- 25A 剩余 `workbench_candidate_matches` P1 已修复。
- full-domain native `PostgresStateStore` shadow-read 已无 P0/P1/read error。
- conservative psql JSON shadow-read PASS。
- runtime policy PASS，`blocked_unknown=0`。
- no-traffic PostgreSQL mode check ready。
- read-only cutover preflight pass。
- production service 未修改、未重启。

## 下一步

可以重新进入阶段 25 controlled read switch execute 授权流程。

执行任何 production service 配置变更或 restart 前，仍必须 same-run 再跑：

- production read-only shadow-read。
- runtime policy classification。
- no-traffic PostgreSQL mode check。
- cutover preflight。
- service metadata before snapshot。

只要出现 P0/P1/read error/`blocked_unknown`，必须停止。
