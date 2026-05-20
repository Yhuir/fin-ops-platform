# 14 Runtime state policy / controlled mirror-write rehearsal planning

执行时间：2026-05-20

Gate：`PASS_FOR_PLANNING`

## 阶段边界

- 阶段 14 只补齐 runtime state 策略、controlled mirror-write rehearsal 计划、本地代码和测试验证。
- 没有执行 production cutover。
- 没有启用 production dual-write 或 mirror-write。
- 没有把 production backend 切到 PostgreSQL、shadow 或 dual。
- 没有修改或重启 production `fin-ops.service`。
- 没有修改 systemd、生产 release 或生产运行配置。
- 没有写 app Mongo `fin_ops_platform_app`。
- 没有触碰 OA Mongo `form_data_db.form_data`。
- 没有写 production PostgreSQL `fin_ops`。
- 没有新增 schema migration；现有 `job.background_jobs` 与 `audit.app_health_alerts` 可以表达阶段 14 策略需要的 runtime state。

## 承接阶段 13

阶段 13 final report：

- `docs/database-migration/reports/stage13-shadow-read-postrepair-20260520154127.stage13.shadow-read.json`

阶段 13 repair artifacts：

- `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-dry-run.json`
- `docs/database-migration/reports/stage13-shadow-read-20260520150138.stage13.repair-result.json`

阶段 13 已闭合所有业务事实阻塞：

```text
gate=PARTIAL
total_domains=7
compared_domains=7
matched_domains=5
mismatched_domains=2
primary_errors=0
shadow_errors=0
severity_counts=P0:0,P1:0,P2:13,ignored:0
```

已 matched：

- `app_settings`
- `workbench_pair_relations`
- `no_oa_bank_batches`
- `bank_transaction_categories`
- `turnover_relations`

仍存在的 P2 只属于 runtime state：

| Domain | Mismatch | Count | 阶段 14 策略 |
| --- | --- | ---: | --- |
| `background_jobs` | `missing_in_primary` | 10 | PostgreSQL shadow 中存在 primary 当前没有的 job history；按 live payload 分类为 `cleanup_candidate`、`retention_only` 或 `blocked_unknown`。active/attention job 未来必须 mirror-write。 |
| `app_health_alerts` | `missing_in_shadow` | 3 | current health alert 是运行态；controlled mirror-write rehearsal 中 active alert 必须 mirror-write，recovered alert 只作为 retention。 |

阶段 13 report 是脱敏 diff summary，不展开原始 payload。因此阶段 14 的 policy artifact 不记录业务原文，只记录 mismatch category、分类规则和后续 live payload preflight 要求。

Policy artifact：

- `docs/database-migration/reports/stage14-runtime-state-policy.json`

## Background jobs policy

代码事实：

- `BackgroundJobService` 的状态集合为 `queued`、`running`、`succeeded`、`partial_success`、`failed`、`cancelled`、`acknowledged`、`superseded`。
- `queued`、`running` 是 active。
- `failed`、`partial_success` 是 attention，除非已 acknowledged 或 superseded。
- `succeeded`、`cancelled`、`acknowledged`、`superseded` 是 terminal history。
- service 启动会把 stale active job 标记为 failed，因此 active/attention state 对用户可见状态、补偿和重试有影响。
- `DualStateStore` 已 mirror `save_background_jobs`。

策略表：

| 条件 | Classification | Mirror-write | Cutover blocker |
| --- | --- | --- | --- |
| `status in {queued,running}` | `mirror_write_required` | 是 | 否；但 rehearsal 后仍缺失需要调查 |
| `status in {failed,partial_success}` 且未 acknowledged/superseded | `mirror_write_required` | 是 | 否；但 rehearsal 后仍缺失需要调查 |
| terminal 非 derived job | `retention_only` | 否 | 否 |
| terminal derived job 且有 `source`、`affected_scopes` 或 `affected_months` | `rebuildable` | 否 | 否 |
| shadow-only terminal job 且有 timestamp evidence | `cleanup_candidate` | 否 | 否 |
| unknown status/type、payload 非 object、shadow-only terminal 缺 timestamp | `blocked_unknown` | 否 | 是 |

Derived / rebuildable job type：

- `workbench_matching`
- `workbench_rebuild`
- `workbench_read_model_rebuild`
- `oa_sync_workbench_rebuild`
- `cost_statistics_cache_warmup`
- `tax_offset_cache_warmup`
- `historical_etc_reconcile`

