# 25B 阶段 Codex 执行 Prompt：Workbench candidate runtime snapshot repair

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 25B：根据用户授权，仅修复 production PostgreSQL 中 `workbench_candidate_matches` runtime snapshot 缺失问题，并重新运行 production read-only full-domain `PostgresStateStore` shadow-read。完成后明确是否可以重新申请阶段 25 controlled read switch execute 授权。

## 当前背景

阶段 25A 已修复阶段 25 真实 `PostgresStateStore` full-domain shadow-read 中的代码层 blocker：

- `workbench_pair_relations` P0 已修复。
- `etc_state` / `etc_reconciliation_state` / historical ETC / read model export metadata 已修复或可审计解释。
- 阶段 25A targeted production read-only revalidation 结果：
  - `etc_reconciliation_state` matched。
  - `workbench_candidate_matches` 仍 P1=3：
    - `candidates` missing in PostgreSQL shadow。
    - `schema_version` missing in PostgreSQL shadow。
    - `scope_runs` missing in PostgreSQL shadow。

根因：production app Mongo 当前 `workbench_candidate_matches` runtime snapshot 有 candidates / schema_version / scope_runs；production PostgreSQL 尚未写入 `app.app_settings` 的 `state:workbench_candidate_matches` snapshot。

## 用户授权边界

允许写 production PostgreSQL，仅限：

1. `app.app_settings` 中 `settings_key='state:workbench_candidate_matches'` 的一行。

允许读取：

1. app Mongo 的当前 `workbench_candidate_matches` snapshot，只读。
2. production PostgreSQL 当前相关状态，只读。

本阶段不执行可选 read_model 清理，除非用户另行授权。当前代码已让 `PostgresStateStore.load_workbench_candidate_matches()` 在 snapshot 存在时优先读取 `app.app_settings`，因此无需清理 `read_model.workbench_candidate_matches` 才能通过 read switch gate。

禁止：

1. 写 app Mongo。
2. 读取、写入或触碰 OA Mongo `form_data_db.form_data`。
3. 修改 `/opt/fin-ops/current`。
4. 修改 `/opt/fin-ops/venv`。
5. 修改 systemd unit/drop-in/env。
6. 执行 `systemctl daemon-reload`。
7. 重启 `fin-ops.service`。
8. 执行 read switch/cutover。
9. 输出任何 secret、完整 DSN、SSH 密码、Mongo URI。

## 必须先读

- `docs/database-migration/25A-actual-postgres-store-shadow-remediation.md`
- `docs/database-migration/reports/stage25A-actual-postgres-store-shadow-20260521001446-r4-domains.full-shadow-read-postgres.json`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/tools/run_shadow_read_rehearsal.py`
- `backend/src/fin_ops_platform/tools/run_runtime_state_policy_preflight.py`
- `backend/src/fin_ops_platform/tools/run_cutover_preflight.py` 或当前等价 cutover preflight 工具

## 执行任务

### 25B.1 本地确认

确认当前代码满足：

- `PostgresStateStore.load_workbench_candidate_matches()` 在 `state:workbench_candidate_matches` snapshot 存在时优先返回 snapshot。
- targeted tests 覆盖该行为。
- 本地相关测试通过。

### 25B.2 生成 repair artifact

在 production 服务器 one-off release 目录中执行 repair 脚本前必须先生成 dry-run summary：

- 从 app Mongo read-only store 加载 `load_workbench_candidate_matches()`。
- 校验 payload 是 dict。
- 校验包含 `candidates`、`schema_version`、`scope_runs`。
- 校验 `len(candidates) > 0`。
- 计算 redacted summary：
  - candidate_count
  - scope_run_count
  - schema_version
  - payload sha256
  - existing PostgreSQL `state:workbench_candidate_matches` 是否存在
  - existing `read_model.workbench_candidate_matches` row count

dry-run 不写任何数据库。

### 25B.3 执行授权 repair

只有 dry-run 校验通过才执行：

```sql
insert into app.app_settings(settings_key, version, settings_payload, raw_payload, updated_at)
values ('state:workbench_candidate_matches', 1, <snapshot_jsonb>, jsonb_build_object('normalized_payload', <snapshot_jsonb>), now())
on conflict (settings_key) do update set
  version = app.app_settings.version + 1,
  settings_payload = excluded.settings_payload,
  raw_payload = excluded.raw_payload,
  updated_at = now();
```

必须验证：

- 只写入/更新 `settings_key='state:workbench_candidate_matches'`。
- affected row count 为 1。
- repair 后 PostgreSQL 该 row 的 candidates count / scope_runs count / schema_version / sha256 与 app Mongo snapshot 一致。

不得清理 `read_model.workbench_candidate_matches`，除非用户另行授权。

### 25B.4 Production read-only gates

repair 后必须重新运行：

1. full-domain真实 `PostgresStateStore` shadow-read：
   - primary backend：`mongo_readonly`
   - shadow backend：`postgres`
   - `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`
   - 20 domains
2. conservative psql JSON shadow-read。
3. runtime policy classification。
4. no-traffic PostgreSQL mode check。
5. read-only cutover preflight。

继续条件：

- full-domain `PostgresStateStore` shadow-read 无 P0/P1/read error。
- conservative psql JSON shadow-read 无 P0/P1/read error；仅 P2 retention-only 可接受。
- runtime policy PASS，`blocked_unknown_count=0`。
- no-traffic PostgreSQL mode check ready。
- cutover preflight pass。

若任一 gate 失败，停止并记录 blocker；不得修改 production service。

### 25B.5 文档

创建或更新：

- `docs/database-migration/25B-workbench-candidate-runtime-snapshot-repair.md`
- `docs/database-migration/README.md`
- `docs/index.md`
- `docs/database-migration/25A-actual-postgres-store-shadow-remediation.md`

必须记录：

- repair run id。
- 是否写 production PostgreSQL。
- 实际写入范围。
- 是否修改/restart production service。
- 每个 gate 的结果。
- 下一步是否可重新请求 stage 25 read switch execute 授权。

## Gate

可用 gate：

- `PASS_WORKBENCH_CANDIDATE_RUNTIME_SNAPSHOT_REPAIR_READY_FOR_READ_SWITCH_AUTHORIZATION`
- `BLOCKED_REPAIR_DRY_RUN_VALIDATION`
- `BLOCKED_REPAIR_EXECUTE`
- `BLOCKED_FULL_POSTGRES_STORE_SHADOW_READ`
- `BLOCKED_RUNTIME_POLICY`
- `BLOCKED_NO_TRAFFIC_POSTGRES_CHECK`
- `BLOCKED_CUTOVER_PREFLIGHT`

最终回答必须说明：

- prompt 路径。
- production PostgreSQL 是否被写入，以及精确范围。
- production service 是否被修改/重启。
- app Mongo / OA Mongo 是否被写入或触碰。
- full-domain shadow-read 最终结果。
- 是否可以重新进入 stage 25 read switch execute 授权。
```
