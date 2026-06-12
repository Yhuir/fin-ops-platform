# Runtime 同步基线 - 2026-06-12

本报告是生产只读采集的红acted摘要，不包含数据库连接串、密码、token 或业务 payload。原始 JSON 仅保存在生产机 `/tmp/finops-stage3-*`，不提交仓库。

## 采集范围

- 时间：2026-06-12 22:35-22:50 CST。
- 生产 API release：`main-fe346ce1-20260612204127`。
- 诊断代码：本地 `main` 的 `35225788` 加本阶段 SQL pattern 修复，解压到生产机 `/tmp/finops-stage3-head` 后只读执行。
- 只读命令：`scripts/check-read-model-scope-contracts.py --json`、PostgreSQL 聚合查询、`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`、`/health`、systemd status、worker `--check`。
- 禁止动作：未执行 `--apply`，未 delete/update/insert 业务或 runtime 表，未重启服务。

## SLO 基线

目标 SLO：

- 页面首包 p95 < 1s。
- 轻量 read model enqueue-to-fresh p95 < 3s。
- 重型 workbench 局部收敛 p95 < 10-15s。

当前证据：

| 指标 | 当前值 | 判定 |
| --- | ---: | --- |
| `/api/workbench/summary` p95 | 130ms | 达标 |
| `/api/workbench/groups` p95 | 1036ms | 略超 1s 首包目标 |
| `/api/input-invoice-usage/rows/.../relation-details` p95 | 42.8s | 严重不达标，且单请求约 1129 次 DB query |
| `no_oa_bank_batch.read_model.refresh` p95 | 2.877s | 达标 |
| `workbench_relation.read_model.refresh` p95 | 7.142s | 超轻量 3s，但仍在较低范围 |
| `workbench.read_model.refresh` p95 | 356.366s | 不达标，重型链路需要拆分/预热/worker 策略 |
| `cost_statistics.read_model.refresh` p95 | 188.205s | 不达标，父 scope/shard 链路仍慢 |
| `pending_invoice.read_model.refresh` p95 | 113.974s | 不达标 |

说明：read model p95 使用最近 7 天 `job.outbox_events.processed_at - created_at`，它包含 PostgreSQL polling 等待、积压和执行时间，不等同纯 SQL 执行时间。

## 当前 blocker

`check-read-model-scope-contracts.py --json` 结果：

- `ok=false`
- `violation_count=9`
- `current_uncovered_outbox_failure_count=0`
- `covered_historical_outbox_failure_count=10`

当前没有未覆盖的真实 read model failure。现有红/失败主要来自历史 runtime 状态污染：

| 类型 | 数量 | scope |
| --- | ---: | --- |
| legacy `cost_statistics` dirty scope | 3 | `2026-03`, `2026-04`, `all` |
| legacy `cost_statistics` dead-letter outbox | 3 | `2026-03`, `2026-04`, `all` |
| legacy `cost_statistics` failed readiness | 3 | `2026-03`, `2026-04`, `all` |
| covered historical outbox failure | 10 | `output_invoice_collection` 9 条、`workbench all` 1 条 |

replacement scope：

- `active:all`
- `all:all`
- `active:2026-03`
- `all:2026-03`
- `active:2026-04`
- `all:2026-04`

结论：下一阶段应先发布包含 current-effective App Status 和 repair manifest 的代码，再执行受控 repair apply。该动作会清理 legacy cost runtime 行并补投规范 scope，不应删除 current blocker，也不应手工写 fresh readiness。

## Queue 与 readiness

PostgreSQL durable queue：

- `job.read_model_dirty_scopes`
  - `done=30327`
  - `pending=3`
  - pending 最老更新时间：2026-06-08 20:45:44 CST
  - pending 全部是 legacy `cost_statistics` scope。
- `job.outbox_events` read model refresh
  - `done=35517`
  - `dead_lettered=13`
  - dead-letter 最老更新时间：2026-06-05 15:12:44 CST
  - 13 条包括 3 条 legacy cost scope 和 10 条已覆盖历史 failure。
- `read_model.app_status_readiness`
  - non-fresh 只有 3 条，全部为 legacy `cost_statistics` failed readiness。

RabbitMQ：

- 当前 `FIN_OPS_QUEUE_BACKEND=postgres`。
- RabbitMQ dispatcher active running，但只是 shadow publisher。
- worker `--check` 显示 `runtime_transport=postgres`，`rabbitmq_configured=false`。
- RabbitMQ server active running。
- `rabbitmqctl list_queues` 在本次采集中 60s 超时，RabbitMQ 管理面观测本身需要修复。

结论：当前慢同步不是 RabbitMQ consumer 缺失单独造成的；生产还没切 real consumers。RabbitMQ real consumers 可以降低 wakeup/polling 延迟，但必须在 legacy repair 和 worker/query瓶颈处理后灰度。

