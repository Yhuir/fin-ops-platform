# 2026-06-12 生产同步 Repair 执行报告

## 范围

- 目标：发布包含 current-effective App Status、repair manifest 和 production dry-run SQL 修复的 release，执行受控 `cost_statistics` legacy scope repair，并验证 replacement scope 真实收敛。
- Release：`main-b9c31cf4-stage4-202606122310`
- Commit：`b9c31cf43f3b37c09a8dec47e08524f82407be09`
- 生产脚本：`scripts/check-read-model-scope-contracts.py`
- 原始运行产物保存在生产机 `/tmp/finops-stage4-20260612T225927+0800-*`。该路径只作审计定位，不作为长期事实源。

本次没有启用 RabbitMQ real consumers、Redis fresh-cache、PgBouncer、Prometheus/Grafana、分区或新增索引；这些仍属于后续性能阶段。

## 执行前 Gate

发布前本地验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v`
- `PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help`
- `bash scripts/verify.sh docs`

发布结果：

- `./scripts/deploy-oa.sh --release-name main-b9c31cf4-stage4-202606122310` 成功。
- 发布迁移执行 `0067 app_status_current_effective_outbox_index`。
- `/health/ready` 返回 `ready`。
- `runtime_release.consistent=true`，运行目录为 `/opt/fin-ops/releases/main-b9c31cf4-stage4-202606122310/src`。

dry-run gate：

| 指标 | 值 |
|---|---:|
| `violation_count` | 9 |
| `current_uncovered_outbox_failure_count` | 0 |
| `covered_historical_outbox_failure_count` | 10 |
| `repair_manifest.items` | 19 |

dry-run 分类：

- legacy `cost_statistics` dirty scope：3 条，scope 为 `all`、`2026-03`、`2026-04`。
- legacy `cost_statistics` outbox dead-letter：3 条，scope 为 `all`、`2026-03`、`2026-04`。
- legacy `cost_statistics` readiness failed：3 条，scope 为 `all`、`2026-03`、`2026-04`。
- 已覆盖历史 outbox failure：10 条，均已有 later done 或 fresh readiness 证明。
- replacement scope：`active:all`、`all:all`、`active:2026-03`、`all:2026-03`、`active:2026-04`、`all:2026-04`。

因为 `current_uncovered_outbox_failure_count=0`，允许执行 `--apply`。如果该值非 0，本阶段必须停止，不能删除当前真实 blocker。

## Apply 结果

命令：

```bash
PYTHONPATH="$RELEASE/backend/src" /opt/fin-ops/venv/bin/python scripts/check-read-model-scope-contracts.py \
  --apply \
  --reason production_scope_contract_repair \
  --json
```

结果：

| 项目 | 值 |
|---|---:|
| 删除 `job.read_model_dirty_scopes` legacy 行 | 3 |
| 删除 `job.outbox_events` legacy 行 | 3 |
| 删除 `read_model.app_status_readiness` legacy 行 | 3 |
| replacement enqueue | 6 |
| repair audit event | `98e118a0-0209-4dc0-8ad6-56d30e4e9043` |

本次没有手工写入 `fresh` readiness。replacement scope 通过 `ReadModelRefreshGateway` 入队，由 worker 真实重建后发布 readiness。

回滚口径：

- Release 回滚走 `finops-deploy-control rollback` 或部署脚本既有回滚流程。
- 数据回滚以 apply JSON 中 `repair_manifest.items[].row` 为准恢复被删除行。
- replacement enqueue 已投递的事件回滚前必须先检查最新 dirty/outbox/readiness，避免回放已被真实 fresh 覆盖的旧状态。
- 不允许通过批量改 `read_model.app_status_readiness.status='fresh'` 伪造恢复。

## 收敛验证

repair 后第一次 post-check：

| 指标 | 值 |
|---|---:|
| `violation_count` | 0 |
| `cost_statistics_legacy_dirty_scopes` | 0 |
| `cost_statistics_legacy_outbox_events` | 0 |
| `cost_statistics_legacy_readiness_rows` | 0 |
| `current_uncovered_outbox_failure_count` | 0 |
| `replacement_scope_keys` | 0 |

worker 收敛后只读数据库验证：

| 指标 | 值 |
|---|---:|
| `job.read_model_dirty_scopes` 非 `done` | 0 |
| read model refresh outbox active 非 `done/dead_lettered` | 0 |
| `read_model.app_status_readiness` 非 `fresh` | 0 |

6 个 replacement scope 的最新 dirty/outbox 状态均为 `done`：

- `active:all`
- `all:all`
- `active:2026-03`
- `all:2026-03`
- `active:2026-04`
- `all:2026-04`

`/health/ready` 最终摘要：

| 指标 | 值 |
|---|---:|
| status | `ready` |
| `queue_backlog.dead_lettered` | 10 |
| `queue_backlog.done` | 35616 |
| `dirty_scopes.done` | 30393 |
| `failed_jobs` | 10 |
| `stale_dirty_scope_count` | 0 |
| `missing_required_worker_count` | 0 |
| `stale_required_worker_count` | 0 |
| `mismatched_required_worker_count` | 0 |
| `rabbitmq_unpublished_backlog` | 0 |
| `read_model_refresh_failure_rate` | 0.000281 |
| `read_model_refresh_duration_ms.p95` | 17764.1864 |

`/api/app-health` 在未认证请求下返回 401，符合认证边界；页面 App Status 的事实源通过 `read_model.app_status_readiness`、dirty/outbox 和 `/health/ready.runtime_infrastructure` 验证。

## 结论

本阶段完成了“旧 legacy scope 污染导致 App Status 长期失败”的生产修复闭环：

- legacy cost scope 违规从 9 降为 0。
- current uncovered failure 为 0，未删除真实当前 blocker。
- replacement scope 全部由 worker 真实完成，readiness 非 fresh 为 0。
- stale dirty scope 从基线的 3 降为 0。

这不是“几秒内全部同步”性能闭环的完成态。剩余 10 条 dead-letter 是已被 later done/fresh readiness 覆盖的历史 outbox failure，当前不应阻断页面显示已同步，但仍会让 `/health/ready.runtime_infrastructure.failed_jobs=10`。如果目标是运维面板也完全没有失败计数，下一阶段应使用独立的受控 dead-letter resolve/归档流程处理，不能在本阶段顺手删除。

## 后续阶段

1. RabbitMQ real consumers：当前 RabbitMQ 仍只是 publish/wakeup 边界，management metric 返回 404；需要启用真实 consumer 和监控，降低 wakeup 延迟。
2. Redis fresh-cache：只缓存 fresh gate 之后 payload，优先覆盖页面首包慢且重复读取的 read model。
3. PostgreSQL 索引/分区：基于基线 EXPLAIN 和生产 pg_stat/表大小做，不做盲目分区。
4. Prometheus/Grafana 或 OpenTelemetry：把 enqueue-to-fresh latency、pending age、failure rate、readiness non-fresh 和 API p95 做成持续 SLO。
5. Worker shutdown/reclaim：本次发布后观察到 worker 在处理事件时被 systemd 重启，outbox 进入 `processing` 并依赖 300s lock timeout 回收；这是“打开 app 后同步几分钟”的直接风险。后续 Stage 6 已将 shutdown lease release 纳入 worker/repository 边界。

## Stage 5：covered historical dead-letter 归档

Release：`main-d38edfa9-stage5-202606122335`

Commit：`d38edfa93c7211654c9df71f02974c6b7cbd011a`

本阶段新增并发布 `runtime_queue_ops resolve-covered-dead-letters`：

- dry-run/execute 双模式。
- 每条 dead-letter 必须有同一 `tenant_id + read_model_key + scope_type + scope_key` 的 `fresh_readiness`，或同一 outbox scope 在该 dead-letter 之后已有 `done` 事件。
- 同一 `tenant_id + scope_type + scope_key` 不能存在 `pending`、`processing` 或 `failed` dirty scope。
- execute 复用 `RuntimeQueueRepository.resolve_dead_letter_event()`，把事件标为 `done`，并写 `raw_payload.operator_resolution`，不直接 SQL 改状态。

本地验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue_ops tests.test_runtime_queue -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters --help`
- `bash scripts/verify.sh docs`

