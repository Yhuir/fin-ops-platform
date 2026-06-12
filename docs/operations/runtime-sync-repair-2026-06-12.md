# 2026-06-12 生产同步 Repair 执行报告

## 范围

- 目标：记录 2026-06-12 生产同步闭环执行过程，从 legacy scope repair 到 RabbitMQ real consumers 切换。
- Stage 4 Release：`main-b9c31cf4-stage4-202606122310`
- Stage 4 Commit：`b9c31cf43f3b37c09a8dec47e08524f82407be09`
- 生产脚本：`scripts/check-read-model-scope-contracts.py`
- 原始运行产物保存在生产机 `/tmp/finops-stage4-20260612T225927+0800-*`。该路径只作审计定位，不作为长期事实源。

Stage 4 没有启用 RabbitMQ real consumers、Redis fresh-cache、PgBouncer、Prometheus/Grafana、分区或新增索引；Stage 7-9 已完成 required RabbitMQ real consumer 切换。Redis fresh-cache、PgBouncer、Prometheus/Grafana、分区和新增索引仍属于后续性能阶段。

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

## Stage 4 后续判断

1. RabbitMQ real consumers：Stage 4 时 RabbitMQ 仍只是 publish/wakeup 边界，management metric 返回 404；已在 Stage 7-9 启用真实 consumer 和监控。
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

Release：`main-3933b00f-stage6-202606122329`

Commit：`3933b00ffc6868df382ad8f2cb54caeb61b23463`

本阶段修复 Stage 5 发现的 300s lock-timeout 尾延迟风险：

- `RuntimeQueueRepository.release_event()`：只释放当前 `worker_id` 持有的 `processing` outbox event，恢复为 `pending`、`available_at=now()`、清理 lock、回退本次 claim 增加的 `attempts`，并写入 `raw_payload.runtime_shutdown_release`。
- `RuntimeWorker`：在 `run_forever()` 期间安装 `SIGTERM/SIGINT` handler；handler 中断当前处理，worker 释放已 claim 的事件，记录 `stopping/stopped` heartbeat 后退出。
- 如果 queue 实现没有 `release_event()`，worker 仍会走原有 retry failure fallback，避免事件无限卡住。

这项修复针对发布、systemd stop 或滚动重启造成的 `processing` lease 残留。它不能缩短单个真实重型 rebuild 的执行时间；后者仍需要 RabbitMQ real consumers、索引/分区、增量 worker 和 Redis fresh-cache 阶段继续优化。