## Worker 与连接数

systemd：

- API、RabbitMQ dispatcher、12 个 `fin-ops-worker@*.service` 均 active/running。
- 最近启动时间：2026-06-12 20:42-20:43 CST。
- 本次采集未见 systemd restart。

DB heartbeat：

- `job.runtime_worker_heartbeats` 保留旧 heartbeat 行，聚合 `max_lag_seconds` 会被历史 worker 污染。
- 当前 systemd 和 worker `--check` 比 heartbeat 表聚合更可信。

PostgreSQL 连接：

- 当前连接数：36。
- `max_connections=100`。
- 当前没有连接数瓶颈证据。

结论：PgBouncer 不是当前第一优先级。后续若启用 RabbitMQ consumers 或提高 worker 并发，再以 `connection_acquire_ms` 和连接数阈值决定是否引入。

## 表和索引体积

最大 read model 表：

| 表 | total | 估算行数 | 备注 |
| --- | ---: | ---: | --- |
| `read_model.workbench_group_rows` | 3.29 GiB | 390k | 主要膨胀点 |
| `read_model.workbench_groups` | 3.05 GiB | 196k | 主要膨胀点 |
| `read_model.workbench_rows` | 2.24 GiB | 335k | 主要膨胀点 |
| `read_model.workbench_snapshots` | 1.25 GiB | 433 | payload 大 |
| `read_model.search_index_rows` | 120 MiB | 1678 | 可接受 |
| `job.outbox_events` | 63 MiB | 35k | 可接受 |

最大索引里存在多条大而未被扫描的索引：

- `workbench_groups_searchable_text_trgm` 676 MiB，`idx_scan=0`。
- `workbench_rows_payload_gin` 322 MiB，`idx_scan=0`。
- `workbench_group_rows_generation_scope_identity_zone_idx` 91 MiB，`idx_scan=0`。
- `workbench_rows_generation_scope_identity_idx` 89 MiB，`idx_scan=0`。

结论：PostgreSQL 分区/索引优化应优先针对 workbench 投影表，而不是全库先分区。先做 query workload 和索引使用分析，删除/替换无用大索引前必须做 impact analysis 和回滚计划。

## EXPLAIN 结果

| 查询 | execution time | 结论 |
| --- | ---: | --- |
| active dirty scopes | 4.798ms | 不是瓶颈 |
| active read model outbox | 13.286ms | 不是瓶颈 |
| non-fresh readiness | 0.051ms | 不是瓶颈 |
| workbench groups `all/paired` 首页诊断查询 | 1180.499ms | 与 `/api/workbench/groups` p95 超 1s 一致，需要专门优化 |

`pg_stat_statements` 本次无法读取：当前账号返回 `permission denied to examine "shared_preload_libraries"`。长期观测需要调整权限或提供只读观测账号，否则无法持续追踪 top SQL。

## 方案优先级判断

| 方案 | 本轮结论 | 理由 |
| --- | --- | --- |
| 受控 repair apply | 立即需要 | 当前 App Status 失败主要来自 legacy cost scope 和历史 dead-letter 污染 |
| RabbitMQ real consumers | 需要，但不是第一步 | 当前 worker 仍 PostgreSQL polling；可降低 wakeup latency，但不能修复 legacy failure 或慢 SQL |
| Redis fresh-cache | 需要按页面评估 | workbench summary 已较快；groups 和 relation-details 需要先确认 fresh payload/key/query shape |
| PgBouncer | 暂不优先 | 36/100 连接，无连接数瓶颈证据 |
| Prometheus/Grafana 或 OpenTelemetry | 需要 | `/health` 是进程内窗口，pg_stat_statements 不可用；缺少持续 p95/lag/failure rate |
| PostgreSQL 索引优化 | 需要 | workbench 大表/大索引明显；需先按 workload 做 impact analysis |
| PostgreSQL 分区 | 暂不作为第一刀 | 当前最大压力是 workbench generation/payload/index 体积；先优化 retention、索引、query，再决定分区 |

## 下一阶段

1. 发布包含 `cd39b3a4`、`35225788` 和本阶段 SQL pattern 修复的 release。
2. 在新 release 上重新运行 `scripts/check-read-model-scope-contracts.py --json`，确认结果仍为 `current_uncovered_outbox_failure_count=0`。
3. 执行受控 `--apply --reason production_scope_contract_repair`，保存 audit id、cleanup、replacement enqueue 和 rollback manifest。
4. 等待 replacement scopes 收敛，重新采集 dirty/outbox/readiness/App Status。
5. 若 App Status 仍失败，进入 current blocker 修复；若 App Status 变绿，再进入 RabbitMQ real consumers 和 workbench/input-invoice 页面性能优化。
