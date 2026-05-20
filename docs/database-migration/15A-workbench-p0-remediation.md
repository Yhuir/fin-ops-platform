# 阶段 15A：Workbench pair relations P0 remediation

## Gate

`PARTIAL_READY_FOR_STAGE15_RETRY`

阶段 15A 已完成阶段 15 blocker 的只读根因确认、post-main refreshed dry-run、用户授权后的 production PostgreSQL workbench repair，以及 repair 后 production one-off shadow-read。`workbench_pair_relations` 已达到 `mismatch_count=0`、`P0=0`、`P1=0`。整体 shadow-read 仍为 `PARTIAL`，但剩余差异为 runtime state `P2`，且阶段 14/15 runtime policy 分类器复核为 `PASS`、`blocked_unknown_count=0`。

## 阶段边界

- 本阶段不是 mirror-write、dual-write、cutover 或事实源切换。
- OA Mongo `form_data_db.form_data` 未访问、未读取、未写入、未修改。
- app Mongo `fin_ops_platform_app` 仅作为只读 primary source 使用，未写入。
- production PostgreSQL 已在用户明确授权下只写入白名单 workbench targets。
- production `fin-ops.service` 未修改、未重启；repair 前后 service 均为 active 且 `MainPID` 未变化。

## 输入事实

阶段 13 post-repair shadow-read 已确认 `workbench_pair_relations` matched：

- report: `docs/database-migration/reports/stage13-shadow-read-postrepair-20260520154127.stage13.shadow-read.json`
- `gate_recommendation=PARTIAL`
- `workbench_pair_relations.mismatch_count=0`
- `workbench_pair_relations.severity_counts=P0:0,P1:0,P2:0,ignored:0`

阶段 15 production read-only preflight 后重新出现 blocker：

- report: `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.readonly-preflight.json`
- `gate_recommendation=BLOCKED`
- conservative summary: `P0=5,P1=0,P2=13,ignored=0`
- `workbench_pair_relations.mismatch_count=5`
- P0 paths:
  - `pair_relation_history.length`
  - 4 个 `pair_relations.candidate:<hash>` `missing_in_shadow`

阶段 15 runtime policy live classification 已通过：

- report: `docs/database-migration/reports/stage15-mirror-write-20260520164450.stage15.runtime-policy.json`
- `gate_recommendation=PASS`
- `blocked_unknown_count=0`
- `background_jobs`: `cleanup_candidate=11`, `rebuildable=112`, `retention_only=23`
- `app_health_alerts`: `retention_only=11`

## 15A 只读 diagnostics

Run id: `stage15A-workbench-remediation-20260520171506`

Artifact:

- `docs/database-migration/reports/stage15A-workbench-remediation-20260520171506.stage15A.workbench-diagnostics.json`

Production service before diagnostics:

- `ActiveState=active`
- `MainPID=452671`
- `WorkingDirectory=/opt/fin-ops/current`

Diagnostics 结果：

| Metric | app Mongo primary | PostgreSQL shadow |
| --- | ---: | ---: |
| `pair_relations_count` | 146 | 142 |
| `pair_relation_history_count` | 21 | 17 |
| `missing_in_shadow_count` | 4 | n/a |
| `missing_in_primary_count` | 0 | n/a |
| `history_length_delta` | 4 | n/a |

Targeted stage 15 P0 key status:

- 4 个 stage 15 `candidate:<hash>` 当前均存在于 app Mongo primary。
- 4 个 stage 15 `candidate:<hash>` 当前均不存在于 PostgreSQL shadow。
- Diagnostics report 只包含 key hash 和 payload hash，不包含 raw payload。

Root cause classification:

`runtime_drift`

解释：

- 阶段 13 post-repair 同域已 matched。
- 阶段 15 之后的只读 diagnostics 显示 PostgreSQL 比 app Mongo 正好少 4 条 relation 和 4 条 history。
- mismatch 形态是 `missing_in_shadow`，不是 value/type/wrapper shape mismatch。
- 本地代码阅读和测试没有证明 `PsqlShadowReadStore`、PostgreSQL repository 或 normalizer 有新的 shape regression。
- 因此当前 blocker 是阶段 13 repair 后生产仍以 Mongo-only 写入 workbench 业务事实，PostgreSQL shadow 未同步。

## 15A repair dry-run

Artifact:

- `docs/database-migration/reports/stage15A-workbench-remediation-20260520171506.stage15A.repair-dry-run.json`

Dry-run 结论：

- `row_count_bound_passed=true`
- `requires_user_authorization=true`
- `recommended_next_gate=BLOCKED_REPAIR_REQUIRES_USER_AUTHORIZATION`

Bounds:

