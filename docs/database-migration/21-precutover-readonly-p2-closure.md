# 阶段 21：Pre-cutover read-only validation and retention P2 closure

执行时间：2026-05-20

Gate：`READ_ONLY_GATE_PASS_RETENTION_P2_ACCEPTED`

## 阶段边界

- 本阶段只执行 production read-only shadow-read 和 runtime policy classification。
- 本阶段不执行 read switch。
- 本阶段不执行 cutover。
- 本阶段不写 production PostgreSQL。
- 本阶段不写 app Mongo `fin_ops_platform_app`。
- 本阶段不读取、写入或触碰 OA Mongo `form_data_db.form_data`。
- 本阶段不修改或重启 production `fin-ops.service`。

## 背景

阶段 20 已完成用户单独授权后的 controlled runtime mirror-write execute：

- `background_jobs` 已 matched。
- `app_health_alerts` 仍有 retention-only P2。
- post-execute runtime policy 无 `blocked_unknown`。

进入 read switch 或 cutover 前仍需要重新执行 production read-only shadow-read 和 runtime policy classification；若出现 P0/P1/read error/`blocked_unknown`，必须停止。

## Read-only run

Run id：

- `stage21-precutover-readonly-20260520230248`

Artifacts：

- `docs/database-migration/reports/stage21-precutover-readonly-20260520230248.shadow-read.json`
- `docs/database-migration/reports/stage21-precutover-readonly-20260520230248.runtime-policy.json`
- `docs/database-migration/reports/stage21-precutover-readonly-20260520230248.stage21-summary.json`
- `docs/database-migration/reports/stage21-precutover-readonly-20260520230248.service-before.txt`
- `docs/database-migration/reports/stage21-precutover-readonly-20260520230248.service-after.txt`

## Validation result

| Check | Result |
| --- | --- |
| shadow-read gate | `PARTIAL` |
| shadow-read P0/P1/P2 | `0/0/12` |
| primary errors | `0` |
| shadow errors | `0` |
| mismatched domains | `1` |
| runtime-policy gate | `PASS` |
| `blocked_unknown_count` | `0` |
| app Mongo write | `false` |
| production PostgreSQL write | `false` |
| OA Mongo `form_data_db.form_data` touched | `false` |
| service modified/restarted | `false` |

Domain result：

| Domain | Status | Mismatches | P0 | P1 | P2 |
| --- | --- | ---: | ---: | ---: | ---: |
| `app_settings` | `matched` | `0` | `0` | `0` | `0` |
| `pending_invoice_commands` | `matched` | `0` | `0` | `0` | `0` |
| `background_jobs` | `matched` | `0` | `0` | `0` | `0` |
| `app_health_alerts` | `mismatched` | `12` | `0` | `0` | `12` |
| `workbench_pair_relations` | `matched` | `0` | `0` | `0` | `0` |
| `no_oa_bank_batches` | `matched` | `0` | `0` | `0` | `0` |
| `bank_transaction_categories` | `matched` | `0` | `0` | `0` | `0` |
| `turnover_relations` | `matched` | `0` | `0` | `0` | `0` |

Runtime policy：

| Domain | Primary | Shadow | Classification | Missing/Different |
| --- | ---: | ---: | --- | --- |
| `background_jobs` | `137` | `137` | `rebuildable=114`, `retention_only=23` | `0/0` |
| `app_health_alerts` | `11` | `11` | `retention_only=11` | `0/0` |

## Accepted P2

`app_health_alerts` 的 12 条 P2 为 retention-only runtime alert 字段差异：

- `first_seen_at`
- `last_seen_at`
- `message`
- `recovered_at`

接受理由：

- P0=`0`，P1=`0`。
- primary/shadow 均为 11 条 alert。
- runtime policy 无 missing、无 different、无 `blocked_unknown`。
- `app_health_alerts` 属于 runtime/retention state，不是业务事实源。
- `background_jobs` 已 matched。

该 P2 不阻断下一阶段 read switch / cutover planning，但每次执行型 read switch、cutover 或 service 配置变更前仍必须重新执行 production read-only shadow-read 和 runtime policy classification。

## Service state

`fin-ops.service` before/after had no diff：

| Field | Value |
| --- | --- |
| `MainPID` | `452671` |
| `ExecMainStartTimestamp` | `Wed 2026-05-20 16:07:52 CST` |
| `WorkingDirectory` | `/opt/fin-ops/current` |
| `ActiveState` | `active` |
| `SubState` | `running` |

## Gate

`READ_ONLY_GATE_PASS_RETENTION_P2_ACCEPTED`

阶段 21 完成了阶段 20 execute 后的 production read-only validation。当前 conservative domains 无 P0/P1/read error，runtime policy 无 `blocked_unknown`。剩余 `app_health_alerts` P2 已按 retention-only runtime state 明确接受。继续进入任何执行型 read switch 或 cutover 前，仍必须重新执行 production read-only shadow-read 和 runtime policy classification。