本地验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker tests.test_runtime_queue tests.test_runtime_queue_ops tests.test_rabbitmq_runtime -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.worker --help`
- `bash scripts/verify.sh docs`
- 干净部署 worktree `/tmp/finops-stage6-deploy` 重跑上述 worker/queue/runtime 测试与 docs verify。

生产发布：

- `./scripts/deploy-oa.sh --release-name main-3933b00f-stage6-202606122329` 成功。
- 本阶段没有新增 migration；发布输出中 `0001` 到 `0067` 均为 skipped。
- `/health/ready.runtime_release.consistent=true`，运行目录为 `/opt/fin-ops/releases/main-3933b00f-stage6-202606122329/src`。

发布期间真实验证到 shutdown release path：

- `fin-ops-worker@workbench.service` 在 `23:30:02` 收到 stop，已 claim 的 `workbench.read_model.refresh` 事件 `bcc5d43e-1dfc-4e16-9b36-5fffdf5b6a0d` 记录 `runtime_worker.event_released`，`error=shutdown_signal_15`。
- 同一服务在 `23:30:25` 再次 stop，事件 `57824909-e07b-4054-a6d9-ceb0f7af2162` 同样 release。
- 生产库中带 `raw_payload.runtime_shutdown_release` 的 outbox 记录数为 4。

发布后中间态曾出现后台 workbench refresh 仍在追赶：

| 指标 | 值 |
|---|---:|
| read model outbox 非 `done` | 6 |
| dirty scope 非 `done` | 1 |
| readiness 非 `fresh` | 0 |
| `failed_jobs` | 0 |
| `queue_backlog.pending` | 5 |
| `queue_backlog.processing` | 1 |

这时页面 readiness 已经是 fresh，后台 workbench 重建仍在进行；关键差异是 shutdown 后事件立即回到可 claim 状态，而不是依赖 300s lock timeout。

收敛后最终生产快照：

| 指标 | 值 |
|---|---:|
| `/health/ready.status` | `ready` |
| runtime release | `main-3933b00f-stage6-202606122329` |
| release commit | `3933b00ffc6868df382ad8f2cb54caeb61b23463` |
| `job.outbox_events` read model 非 `done` | 0 |
| `job.read_model_dirty_scopes` 非 `done` | 0 |
| `read_model.app_status_readiness` 非 `fresh` | 0 |
| `/health/ready.failed_jobs` | 0 |
| `/health/ready.stale_dirty_scope_count` | 0 |
| required worker missing/stale/mismatch | 0 / 0 / 0 |
| `read_model_refresh_failure_rate` | 0.0 |
| `read_model_refresh_duration_ms.p95` | 17769.2015 |

Stage 6 剩余风险快照：

- `read_model_refresh_duration_ms.p95` 仍约 17.77s，来自滚动窗口内的重型 workbench refresh；Stage 6 只消除发布/重启导致的分钟级 lease 等待，不代表“几秒内全部同步”性能 SLO 已完成。
- RabbitMQ management metric 当时仍返回 `HTTP Error 404: Not Found`，真实 consumer 与持续观测阶段尚未闭环；该项已在 Stage 7-9 处理。
- workbench 全量/月份 rebuild 的真实性能仍需要基于 EXPLAIN、索引/分区、增量化和 fresh-cache 后续阶段继续优化。

## Stage 7：RabbitMQ required-only preflight 与 topology 补齐

Release：`main-c5454601-stage7-202606122340`

Commit：`c5454601a043b4b504fd0c7e5582f77f68603f9e`

本阶段修复 RabbitMQ 灰度前置检查的范围：

- `run_rabbitmq_staging_preflight` 默认只检查 registry 中 `required=true` 且 `rabbitmq_eligible=true` 的 worker。
- `file-migration`、`bank-account-balance` 等 optional worker 只有显式传 `--include-optional-workers` 才参与检查，避免未启用依赖阻塞 required 队列灰度。
- 文档明确 optional worker 需要先补齐 GridFS、对象存储或专用 dependency 后再启用。

本地验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_rabbitmq_staging_preflight tests.test_rabbitmq_runtime -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.run_rabbitmq_staging_preflight --help`
- `bash scripts/verify.sh docs`

生产发布后 non-destructive preflight：

| 指标 | 值 |
|---|---:|
| status | `pass` |
| `include_optional_workers` | `false` |
| `check_count` | 14 |
| failed | `[]` |

preflight 通过后继续检查 RabbitMQ Management API，发现 `rabbitmq_metric_error=HTTP Error 404: Not Found` 不是权限或 API 不可用，而是部分 event queue / DLQ 尚未由 topology bootstrap 创建。使用 `/etc/fin-ops/fin-ops.rabbitmq-topology.env` 执行 topology apply 后验证：

| 指标 | 值 |
|---|---:|
| missing required queue / DLQ | 0 |
| `rabbitmq_metric_error` | `null` |
| preflight status | `pass` |
| `rabbitmq_queue_depth` | 5280 |
| `rabbitmq_consumer_count` | 0 |

`rabbitmq_queue_depth=5280` 且 `consumer_count=0` 说明 dispatcher shadow publish 已堆积 broker 消息，但 worker 仍未切到 real consumers；这不是失败闭环，只是 Stage 8/9 切换前的预期中间态。

回滚口径：

- Stage 7 代码回滚走 release rollback。
- topology apply 创建 exchange/queue/binding/DLQ，不删除 PostgreSQL durable queue 状态；如需停用 RabbitMQ，可把 worker 保持 `FIN_OPS_QUEUE_BACKEND=postgres`，dispatcher 改回 shadow/off，不需要删除 RabbitMQ 队列。

## Stage 8：共享 RabbitMQ worker 凭据

Release：`main-f4c6208b-stage8-202606122353`

Commit：`f4c6208b1d5fc3066b9b1cfa1ba2d2b1da466bf30`

本阶段把 worker consumer 连接凭据从 per-worker env 中拆出来：

- `fin-ops-worker@.service.example` 在 common/secrets 和 per-worker env 之间加载 `/etc/fin-ops/fin-ops.rabbitmq-worker.env`。
- `/etc/fin-ops/fin-ops.rabbitmq-worker.env` 只保存共享 `RABBITMQ_URL`，不得设置 `FIN_OPS_QUEUE_BACKEND`。
- `/etc/fin-ops/fin-ops.worker.<instance>.env` 仍是单个 worker 是否切到 RabbitMQ 的控制点，只有灰度实例才设置 `FIN_OPS_QUEUE_BACKEND=rabbitmq`。
- 仓库模板不再在每个 worker env example 中放占位 `RABBITMQ_URL`，避免同一 secret 在多处漂移。