| Bound | Actual | Limit | Pass |
| --- | ---: | ---: | --- |
| `pair_relations_count` | 146 | 10000 | yes |
| `pair_relation_history_count` | 21 | 50000 | yes |
| `state:workbench_pair_relations` rows | 1 | 1 | yes |

Planned operations if authorized:

| Operation | Count |
| --- | ---: |
| incremental missing relation inserts | 4 |
| incremental relation updates | 0 |
| incremental relation deletes | 0 |
| full rebuild relations | 146 |
| delete current history rows | 17 |
| insert current history rows | 21 |
| upsert snapshot fallback | 1 |

Recommended repair strategy:

`transactional_full_rebuild_workbench_tables_and_snapshot_from_current_app_mongo_snapshot`

Reason:

- It keeps `app.workbench_pair_relations`, `app.workbench_pair_relation_history`, and `state:workbench_pair_relations` fallback snapshot aligned with the same current app Mongo read-only snapshot.
- It avoids partial relation/history inconsistency.
- Counts are small and within bounds.

## Production write scope requiring authorization

If user authorizes repair, allowed production PostgreSQL write targets are limited to:

- `app.workbench_pair_relations`
- `app.workbench_pair_relation_history`
- `app.app_settings` where `settings_key='state:workbench_pair_relations'`

Forbidden during repair:

- Write app Mongo.
- Touch OA Mongo.
- Write any non-whitelisted PostgreSQL table.
- `drop`, `truncate`, or `alter` any production table.
- Restart or modify `fin-ops.service`.
- Print secrets or complete DB URI.

## Backup and rollback plan

Before any repair execution:

1. Backup `app.workbench_pair_relations`.
2. Backup `app.workbench_pair_relation_history`.
3. Backup `app.app_settings` row where `settings_key='state:workbench_pair_relations'`.
4. Store raw backup only on the server temporary directory.
5. Pull back only backup metadata: path, size, sha256, included tables/rows, created_at.

Rollback:

1. Restore the backed up workbench pair relation tables and snapshot row.
2. Rerun production read-only shadow-read.
3. Do not restart service unless separately authorized.

## Verification completed

Local baseline:

```bash
python -m py_compile backend/src/fin_ops_platform/services/shadow_read_rehearsal.py backend/src/fin_ops_platform/services/shadow_read_psql_store.py backend/src/fin_ops_platform/services/postgres_repositories/workbench.py backend/src/fin_ops_platform/tools/postgres_transform.py
python -m pytest tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_postgres_transform.py tests/test_export_app_mongo.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
```

Results:

- py_compile: passed
- targeted migration tests: `34 passed, 4 subtests passed`
- PostgreSQL regression matrix: `32 passed, 11 skipped, 5 warnings, 10 subtests passed`
- app check: `status=ready`, `storage.backend=local_pickle`

Full `python -m pytest -q` was not rerun after diagnostics because no code changed and the stage is blocked before production repair authorization.

## Current status

15A has closed the root-cause investigation and dry-run portion. It has not closed the full remediation because production PostgreSQL write authorization must be refreshed after live drift changed the dry-run scope.

## Authorization revalidation on 2026-05-20 17:33 CST

Before executing the previously authorized repair, production read-only diagnostics were rerun. The counts had changed:

| Metric | Authorized dry-run | Revalidated current state |
| --- | ---: | ---: |
| app Mongo `pair_relations_count` | 146 | 147 |
| app Mongo `pair_relation_history_count` | 21 | 22 |
| PostgreSQL `pair_relations_count` | 142 | 142 |
| PostgreSQL `pair_relation_history_count` | 17 | 17 |
| `missing_in_shadow_count` | 4 | 5 |
| `history_length_delta` | 4 | 5 |

New artifacts:

- `docs/database-migration/reports/stage15A-workbench-remediation-20260520173336.stage15A.workbench-diagnostics.json`
- `docs/database-migration/reports/stage15A-workbench-remediation-20260520173336.stage15A.repair-dry-run.json`

Refreshed dry-run result:

- `row_count_bound_passed=true`
- `root_cause_classification=runtime_drift`
- `recommended_next_gate=BLOCKED_REPAIR_REQUIRES_USER_AUTHORIZATION`

Refreshed planned operations:

| Operation | Count |
| --- | ---: |
| incremental missing relation inserts | 5 |
| incremental relation updates | 0 |
| incremental relation deletes | 0 |
| full rebuild relations | 147 |
| delete current history rows | 17 |
| insert current history rows | 22 |
| upsert snapshot fallback | 1 |

No production PostgreSQL write, backup, restore, service restart, app Mongo write, or OA Mongo access was executed during this revalidation.

## Main merge and post-main revalidation on 2026-05-20 17:41 CST

