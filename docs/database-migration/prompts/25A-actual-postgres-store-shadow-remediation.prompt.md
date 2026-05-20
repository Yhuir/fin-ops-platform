# 25A 阶段 Codex 执行 Prompt：Actual PostgreSQL store shadow remediation

```text
/goal
在当前 worktree `/Users/yu/Desktop/fin-ops-platform-db-migration` 中执行数据库迁移阶段 25A：修复阶段 25 在真实 `PostgresStateStore` backend full-domain shadow-read 中暴露的 P0/P1 runtime shape 差异，使 app 切换到 PostgreSQL 后实际读取路径与 app Mongo primary 兼容。阶段 25A 先做代码和只读验证；除非用户单独授权，不允许写 production PostgreSQL，不允许修改 production service，不允许 restart。

## 当前背景

阶段 24 conservative `postgres_psql_json` rehearsal 已 PASS，但阶段 25 在正式 read switch 前新增真实 `PostgresStateStore` backend full-domain shadow-read，结果 Gate 为 `BLOCKED`：

- Run ID：`stage25-full-shadow-postgres-precheck-20260520235831`
- P0：`20`
- P1：`77`
- P2：`3`
- read errors：`0`
- affected domains：
  - `workbench_pair_relations`
  - `turnover_ledger_extras`
  - `workbench_read_models`
  - `workbench_candidate_matches`
  - `cost_statistics_read_models`
  - `tax_offset_read_models`
  - `etc_state`
  - `etc_reconciliation_state`
  - `historical_etc_repair_parsed_seeds`
  - `historical_etc_repair_states`

## 用户当前授权边界

允许：

1. 读取本地代码、文档、reports。
2. 修改本地代码、测试和迁移文档。
3. 运行本地测试。
4. 通过 SSH 做 production 只读复核。
5. 创建新的 release candidate 目录并执行只读/no-traffic check。
6. 读取 app Mongo primary 作为 read-only shadow primary；不得写 app Mongo。
7. 读取 production PostgreSQL；不得写 production PostgreSQL。

不允许：

1. 修改 `/opt/fin-ops/current`。
2. 修改 `/opt/fin-ops/venv`。
3. 修改 systemd unit/drop-in/env。
4. 执行 `systemctl daemon-reload` 或 restart。
5. 执行 read switch/cutover。
6. 写 production PostgreSQL business/runtime data，除非用户之后单独授权。
7. 写 app Mongo。
8. 读取、写入或触碰 OA Mongo `form_data_db.form_data`。
9. 输出任何 secret、完整 DSN、SSH 密码、Mongo URI。

## 必须先读

- `docs/database-migration/25-controlled-read-switch-execute.md`
- `docs/database-migration/reports/stage25-full-shadow-postgres-precheck-20260520235831.stage25.full-shadow-read-postgres.json`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- `backend/src/fin_ops_platform/services/state_store_diff.py`
- affected service hydration code for ETC/workbench/read-model domains
- relevant tests under `tests/test_postgres_state_store.py`, `tests/test_postgres_state_store_integration.py`, `tests/test_postgres_repositories_core.py`, `tests/test_postgres_repositories_boundaries.py`

## 执行任务

### 25A.1 Root cause inventory

从 stage25 report 提取每个 affected domain 的 mismatch paths，判断是：

- repository load shape 不等价；
- transform/backfill 数据缺失；
- read model rebuildable projection 可接受但 diff severity/policy 需要调整；
- true production PostgreSQL data repair/backfill 需求。

必须记录 root cause，不允许直接“忽略 diff”。

### 25A.2 TDD 修复

对每类 root cause 先补失败测试，再做最小修复。

优先顺序：

1. `workbench_pair_relations` P0。
2. `etc_state` / `etc_reconciliation_state` P1。
3. `historical_etc_repair_states` P1。
4. read-model rebuildable projection P1。
5. `turnover_ledger_extras` P1。

### 25A.3 本地验证

必须运行：

```bash
PYTHONPATH=backend/src pytest -q \
  tests/test_postgres_state_store.py \
  tests/test_postgres_repositories_core.py \
  tests/test_postgres_repositories_boundaries.py \
  tests/test_postgres_state_store_integration.py \
  tests/test_shadow_read_rehearsal.py \
  tests/test_app_postgres_mode.py
```

并运行：

```bash
python -m pytest -q
```

### 25A.4 Production read-only revalidation

生成新的 release candidate 或同步修复代码到临时 release 目录，不修改 live service。

必须重新运行：

- conservative psql JSON shadow-read。
- runtime policy classification。
- no-traffic PostgreSQL mode check。
- read-only cutover preflight。
- full-domain真实 `PostgresStateStore` shadow-read。

继续条件：

- conservative shadow-read 无 P0/P1/read error。
- runtime policy PASS 且 `blocked_unknown=0`。
- no-traffic PostgreSQL mode check ready。
- cutover preflight pass。
- full-domain `PostgresStateStore` shadow-read 无 P0/P1/read error。

如果 full-domain 仍有 P0/P1，必须停止并记录剩余 blocker。

### 25A.5 文档

创建或更新：

- `docs/database-migration/25A-actual-postgres-store-shadow-remediation.md`
- `docs/database-migration/README.md`
- `docs/index.md`
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md`

## Gate

可用 gate：

- `PASS_ACTUAL_POSTGRES_STORE_SHADOW_READY_REQUIRES_READ_SWITCH_AUTHORIZATION`
- `BLOCKED_REQUIRES_PRODUCTION_POSTGRES_REPAIR_AUTHORIZATION`
- `BLOCKED_FULL_POSTGRES_STORE_SHADOW_READ`
- `BLOCKED_LOCAL_VERIFICATION`
- `BLOCKED_PRODUCTION_READONLY_REVALIDATION`

最终回答必须说明：

- prompt 路径。
- 是否修改了本地代码。
- 是否写 production PostgreSQL。
- 是否修改/重启 production service。
- full-domain `PostgresStateStore` shadow-read 最终结果。
- 下一步是否可重新进入 read switch execute 授权。
```