本地验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_deploy_oa_script tests.test_rabbitmq_staging_preflight tests.test_rabbitmq_runtime -v`
- `bash scripts/verify.sh docs`

生产操作：

- 创建 `/etc/fin-ops/fin-ops.rabbitmq-worker.env`，权限 `0600 root root`。
- 轮换 worker 专用 RabbitMQ 凭据，并只把连接串写入上述 root-only 文件。
- 短时启动 `turnover-ledger` consumer smoke，验证 worker 可以读取共享 env 并连接 broker。

Stage 8 smoke 暴露出 `timeout` 触发 `SIGINT` 时 consumer 会打印 `KeyboardInterrupt` traceback；该行为不影响数据一致性，但会污染 systemd/运维日志，因此进入 Stage 9 修复。

回滚口径：

- 删除或清空 `/etc/fin-ops/fin-ops.rabbitmq-worker.env` 后，所有仍使用 `FIN_OPS_QUEUE_BACKEND=postgres` 的 worker 不受影响。
- 已切到 RabbitMQ 的 worker 回滚时先把 per-worker env 改回 `FIN_OPS_QUEUE_BACKEND=postgres`，再重启对应 unit。

## Stage 9：RabbitMQ consumer clean interrupt 与 required worker cutover

Release：`main-99a98feb-stage9-202606130000`

Commit：`99a98feb3895141db5e5f1347d29cf38f4c313f5`

本阶段完成 RabbitMQ real consumers 的 required worker 切换：

- `RabbitMqConsumer.consume_forever()` 捕获 `KeyboardInterrupt`，记录 `stopped` 后干净返回，避免受控 smoke 或 systemd stop 打印 traceback。
- 发布后重跑 `turnover-ledger` 短时 smoke：`timeout` 返回 `124` 属于受控超时退出；没有 traceback、没有残留进程，目标队列保持 `messages=0 / consumers=0 / unacked=0`。
- 将 required RabbitMQ eligible worker 的 `/etc/fin-ops/fin-ops.worker.<instance>.env` 切换为 `FIN_OPS_QUEUE_BACKEND=rabbitmq` 并重启：
  - `oa-sync`
  - `workbench`
  - `workbench-relation`
  - `bank-detail`
  - `turnover-ledger`
  - `search-pending`
  - `invoice-lifecycle`
  - `invoice-usage-collection`
  - `cost-tax`
  - `import`
  - `no-oa-bank-batch`
- `workbench-matching` 继续使用 PostgreSQL queue；它不是 RabbitMQ eligible refresh worker。
- optional `bank-account-balance`、`file-migration` 未启用。

生产 env 备份：

| 备份 | 路径 |
|---|---|
| required cutover 前 per-worker env | `/etc/fin-ops/rabbitmq-required-cutover-backup-20260613000902` |
| 单独 turnover-ledger smoke 前备份 | `/etc/fin-ops/rabbitmq-worker-cutover-backup-20260613000651` |

切换后 RabbitMQ broker 检查：

| 指标 | 值 |
|---|---:|
| required event queue depth | 0 |
| required event queue consumers | 每个 required queue 1 |
| total RabbitMQ depth | 0 |
| RabbitMQ DLQ | 0 |
| `/health/ready.rabbitmq_consumer_count` | 15 |
| `/health/ready.rabbitmq_queue_depth` | 0 |
| `/health/ready.rabbitmq_dlq_count` | 0 |
| `/health/ready.rabbitmq_metric_error` | `null` |

切换过程中发现 `finops.cost_statistics.read_model.refresh.dlq` 有 2 条 RabbitMQ orphan envelope，但 PostgreSQL `job.outbox_events` 中没有对应 `event_id`。由于 PostgreSQL durable queue 才是事实源，这 2 条 broker-only DLQ 不代表真实 read model blocker。已先导出审计摘要到生产 `/tmp/finops-rabbitmq-cost-statistics-dlq-purge-20260613T001207+0800.json`，再清空该 DLQ。

最终 `/health/ready` 摘要：

| 指标 | 值 |
|---|---:|
| status | `ready` |
| `queue_backlog.done` | 35952 |
| `dirty_scopes.done` | 30684 |
| `failed_jobs` | 0 |
| `rabbitmq_consumer_count` | 15 |
| `rabbitmq_queue_depth` | 0 |
| `rabbitmq_dlq_count` | 0 |
| `rabbitmq_metric_error` | `null` |
| `read_model_refresh_duration_ms.p50` | 377.38ms |
| `read_model_refresh_duration_ms.p95` | 17765.13ms |
| `read_model_refresh_duration_ms.p99` | 38188.05ms |

结论：

- required worker 已从 PostgreSQL polling/wakeup 切到 RabbitMQ real consumer。
- RabbitMQ Management API、queue depth、DLQ 和 consumer count 已纳入 `/health/ready` 可观测闭环。
- PostgreSQL durable queue、dirty scope 和 readiness 全部保持真实收敛；没有通过手工写 fresh 或删除 current blocker 达成绿色状态。

回滚口径：

- 按备份目录恢复 `/etc/fin-ops/fin-ops.worker.<instance>.env`，或逐个把 `FIN_OPS_QUEUE_BACKEND` 改回 `postgres`。
- 重启对应 `fin-ops-worker@<instance>.service`。
- 确认 `/health/ready.runtime_infrastructure` 的 required worker missing/stale/mismatch 为 0，PostgreSQL `job.outbox_events` 与 `job.read_model_dirty_scopes` 没有 active backlog。
- 不需要清空 PostgreSQL durable queue；RabbitMQ 中残留消息只作为 transport envelope 处理，不能作为 read model 状态事实源。

## Stage 10：post-cutover 只读基线

采集时间：2026-06-13 00:20-00:22 CST

采集方式：

- `/health`
- `/health/ready`
- `rabbitmqctl -p /finops list_queues name messages consumers messages_unacknowledged --formatter=json`
- PostgreSQL 只读聚合查询

采集未执行 migration、env 修改、service restart、enqueue、repair 或表写入。

当前稳定性：

| 指标 | 值 |
|---|---:|
| `/health.status` | `ready` |
| `/health/ready.status` | `ready` |
| `job.outbox_events` read model 非 `done` | 0 |
| `job.read_model_dirty_scopes` 非 `done` | 0 |
| `read_model.app_status_readiness` 非 `fresh` | 0 |
| `failed_jobs` | 0 |
| `stale_dirty_scope_count` | 0 |
| required worker missing/stale/mismatch | 0 / 0 / 0 |
| RabbitMQ total depth | 0 |
| RabbitMQ unacked | 0 |
| RabbitMQ DLQ | 0 |
| `/health/ready.rabbitmq_consumer_count` | 15 |
| PostgreSQL active/idle connections | 1 / 17 |

RabbitMQ cutover 后从 `2026-06-13 00:09:00+08` 起还没有新的 `*.read_model.refresh` outbox event，因此不能用该窗口证明 enqueue-to-fresh p95 已达标。当前 24h refresh p95 仍包含 Stage 9 前历史积压和 workbench `all` 重建样本：

| event type | 24h count | p50 | p95 | max |
|---|---:|---:|---:|---:|
| `workbench.read_model.refresh` | 316 | 93.457s | 380.888s | 483.112s |
| `no_oa_bank_batch.read_model.refresh` | 7 | 184.159s | 188.182s | 188.616s |
| `invoice_lifecycle.read_model.refresh` | 61 | 40.165s | 89.613s | 323.114s |
| `oa_pending_payment.read_model.refresh` | 61 | 36.866s | 86.390s | 96.607s |
| `input_invoice_usage.read_model.refresh` | 62 | 41.107s | 85.375s | 317.264s |
| `bank_detail.read_model.refresh` | 20 | 5.881s | 75.784s | 76.253s |
| `output_invoice_collection.read_model.refresh` | 63 | 17.351s | 75.032s | 87.123s |
| `pending_invoice.read_model.refresh` | 291 | 1.385s | 67.341s | 71.212s |
| `tax_offset.read_model.refresh` | 63 | 28.104s | 36.793s | 37.641s |
| `cost_statistics.read_model.refresh` | 157 | 9.498s | 33.080s | 326.411s |
| `search.read_model.refresh` | 15 | 9.269s | 19.131s | 19.437s |
| `workbench_relation.read_model.refresh` | 112 | 2.269s | 5.593s | 7.253s |

表体积仍集中在 workbench projection：

| relation | total size | live rows | idx scans |
|---|---:|---:|---:|
| `read_model.workbench_group_rows` | 3.65GB | 415k | 3.286M |
| `read_model.workbench_groups` | 3.45GB | 208k | 1.681M |
| `read_model.workbench_rows` | 2.54GB | 356k | 2.755M |
| `read_model.workbench_snapshots` | 1.44GB | 462 | 4.761k |

仍存在大而低/零扫描索引，例如：

- `workbench_groups_searchable_text_trgm` 708MB，`idx_scan=0`。
- `workbench_rows_payload_gin` 337MB，`idx_scan=0`。
- `workbench_group_rows_generation_scope_identity_zone_idx` 95MB，`idx_scan=0`。
- `workbench_rows_generation_scope_identity_idx` 93MB，`idx_scan=0`。
- `workbench_group_rows_column_values_gin` 66MB，`idx_scan=0`。

API rolling window 当前最慢 endpoint：

| endpoint | samples | p95 | DB p95 | SQL p95 | DB query p95 |
|---|---:|---:|---:|---:|---:|
| `GET /api/workbench/groups` | 18 | 570.598ms | 256.747ms | 256.483ms | 17 |
| `GET /health/ready` | 11 | 320.297ms | 251.646ms | 251.324ms | 17 |
| `GET /api/app-health` | 512 | 154.363ms | 73.193ms | 72.877ms | 31 |
| `GET /api/workbench/summary` | 9 | 113.021ms | 9.310ms | 9.142ms | 10 |
| `GET /api/workbench/groups/detail` | 16 | 110.957ms | 80.459ms | 42.389ms | 4 |

持续观测缺口：

- `/health.api_performance.endpoints` 以 endpoint 字典 key 暴露标签；采集脚本必须保留 key，不能只取 values。
- `pg_stat_statements` 仍未通过 `shared_preload_libraries` 启用，生产 SQL top list 不可用。
- RabbitMQ 后没有新 refresh 样本，不能只靠“当前无 backlog”宣称 enqueue-to-fresh SLO 已达成。

本地工作树已存在一组未提交 WIP，方向包括 `input_invoice_usage` relation-details 走 SQL read model row、candidate relation 不再标记已付款、多个页面 relation status 展示。相关后端测试已通过：

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_input_invoice_usage_api \
  tests.test_input_invoice_usage_service \
  tests.test_invoice_usage_collection_sql_runtime -v
```