Current worktree branch `codex/db-migration` was fast-forwarded to local `main` commit `5cdad9cc` and the migration-stage worktree changes were restored without Git conflicts.

Main changes relevant to migration:

- new pending invoice workflow;
- new `pending_invoice_manual_invoice_commands` app Mongo collection path;
- app settings extensions for `bank_transaction_tags` and `pending_invoice_tag_groups`;
- workbench write paths can continue producing `workbench_pair_relations` and relation history.

Local verification after main merge:

```bash
python -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/state_store.py backend/src/fin_ops_platform/services/pending_invoice_service.py backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/services/postgres_repositories/workbench.py backend/src/fin_ops_platform/tools/postgres_transform.py
python -m pytest tests/test_pending_invoice_service.py tests/test_pending_invoice_api.py tests/test_app_settings_service.py tests/test_bank_transaction_category_service.py tests/test_shadow_read_rehearsal.py tests/test_state_store_diff.py tests/test_postgres_transform.py tests/test_export_app_mongo.py tests/test_postgres_repositories_core.py tests/test_postgres_repositories_boundaries.py -q
python -m pytest tests/test_state_store_contract.py tests/test_postgres_state_store.py tests/test_app_postgres_mode.py tests/test_postgres_test_utils.py tests/test_postgres_state_store_integration.py tests/test_app_postgres_mode_integration.py tests/test_postgres_migrations.py tests/test_runtime_state_policy.py tests/test_stage15_runtime_tools.py -q
PYTHONPATH=backend/src python -m fin_ops_platform.app.main --check
```

Results:

- py_compile: passed
- pending-invoice plus migration targeted tests: `85 passed, 5 warnings, 4 subtests passed`
- PostgreSQL/runtime migration tests: `48 passed, 11 skipped, 5 warnings, 26 subtests passed`
- app check: `status=ready`, `storage.backend=local_pickle`

Post-main production read-only artifacts:

- `docs/database-migration/reports/stage15A-post-main-revalidation-20260520174147.stage15A.workbench-diagnostics.json`
- `docs/database-migration/reports/stage15A-post-main-revalidation-20260520174147.stage15A.repair-dry-run.json`
- `docs/database-migration/reports/stage15A-post-main-revalidation-20260520174147.stage15A.main-new-state-diagnostics.json`

Post-main workbench counts:

| Metric | Post-main current state |
| --- | ---: |
| app Mongo `pair_relations_count` | 150 |
| app Mongo `pair_relation_history_count` | 25 |
| PostgreSQL `pair_relations_count` | 142 |
| PostgreSQL `pair_relation_history_count` | 17 |
| `missing_in_shadow_count` | 8 |

Post-main refreshed dry-run:

| Operation | Count |
| --- | ---: |
| incremental missing relation inserts | 8 |
| incremental relation updates | 0 |
| incremental relation deletes | 0 |
| full rebuild relations | 150 |
| delete current history rows | 17 |
| insert current history rows | 25 |
| upsert snapshot fallback | 1 |

Post-main app-owned new-state diagnostics:

| Item | Result |
| --- | --- |
| app Mongo `pending_invoice_manual_invoice_commands` count | 0 |
| PostgreSQL table `app.pending_invoice_manual_invoice_commands` | absent |
| app settings `bank_transaction_tags` present in production state | no |
| app settings `pending_invoice_tag_groups` present in production state | no |

Impact:

- 15A workbench repair can still proceed after refreshed authorization, because pending invoice command count is currently 0 and the workbench repair scope remains app-owned workbench state.
- The overall Mongo-to-PostgreSQL migration is no longer complete against post-main code until pending invoice command persistence and new settings fields are explicitly mapped into PostgreSQL schema/export/transform/repository/shadow-read coverage.
- Because production workbench writes continue during normal use, repair authorization should be bound to a fresh dry-run and executed in a low-write or temporarily quiesced window. If final pre-write counts change again, repair must stop and refresh the dry-run again.

Historical authorization sequence before execution:

- initial dry-run authorization target: `stage15A-workbench-remediation-20260520171506.stage15A.repair-dry-run.json`;
- refreshed dry-run authorization target after live drift changed: `stage15A-workbench-remediation-20260520173336.stage15A.repair-dry-run.json`;
- final post-main refreshed authorization target: `stage15A-post-main-revalidation-20260520174147.stage15A.repair-dry-run.json`.

The final target above is the one actually executed after user authorization.

## Authorized production repair on 2026-05-20 17:47 CST

User authorization:

> Execute 15A production PostgreSQL workbench repair using post-main refreshed dry-run report `stage15A-post-main-revalidation-20260520174147.stage15A.repair-dry-run.json`, only writing `app.workbench_pair_relations`, `app.workbench_pair_relation_history`, and `app.app_settings` where `settings_key='state:workbench_pair_relations'`.