Non-derived fact/job type：

- `file_import`
- `etc_invoice_import`
- `settings_data_reset`

阶段 13 的 10 条 `background_jobs` P2 是 `missing_in_primary`。在没有 live payload 展开的情况下，阶段 14 将其归为 `cleanup_candidate_or_retention_only` category；阶段 15 production controlled rehearsal preflight 必须对 live payload 运行同一分类器，若出现 `blocked_unknown` 或 active/attention shadow-only job，不能进入 mirror-write 演练。

## App health alerts policy

代码事实：

- `AppHealthAlertService` snapshot contract 是 `{"records": {alert_id: payload}}`。
- 当前状态为 `active`、`recovered`。
- 当前 severity 为 `critical`、`warning`，排序逻辑也接受 `info`。
- alert 没有独立 source 字段，runtime source 由 `kind + scope` 表达。
- 每次 health snapshot 会 evaluate alerts 并保存完整 alert snapshot。
- `DualStateStore` 已 mirror `save_app_health_alerts`。

Known runtime alert kinds：

| Kind | Source | Severity |
| --- | --- | --- |
| `oa_sync_dirty_scope` | OA sync dirty scope age | `warning` 或 `critical` |
| `workbench_rebuild_long_running` | read model rebuild time | `warning` |
| `background_job_long_running` | running job duration | `warning` |
| `dependency_unavailable` | dependency health | `critical` |
| `session_blocked` | app session state | `critical` |

策略表：

| 条件 | Classification | Mirror-write | Cutover blocker |
| --- | --- | --- | --- |
| known kind 且 `status=active` | `mirror_write_required` | 是 | 否；但 rehearsal 后仍缺失需要调查 |
| known kind 且 `status=recovered` | `retention_only` | 否 | 否 |
| shadow-only recovered alert | `cleanup_candidate` | 否 | 否 |
| unknown kind/status/severity、payload 非 object | `blocked_unknown` | 否 | 是 |

阶段 13 的 3 条 `app_health_alerts` P2 是 `missing_in_shadow`。这类 current runtime alert 不应通过 one-off backfill 强行修复；正确闭环是在 controlled mirror-write rehearsal 中验证 `save_app_health_alerts` 写路径。若 rehearsal 后 active alert 仍缺失 shadow，需要修 mirror write 或 repository，而不是把 P2 静默 ignored。

## Dual-write / mirror-write policy

Mirror-write methods：

- `save`
- `save_app_settings`
- `save_tax_certified_imports`
- `save_etc_state`
- `save_etc_reconciliation_state`
- `save_workbench_pair_relations`
- `save_no_oa_bank_batches`
- `save_bank_transaction_categories`
- `save_turnover_relations`
- `save_workbench_read_models`
- `save_workbench_candidate_matches`
- `save_cost_statistics_read_models`
- `save_tax_offset_read_models`
- `save_background_jobs`
- `save_app_health_alerts`

Primary-only file-byte write methods：

- `store_import_file`
- `store_etc_invoice_file`
- `store_etc_reconciliation_file`
- `save_historical_etc_repair_bundle`

失败语义：

- primary failure：不执行 mirror write，原异常抛出。
- non-strict mirror failure：primary 成功结果返回，记录脱敏 mirror failure summary。
- strict mirror failure：primary 成功后 mirror 失败，抛 `DualWriteMirrorError`，summary 记录 strict failure。
- file-byte writes：继续 primary-only，不在阶段 14 引入文件对象镜像策略。

## Controlled mirror-write rehearsal runbook

阶段 14 不启用生产 mirror-write。下一阶段如获授权，建议按以下顺序执行：

1. 部署或一次性同步已包含阶段 14 policy/test 的代码到服务器临时路径。
2. 继续保持 `FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1`，先运行 production read-only preflight。
3. 对 `background_jobs` 和 `app_health_alerts` live payload 执行 runtime state classifier。
4. 若存在 `blocked_unknown`，停止并形成 remediation report。
5. 若只有 `retention_only`、`rebuildable`、`cleanup_candidate` 或 active/current `mirror_write_required`，进入受控 one-off mirror-write rehearsal。
6. 只允许开启受控、短窗口、可回滚的 dual/mirror write；不得切 primary 到 PostgreSQL。
7. 执行 shadow-read，确认 conservative domains 无 P0/P1，runtime P2 均有 policy explanation。
8. 记录 mirror success/failure summary，必须脱敏。
9. 关闭 rehearsal 开关，确认服务状态未异常。
10. 形成阶段 15 report 后再讨论 read switch 或 cutover。