这些 WIP 需要先完成 ownership/impact review、全量相关测试和文档收口后才能提交或部署；不能在未确认范围时直接把整批脏文件带入生产发布。

## 当前闭环状态

已闭环：

- current-effective App Status blocker 只看当前有效 dirty/outbox/readiness，不再被历史 legacy scope 污染。
- legacy `cost_statistics` scope 已受控 repair，并由 replacement scope 真实重建完成。
- covered historical dead-letter 已通过 repository 工具归档，`failed_jobs=0`。
- worker shutdown 不再依赖 300 秒 lock timeout 回收 `processing` lease。
- RabbitMQ topology、Management metrics、required worker real consumers 和 DLQ 清理已完成。

尚未完成“几秒内全部同步”性能 SLO：

- `read_model_refresh_duration_ms.p95` 仍约 17.77s，主要来自滚动窗口里的重型 read model。
- 生产基线中 `/api/input-invoice-usage/rows/.../relation-details` p95 曾达到 42.8s，且单请求约 1129 次 DB query，仍需专门优化。
- Workbench/cost statistics/pending invoice 等重型链路仍需要 EXPLAIN 驱动的索引、分区或增量化评估。
- Redis fresh-cache 还未启用；Prometheus/Grafana 或 OpenTelemetry 长期 SLO 还未替换现有进程内窗口。

下一阶段优先级：

1. 针对 relation-details、workbench groups、cost_statistics、pending_invoice 采集最新 EXPLAIN 和 `pg_stat_statements`/API rolling window，先修最慢读路径和 N+1。
2. 对 workbench 大表和大索引做 impact analysis，先优化查询/索引/retention，再决定是否分区；不做盲目全库分区。
3. 为 fresh gate 后 payload 引入 Redis fresh-cache，确保页面秒开读取的是已通过 readiness/source version 的 snapshot。
4. 接入 Prometheus/Grafana 或 OpenTelemetry，把 enqueue-to-fresh latency、pending age、failure rate、RabbitMQ DLQ、consumer count、API p95 和 DB p95 变成持续告警。
5. 只有当 worker 并发提高后出现连接等待或连接数接近阈值，再启用 PgBouncer；当前 2-3 人使用场景下它不是性能第一瓶颈。