Final pre-write revalidation:

- run id: `stage15A-post-main-repair-20260520174744`
- app Mongo workbench counts still matched the authorized post-main dry-run:
  - `pair_relations_count=150`
  - `pair_relation_history_count=25`
  - `missing_in_shadow_count=8`
- row bounds passed.

Production PostgreSQL backup metadata:

- artifact: `docs/database-migration/reports/stage15A-post-main-repair-20260520174744.stage15A.pg-backup.json`
- raw backup files remain server-local and are not committed to the repo.

Backup row counts:

| Target | Rows |
| --- | ---: |
| `app.workbench_pair_relations` | 142 |
| `app.workbench_pair_relation_history` | 17 |
| `app.app_settings` `state:workbench_pair_relations` | 1 |

Backup files:

| Target | Size | SHA-256 |
| --- | ---: | --- |
| workbench tables SQL dump | 406161 bytes | `ded52245ee0df5d0eeee5a52453eb2aafa87fa2d3dee0ecf2c61846c8b635f2d` |
| app settings snapshot CSV | 255743 bytes | `caf887d483064de29d625bd3c84a1dc722731ddd947f5803329cae5d8cd0a4f4` |

Repair execution artifact:

- `docs/database-migration/reports/stage15A-post-main-repair-20260520174744.stage15A.repair-result.json`

Repair result:

| Metric | Result |
| --- | --- |
| `repair_executed` | `true` |
| `returncode` | `0` |
| service before | `active`, `MainPID=452671` |
| service after | `active`, `MainPID=452671` |

Post-repair PostgreSQL counts:

| Target | Rows |
| --- | ---: |
| `app.workbench_pair_relations` | 150 |
| `app.workbench_pair_relation_history` | 25 |
| `app.app_settings` `state:workbench_pair_relations` | 1 |

Execution note:

- The first SQL attempt failed before writes because the PostgreSQL server did not provide `jsonb_object_length`; the guard query was replaced with `jsonb_object_keys` counting.
- A later repair pass exposed a text-mode JSON escape handling issue in the repair transport. The final successful repair used UTF-8 JSON payloads and revalidated against production shadow-read.
- These issues were confined to the repair execution script path; the final persisted counts and shadow-read result below are the accepted evidence.

## Post-repair production verification

Post-repair shadow-read artifact:

- `docs/database-migration/reports/stage15A-post-main-repair-20260520174744.stage15A.shadow-read-after.json`

Shadow-read summary:

| Metric | Result |
| --- | ---: |
| `gate_recommendation` | `PARTIAL` |
| compared domains | 7 |
| matched domains | 5 |
| mismatched domains | 2 |
| primary errors | 0 |
| shadow errors | 0 |
| P0 mismatches | 0 |
| P1 mismatches | 0 |
| P2 mismatches | 23 |

Workbench domain result:

| Metric | Result |
| --- | ---: |
| domain | `workbench_pair_relations` |
| status | `matched` |
| mismatch count | 0 |
| P0 | 0 |
| P1 | 0 |
| P2 | 0 |

Runtime policy after repair:

- artifact: `docs/database-migration/reports/stage15A-post-main-repair-20260520174744.stage15A.runtime-policy-after.json`
- `gate_recommendation=PASS`
- `blocked_unknown_count=0`

Runtime policy classification counts:

| Classification | Count |
| --- | ---: |
| `cleanup_candidate` | 11 |
| `rebuildable` | 112 |
| `retention_only` | 34 |

Runtime state mismatch counts:

| Mismatch type | Count |
| --- | ---: |
| `missing_in_primary` | 11 |
| `missing_in_shadow` | 35 |
| `different` | 0 |

## Current status after authorized repair

15A is complete for the stage 15 blocker it was created to remediate:

- stage 15 workbench `P0` mismatch is resolved;
- production workbench shadow-read is matched;
- conservative shadow-read has `P0=0` and `P1=0`;
- runtime state has no `blocked_unknown` after policy classification;
- no OA Mongo access or mutation was performed;
- app Mongo remained read-only;
- production service was not restarted or modified.

The next migration step can retry stage 15 production controlled mirror-write rehearsal, but it should start with the same preflight discipline:

1. Run production read-only shadow-read immediately before mirror-write.
2. Rerun runtime policy classification on live `background_jobs` and `app_health_alerts`.
3. Stop if any `P0`, `P1`, or `blocked_unknown` appears.
4. Treat post-main pending invoice command persistence as a separate migration coverage gap before declaring the whole Mongo-to-PostgreSQL migration complete.