生产 dry-run：

| 指标 | 值 |
|---|---:|
| candidate_count | 10 |
| eligible_count | 10 |
| resolved_count | 0 |

10 条候选全部有 `fresh_readiness` 与 `later_done` proof，且 `active_dirty_count=0`。范围为：

- `workbench.read_model.refresh`：`all` 1 条。
- `output_invoice_collection.read_model.refresh`：`2026-01`、`2026-02`、`2026-03` 共 9 条历史重复 dead-letter。

生产 execute：

| 指标 | 值 |
|---|---:|
| candidate_count | 10 |
| eligible_count | 10 |
| resolved_count | 10 |
| reason | `readiness_converged_obsolete_dead_letter` |

执行后 post dry-run：

| 指标 | 值 |
|---|---:|
| candidate_count | 0 |
| eligible_count | 0 |
| resolved_count | 0 |

最终生产快照：

| 指标 | 值 |
|---|---:|
| read model outbox 非 `done` | 0 |
| dirty scope 非 `done` | 0 |
| readiness 非 `fresh` | 0 |
| `operator_resolution` 记录数 | 10 |
| `/health/ready.failed_jobs` | 0 |
| `/health/ready.stale_dirty_scope_count` | 0 |
| required worker missing/stale/mismatch | 0 |
| `read_model_refresh_failure_rate` | 0.0 |

本阶段把 runtime failure count 清到了 0，但仍未达到“几秒内全部同步”的性能闭环。发布期间观察到 3 个正常 refresh scope 在 worker 重启后留在 `processing`，直到 lock timeout/reclaim 后才收敛：

- `workbench:2026-01`
- `input_invoice_usage:2026-03`
- `cost_statistics:active:2026-04`

这些事件没有失败，最终也真实完成；但它们暴露出当前 worker shutdown/reclaim 设计会制造分钟级尾延迟。下一阶段必须优先修复 worker graceful shutdown、processing lease 释放或 deploy worker restart 顺序，再谈 RabbitMQ/Redis/索引性能优化。

## Stage 6：worker shutdown lease release

本阶段修复 Stage 5 发现的 300s lock-timeout 尾延迟风险：

- `RuntimeQueueRepository.release_event()`：只释放当前 `worker_id` 持有的 `processing` outbox event，恢复为 `pending`、`available_at=now()`、清理 lock、回退本次 claim 增加的 `attempts`，并写入 `raw_payload.runtime_shutdown_release`。
- `RuntimeWorker`：在 `run_forever()` 期间安装 `SIGTERM/SIGINT` handler；handler 中断当前处理，worker 释放已 claim 的事件，记录 `stopping/stopped` heartbeat 后退出。
- 如果 queue 实现没有 `release_event()`，worker 仍会走原有 retry failure fallback，避免事件无限卡住。

这项修复针对发布、systemd stop 或滚动重启造成的 `processing` lease 残留。它不能缩短单个真实重型 rebuild 的执行时间；后者仍需要 RabbitMQ real consumers、索引/分区、增量 worker 和 Redis fresh-cache 阶段继续优化。