进入阶段 15 前必须满足：

- 用户明确授权 production controlled mirror-write one-off rehearsal。
- production read-only preflight 无 `blocked_unknown`。
- 不需要写 OA Mongo。
- 不需要写 app Mongo。
- 不修改或重启 systemd。
- 有回滚和观察窗口。

## 本地代码变更

新增：

- `backend/src/fin_ops_platform/services/runtime_state_policy.py`
- `tests/test_runtime_state_policy.py`
- `docs/database-migration/reports/stage14-runtime-state-policy.json`

修改：

- `tests/test_dual_state_store.py`
- `tests/test_shadow_read_rehearsal.py`
- `docs/database-migration/README.md`
- `docs/database-migration/07-shadow-dualwrite-production-cutover.md`

测试覆盖：

- background jobs：active、attention、terminal、shadow-only cleanup、derived rebuildable、unknown status/type、缺 timestamp cleanup blocker。
- app health alerts：active mirror、recovered retention、shadow-only recovered cleanup、unknown kind/severity/status blocker。
- dual-write：`save_background_jobs` 和 `save_app_health_alerts` 已在 required mirror methods 中；全部 file-byte write methods 覆盖 primary-only。
- shadow-read gate：P2-only runtime mismatch 返回 `PARTIAL`，不阻塞下一阶段规划；P0/P1 或 read error 仍 `BLOCKED`。

## 本地验证

阶段 14 首轮 targeted verification：

```text
python -m py_compile backend/src/fin_ops_platform/services/runtime_state_policy.py backend/src/fin_ops_platform/services/dual_state_store.py backend/src/fin_ops_platform/services/shadow_read_rehearsal.py
python -m pytest tests/test_runtime_state_policy.py tests/test_dual_state_store.py tests/test_shadow_read_rehearsal.py -q
32 passed, 24 subtests passed
```

阶段 14 基线验证沿用本阶段执行记录：

```text
python -m py_compile backend/src/fin_ops_platform/services/dual_state_store.py backend/src/fin_ops_platform/services/shadow_state_store.py backend/src/fin_ops_platform/services/shadow_read_rehearsal.py backend/src/fin_ops_platform/services/state_store_factory.py
python -m pytest tests/test_dual_state_store.py tests/test_shadow_state_store.py tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_state_store_factory_preflight.py tests/test_cutover_preflight.py -q
53 passed, 13 subtests passed
```

```text
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q
32 passed, 11 skipped, 5 warnings, 10 subtests passed
```

```text
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
status=ready
storage.backend=local_pickle
```

本机 PostgreSQL 工具已存在：

```text
initdb
pg_ctl
createdb
psql
```

使用本机临时 UTF8 PostgreSQL cluster 与 disposable test DB `fin_ops_stage14_test` 验证：

```text
python -m pytest tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py -q
11 passed, 5 warnings, 16 subtests passed
```

测试结束后临时 PostgreSQL cluster 已 stop，临时目录已清理。

PostgreSQL 回归矩阵：

```text
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q
32 passed, 11 skipped, 5 warnings, 10 subtests passed
```

最终全量验证：

```text
python -m pytest -q
1215 passed, 16 skipped, 5 warnings, 50 subtests passed
```

## Gate 判定

阶段 14 Gate：`PASS_FOR_PLANNING`。

原因：

- 阶段 13 及之前的 P0/P1 已清零。
- 剩余 `background_jobs` 和 `app_health_alerts` P2 已有可执行分类器、policy artifact 和测试。
- `save_background_jobs` 与 `save_app_health_alerts` 已在 mirror-write 方法集合中，并有测试覆盖。
- P2-only gate 语义已用 runner 级测试固定为 `PARTIAL`。
- 阶段 14 未执行任何生产写入、service 修改、restart、dual-write、mirror-write 或 cutover。

仍不能直接 cutover：

- 阶段 14 只是规划和本地验证，不是生产 mirror-write 观测窗口。
- 阶段 13 report 是脱敏 summary；阶段 15 必须在生产只读 preflight 中对 live runtime payload 运行分类器。
- 只有 production controlled mirror-write one-off rehearsal 通过后，才可讨论 read switch / cutover。

下一步建议：

- 阶段 15：授权后的 production controlled mirror-write one-off rehearsal。
