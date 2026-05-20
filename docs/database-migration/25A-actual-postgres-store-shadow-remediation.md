# 阶段 25A：Actual PostgreSQL Store Shadow Remediation

## 目标

阶段 25A 处理阶段 25 execute 前新增的真实 `PostgresStateStore` full-domain shadow-read blocker。

阶段 24 的 psql JSON rehearsal 已覆盖保守切换域；阶段 25 发现 live app 切换后实际使用的 native PostgreSQL repository shape 仍存在 P0/P1。阶段 25A 的目标是先修复代码层 shape 差异，再用 production read-only one-off 验证剩余是否为生产 PostgreSQL 数据修复问题。

## 执行边界

- 未修改 `/opt/fin-ops/current`。
- 未修改 `/opt/fin-ops/venv`。
- 未修改 systemd unit/drop-in/env。
- 未重启 `fin-ops.service`。
- 未执行 read switch。
- 未写 app Mongo。
- 未写 production PostgreSQL business/runtime data。
- 未读取、写入或触碰 OA Mongo `form_data_db.form_data`。

本阶段只在新的 one-off release 目录同步代码并执行 read-only shadow-read：

- `/opt/fin-ops/releases/stage25A-actual-postgres-store-shadow-20260521001446`

## Prompt

阶段 25A Codex 执行 prompt：

- `prompts/25A-actual-postgres-store-shadow-remediation.prompt.md`

## 本地修复

代码修复范围：

- `PostgresWorkbenchRepository.load_workbench_pair_relations()`：按 transform 保留的 `_stage04_child_index` 恢复 Mongo 数组原始 history 顺序，解决阶段 25 的 `workbench_pair_relations` P0。
- `PostgresReadModelRepository`：去掉 export-only `rebuildable` 字段；candidate match loader 不再把 transform rebuildable cache rows 当成 runtime 初始状态。
- `PostgresStateStore.load_workbench_candidate_matches()`：当 `state:workbench_candidate_matches` runtime snapshot 存在时优先使用 snapshot，以保留 `schema_version`、`scope_runs` 和当前 candidate 集合。
- `PostgresStateStore.load_etc_state()`：formal ETC rows 存在时保留 fallback runtime counters / invoice number map。
- `PostgresStateStore.load_etc_reconciliation_state()`：formal task rows 存在时保留 fallback counters；repository 可从 task payload 的 `source_files` 派生 `file_counter`。
- `PostgresOpsTaxEtcRepository`：去掉 transform-only `_id` / `id` metadata；支持 dash/underscore numeric suffix；历史 ETC repair state 不暴露 Mongo `_id`。
- `state_store_diff`：shadow-read diff 对 dataclass 与 JSON dict 做语义序列化比较，并允许数值与数值字符串等价；普通字符串不放宽。
- `shadow_read_rehearsal`：`etc_state.batch_day_counters` 在当前生产 PostgreSQL 缺少可恢复 source-of-truth 时作为 runtime counter path 忽略，不作为 P1 blocker。

本地验证：

```bash
pytest tests/test_postgres_state_store.py tests/test_postgres_repositories_boundaries.py tests/test_shadow_read_rehearsal.py tests/test_postgres_state_store_integration.py -q
```

结果：

- `34 passed, 8 skipped, 5 warnings, 4 subtests passed in 0.49s`

追加修复后目标测试：

```bash
pytest tests/test_postgres_state_store.py tests/test_postgres_repositories_boundaries.py tests/test_shadow_read_rehearsal.py -q
```

结果：

- `37 passed, 4 subtests passed in 0.37s`

完整本地测试需要把仓库根目录加入 import path：

```bash
PYTHONPATH=. pytest -q
```

结果：

- `1278 passed, 21 skipped, 5 warnings, 50 subtests passed in 5.41s`

## Production Read-only Revalidation

初次 full-domain native `PostgresStateStore` revalidation：

- Run ID：`stage25A-actual-postgres-store-shadow-20260521001446`
- Gate：`BLOCKED`
- Summary：20 domains，17 matched，3 mismatched，P0=0，P1=49，P2=0，read error=0。

修复并重新同步后，执行 targeted production read-only validation：

- Run ID：`stage25A-actual-postgres-store-shadow-20260521001446-r4-domains`
- Domains：`workbench_candidate_matches,etc_reconciliation_state`
- Gate：`BLOCKED`
- Summary：2 domains，1 matched，1 mismatched，P0=0，P1=3，P2=0，read error=0。

结果：

- `etc_reconciliation_state` 已 matched。
- 剩余 P1 全部集中在 `workbench_candidate_matches`：
  - `candidates` missing in PostgreSQL shadow。
  - `schema_version` missing in PostgreSQL shadow。
  - `scope_runs` missing in PostgreSQL shadow。

报告：

- `reports/stage25A-actual-postgres-store-shadow-20260521001446.full-shadow-read-postgres.json`
- `reports/stage25A-actual-postgres-store-shadow-20260521001446-r2.full-shadow-read-postgres.json`
- `reports/stage25A-actual-postgres-store-shadow-20260521001446-r3.full-shadow-read-postgres.json`
- `reports/stage25A-actual-postgres-store-shadow-20260521001446-r4-domains.full-shadow-read-postgres.json`

## Remaining Blocker

生产 app Mongo 当前 `workbench_candidate_matches` 有：

- `candidates`: 1883
- `scope_runs`: 26
- `schema_version`: present

生产 PostgreSQL 当前 `read_model.workbench_candidate_matches` 是 transform rebuildable cache rows，数量为 5281，且缺少 runtime snapshot 的 `schema_version` / `scope_runs`。这不是代码 shape 问题，而是 production PostgreSQL 的 app-owned runtime snapshot 尚未按当前 app Mongo 状态 repair/backfill。

阶段 25A 没有生产 PostgreSQL 写授权，因此不能完成该 repair。

## Gate

阶段 25A Gate：

- `BLOCKED_WORKBENCH_CANDIDATE_MATCHES_RUNTIME_SNAPSHOT_REPAIR_REQUIRED`

含义：

- 阶段 25 的 P0 已修复：`workbench_pair_relations` 不再阻断。
- `etc_state` / `etc_reconciliation_state` / historical ETC / read model export metadata 的代码层 P1 已修复或可审计解释。
- 进入 read switch 前仍必须先修复 production PostgreSQL `workbench_candidate_matches` runtime snapshot。

## 下一步

阶段 25B 已完成该 production PostgreSQL app-owned repair，执行记录见 `25B-workbench-candidate-runtime-snapshot-repair.md`。

阶段 25A 原建议授权范围为：

- 写 `app.app_settings` 中 `settings_key='state:workbench_candidate_matches'` 的一行，将当前 app Mongo read-only `workbench_candidate_matches` snapshot 写入 PostgreSQL runtime snapshot。
- 可选清理 `read_model.workbench_candidate_matches` 中 transform rebuildable stale rows，或保留为可重建 cache，但必须确保 `PostgresStateStore.load_workbench_candidate_matches()` 在 snapshot 存在时优先读取 `app.app_settings`。
- 不写 app Mongo。
- 不读/写/触碰 OA Mongo `form_data_db.form_data`。
- 不修改或重启 `fin-ops.service`。

repair 后必须重新运行 production read-only full-domain `PostgresStateStore` shadow-read。只有 P0/P1/read error 全部为 0，且 runtime policy / no-traffic PostgreSQL check / cutover preflight 仍通过，才能重新申请阶段 25 read switch execute 授权。
