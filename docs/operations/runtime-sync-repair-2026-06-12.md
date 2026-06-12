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

## Stage 11：candidate relation 与发票使用详情 SQL read model 发布

发布时间：2026-06-13 00:31-00:40 CST

发布版本：

- release：`main-a2a53ada-stage11-202606130031`
- commit：`a2a53adaf460f99bc1b6ae55bcd6c63355d455fa`

本阶段收口 Stage 10 记录的未提交 WIP，目标是把关联候选状态从 `workbench_relation`
read model 规范传播到下游页面，并把 `/api/input-invoice-usage/rows/{row_id}/relation-details`
从请求热路径 live 组装改为 fresh gate 后的单行 SQL read model payload 读取。

已实现的闭环：

- `relationStatus=candidate` 通过 workbench relation distribution 进入银行明细、待找发票、OA 待付款、销项收款、进项发票使用页面。
- candidate relation 可见但不计入确认、已付款、已核销或成本统计 closed totals。
- 发票使用详情在 read model fresh 时读取 `read_model.input_invoice_usage_rows` 单行 payload；missing/stale/source mismatch 时返回 `refreshing` 并入队，不在 API 请求里重建关系链。
- 权限、审计和撤回/配对写操作没有改成前端本地判定；页面秒开只影响读路径，写路径仍走既有后端 service、权限和 audit 链路。

发布前验证：

- `git diff --check`
- `bash scripts/verify.sh docs`
- 相关后端单测：227 tests pass
- 相关前端单测：102 tests pass
- `npm run build`
- `bash scripts/verify.sh backend`：2827 tests pass，25 skipped
- `npm test -- --run`：全量并发运行出现一次 `TaxOffsetPage.test.tsx` 选择表格用例失败；随后单文件和单用例重跑均通过，按现有前端并发 flaky 风险记录。

部署方式：

- 在干净部署工作树 `/tmp/finops-stage11-deploy` 构建前端。
- 执行 `./scripts/deploy-oa.sh --skip-build --release-name main-a2a53ada-stage11-202606130031`。
- migration `0001`-`0067` 均为已应用状态；backend readiness、frontend hash、public session route 检查通过。

生产验证过程：

部署刚完成时出现 7 条下游 read model 暂时非 fresh：

- `invoice_lifecycle`：`2026-03`、`2026-04`、`2026-05`
- `oa_pending_payment`：`2026-03`、`2026-04`、`2026-05`
- `input_invoice_usage`：`2026-04`

这些 failure 的错误原因均为依赖 `workbench_relation` 尚在 refreshing；没有手工改写 readiness。
约 45 秒后 `read_model.app_status_readiness` 非 fresh 收敛为 0，最终 PostgreSQL durable truth
与 RabbitMQ 均收敛：

| 指标 | 值 |
|---|---:|
| `/health/ready.status` | `ready` |
| `job.outbox_events` read model 非 `done` | 0 |
| `job.read_model_dirty_scopes` 非 `done` | 0 |
| `read_model.app_status_readiness` 非 `fresh` | 0 |
| `queue_backlog.done` | 36019 |
| `dirty_scopes.done` | 30743 |
| `failed_jobs` | 0 |
| `stale_dirty_scope_count` | 0 |
| required worker missing/stale/mismatch | 0 / 0 / 0 |
| RabbitMQ queue depth | 0 |
| RabbitMQ unacked | 0 |
| RabbitMQ DLQ | 0 |
| RabbitMQ consumer count | 15 |
| `read_model_refresh_failure_rate` | 0.0 |
| `read_model_refresh_duration_ms.p95` | 17760.733ms |

发票使用详情生产只读 SQL 抽样显示：在 fresh scope 下单行 payload lookup 约 `0.55-0.70ms`，
payload 中包含 OA、银行流水和发票关系结构。未认证访问 `/api/app-health` 返回 401，符合认证边界。

post-deploy 真实 refresh 样本仍未达成“几秒内全部同步”：

| event type | count | p50 | p95 | max |
|---|---:|---:|---:|---:|
| `workbench.read_model.refresh` | 12 | 83.116s | 226.917s | 321.015s |
| `cost_statistics.read_model.refresh` | 15 | 20.101s | 122.919s | 336.419s |
| `invoice_lifecycle.read_model.refresh` | 6 | 81.961s | 95.902s | 96.005s |
| `oa_pending_payment.read_model.refresh` | 6 | 80.629s | 95.885s | 95.984s |
| `input_invoice_usage.read_model.refresh` | 6 | 75.659s | 92.497s | 94.807s |
| `output_invoice_collection.read_model.refresh` | 6 | 40.819s | 83.636s | 85.798s |
| `tax_offset.read_model.refresh` | 6 | 33.173s | 33.536s | 33.558s |
| `workbench_relation.read_model.refresh` | 10 | 8.971s | 15.029s | 15.231s |

结论：

- Stage 11 让 relation-details 详情读路径摆脱 N+1/live assembly，并把 candidate relation 语义纳入 read model 页面闭环。
- 全局 App Status 最终仍是真实 fresh，不是手工假同步。
- 但 post-deploy enqueue-to-fresh 仍有 30-300 秒级样本，主要来自 `workbench` all/month shard、`cost_statistics` 及其下游依赖 fan-out；“几秒内全部同步”SLO 还没有达成。
- 下一阶段必须针对 workbench generation、all scope aggregation、下游 fan-out gating、Redis fresh-cache、EXPLAIN/索引/分区和持续指标系统继续优化。

## Stage 12-14：启动补扫收敛与 scope run 证明

Stage 12 Release：`main-5256ed9f-stage12-202606130053`

Stage 12 Commit：`5256ed9f2210f2e2f39584caa72dbd74fac2a67a`

Stage 12 将 `startup_stale_scan` 从用户可见 read model fan-out 收窄为只标记
`workbench_matching_dirty_scopes`。生产验证显示，发布后没有再由
`startup_stale_scan` 创建 read model outbox 或 read model dirty scope；但该阶段仍会在 API
启动时无条件标记 matching dirty scope，导致历史大月份 matching 重试并触发 statement timeout。

Stage 13 Release：`main-02dc9317-stage13-202606130103`

Stage 13 Commit：`02dc9317f1d2b171ee92f0690fd5eef09421973a`

Stage 13 将启动 matching stale scan 改为默认关闭，只有
`FIN_OPS_STARTUP_WORKBENCH_MATCHING_STALE_SCAN_ENABLED=1` 时才执行；即使启用，也会先通过
`WorkbenchCandidateMatchService.stale_scope_months(...)` 过滤，只标记缺少 fresh proof 的月份。

生产验证：

| 指标 | 值 |
|---|---:|
| `/health.status` | `ready` |
| `job.outbox_events` 非 `done` | 0 |
| `job.read_model_dirty_scopes` 非 `done` | 0 |
| `read_model.app_status_readiness` 非 `fresh` | 0 |
| Stage 13 后 `startup_stale_scan` outbox | 0 |
| Stage 13 后 `startup_stale_scan` read model dirty scope | 0 |
| Stage 13 后 `startup_stale_scan` matching dirty scope | 0 |

Stage 13 之后不再因为每次应用启动或打开页面自动制造新的同步窗口。历史
`startup_stale_scan` matching rows 仍保留：其中 completed 行代表真实完成，failed 行代表大月份
matching 曾经真实超时，不能手工伪造成 fresh。

Stage 14 Release：`main-3d103ceb-stage14-202606130115`

Stage 14 Commit：`3d103ceb193312ee36ee2bb7c35a446f94888372`

Stage 14 修复 PostgreSQL formal read path：`load_workbench_candidate_matches()` 现在从
`job.workbench_matching_dirty_scopes.status='completed'` 恢复 `scope_runs`，使
`WorkbenchCandidateMatchService.is_scope_fresh(...)` 在生产重启后仍能看到 completed scope run proof。
这避免未来显式启用 startup stale scan 时，因为 scope run 只存在于 durable queue 而未载入 service，
误把已完成月份重新标记为 stale。

本地验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_state_store tests.test_workbench_dirty_queue_wiring -v`
- `bash scripts/verify.sh docs`
- `bash scripts/verify.sh backend`

生产验证：

| 指标 | 值 |
|---|---:|
| `/health.status` | `ready` |
| release commit | `3d103ceb193312ee36ee2bb7c35a446f94888372` |
| `queue_backlog.done` | 36021 |
| `dirty_scopes.done` | 30745 |
| `failed_jobs` | 0 |
| `stale_dirty_scope_count` | 0 |
| runtime readiness attention | 0 |
| runtime outbox attention | 0 |
| restored candidate scope runs | 5 |
| restored months | `2025-10`、`2026-04`、`2026-05`、`2026-06`、`2026-07` |

## Stage 15-16：同步 SLO 基线采集器与生产基线

Stage 15 Release：`main-53b148b3-stage15-202606130124`

Stage 15 Commit：`53b148b32ab546ed90d2a7f914991d89acdf377a`

Stage 15 新增 `fin_ops_platform.tools.sync_slo_baseline`，用于从现有
`RuntimeMonitoringRepository`、dashboard metric、PostgreSQL catalog、固定 EXPLAIN probe
采集只读同步 SLO 基线。该工具不写业务数据，不绕过 fresh gate，也不把 API p95 伪装为已采集；
登录态页面/API p95 仍必须单独通过 HTTP/browser 采样补齐。

Stage 15 本地验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_sync_slo_baseline tests.test_runtime_monitoring tests.test_operations_dashboard_service -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.sync_slo_baseline --help`
- `bash scripts/verify.sh docs`
- `bash scripts/verify.sh backend`：2832 tests pass，25 skipped
- deploy worktree 前端 build 通过；仍有既有 CSS minify warning。

Stage 15 生产部署后采集到 baseline JSON：
`/tmp/finops-sync-slo-baseline-stage15-20260613012648.json`。该轮确认队列和 dirty scope
已收敛，但发现 collector 对 `pg_stat_statements` 的 fallback 会吞掉真实错误，并误报 legacy
`total_time` 列不存在。

Stage 16 Release：`main-688ce928-stage16-202606130133`

Stage 16 Commit：`688ce928bb782d6ba9c692009799a0d48689eceb`

Stage 16 将 `pg_stat_statements` 检测改为先读取 `information_schema.columns` 再选择
`total_exec_time` 或 legacy `total_time`，并在 extension 未通过
`shared_preload_libraries` 加载时保留真实错误。第一次发布尝试在本地临时 worktree 构建阶段失败，
原因是该 worktree 没有 `web/node_modules`，没有触达生产；随后复用已验证的 `web/dist` 并通过
`--skip-build` 发布成功。

Stage 16 本地验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_sync_slo_baseline -v`
- `bash scripts/verify.sh backend`：2833 tests pass，25 skipped

Stage 16 生产 baseline JSON：
`/tmp/finops-sync-slo-baseline-stage16-20260613013413.json`。

生产同步基线：

| 指标 | 值 |
|---|---:|
| `failed_jobs` | 0 |
| `stale_dirty_scope_count` | 0 |
| `max_pending_age_seconds` | null |
| `queue_backlog.done` | 36021 |
| `dirty_scopes.done` | 30745 |
| runtime read model attention | 0 |
| runtime outbox attention | 0 |
| required worker missing/stale/mismatch | 0 / 0 / 0 |
| `read_model_refresh_duration_ms.p50` | 377.895ms |
| `read_model_refresh_duration_ms.p95` | 17759.437ms |
| `read_model_refresh_duration_ms.p99` | 38198.219ms |

关键 read model 窗口样本：

| read model | 15m samples | 15m p95 | 1h samples | 1h p95 | historical p95 | stale | unavailable |
|---|---:|---:|---:|---:|---:|---:|---:|
| `workbench` | 0 | null | 6 | 8478.061ms | 7608.166ms | 0 | 0 |
| `workbench_relation` | 0 | null | 4 | 1000.943ms | 2772.275ms | 0 | 0 |
| `invoice_lifecycle` | 0 | null | 6 | 9094.040ms | 5918.287ms | 0 | 0 |
| `input_invoice_usage` | 0 | null | 5 | 8516.291ms | 989.881ms | 0 | 0 |
| `output_invoice_collection` | 0 | null | 3 | 223.817ms | 265.033ms | 0 | 0 |
| `oa_pending_payment` | 0 | null | 5 | 1331.061ms | 944.822ms | 0 | 0 |
| `cost_statistics` | 0 | null | 2 | 2193.815ms | 11038.899ms | 0 | 0 |
| `tax_offset` | 0 | null | 0 | null | 528.776ms | 0 | 0 |
| `bank_detail` | 0 | null | 0 | null | 1866.591ms | 0 | 0 |

PostgreSQL 基线：

| 指标 | 值 |
|---|---:|
| connections total / active / max | 35 / 1 / 100 |
| wait_event non-null connections | 29 |
| `pg_stat_statements` | unavailable |
| `pg_stat_statements` error | `pg_stat_statements must be loaded via shared_preload_libraries` |

最大 read model/job 表：

| table | total size | estimated rows | seq_scan | idx_scan |
|---|---:|---:|---:|---:|
| `read_model.workbench_group_rows` | 3.69GB | 415423 | 78 | 3307110 |
| `read_model.workbench_groups` | 3.50GB | 210220 | 64 | 1692504 |
| `read_model.workbench_rows` | 2.57GB | 358335 | 298 | 2775063 |
| `read_model.workbench_snapshots` | 1.48GB | 481 | 122 | 4789 |
| `read_model.search_index_rows` | 125MB | 1678 | 0 | 319538 |
| `job.outbox_events` | 71MB | 36022 | 116606 | 6145828 |

最大且疑似低效索引样本：

| index | size | idx_scan |
|---|---:|---:|
| `workbench_groups_searchable_text_trgm` | 708MB | 0 |
| `workbench_rows_payload_gin` | 337MB | 0 |
| `workbench_group_rows_searchable_text_trgm` | 310MB | 413 |
| `workbench_group_rows_generation_scope_identity_zone_idx` | 95MB | 0 |

固定 EXPLAIN probe 当前为 plain EXPLAIN，未执行 ANALYZE：

| probe | total cost | plan rows |
|---|---:|---:|
| `active_read_model_dirty_scopes` | 47.03 | 1 |
| `active_read_model_outbox` | 23.87 | 1 |
| `non_fresh_app_status_readiness` | 31.91 | 1 |
| `workbench_groups_all_scope_count` | 8396.72 | 1 |
| `workbench_group_rows_all_scope_count` | 12903.76 | 1 |

Stage 16 结论：

- 当前“失败/同步几分钟”的主要 current-effective blocker 已被清零；生产 runtime 不再显示 read model/outbox attention。
- 这不是“几秒内全部同步”闭环证明：全局历史 p95 仍约 17.76s，`workbench`、`invoice_lifecycle`、`input_invoice_usage`
  近 1 小时 p95 仍在 8-9s，且 15 分钟窗口无新样本，不能证明写入后 p95 已稳定达标。
- `pg_stat_statements` 必须在 PostgreSQL 参数中启用 `shared_preload_libraries` 并重启数据库，才有 top SQL 生产证据；
  这一步需要独立 rollback 计划。
- 页面首包/API p95 仍是 `not_collected`，必须用登录态 HTTP/browser 采样补齐；不能用 worker freshness 代替页面体验证据。
- 最大表和最大索引集中在 workbench generation 表，下一阶段索引、retention、分区或 payload-cache 决策必须围绕这些事实做 impact analysis。

## Stage 17：启用 pg_stat_statements preload

Stage 17 只做生产运维配置变更，无代码提交。目标是补齐数据库 top SQL 证据链，避免在没有
`pg_stat_statements` 的情况下盲做索引或分区。

变更前只读 preflight：

| 项目 | 结果 |
|---|---|
| PostgreSQL service | `postgresql.service` |
| PostgreSQL version | 16.12 |
| config file | `/var/lib/pgsql/data/postgresql.conf` |
| auto config file | `/var/lib/pgsql/data/postgresql.auto.conf` |
| `shared_preload_libraries` | empty |
| app/workers active connections | idle only；无 active transaction |
| `job.outbox_events` active statuses | 0 |
| `job.read_model_dirty_scopes` active statuses | 0 |
| `read_model.app_status_readiness` | 124 fresh |

执行记录：

1. 备份 `/var/lib/pgsql/data/postgresql.auto.conf` 到
   `/var/lib/pgsql/data/postgresql.auto.conf.stage17-20260613013828.bak`。
2. 停止 `fin-ops-rabbitmq-dispatcher.service`、12 个 `fin-ops-worker@*.service` 和 `fin-ops.service`。
3. 执行 `ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';`。
4. 重启 `postgresql.service`；验证 `shared_preload_libraries` 为 `pg_stat_statements`。
5. 用 `/usr/local/sbin/finops-deploy-control restart` 恢复 API；由于该 helper 只重启调用时
   active 的 worker，而 worker 在第 2 步已经全部停止，所以随后显式执行
   `/usr/local/sbin/finops-ensure-runtime-workers /opt/fin-ops/releases/main-688ce928-stage16-202606130133/src`
   恢复 required workers，并启动 dispatcher。

恢复验证：

| 指标 | 值 |
|---|---:|
| `/health/ready.status` | `ready` |
| release | `main-688ce928-stage16-202606130133` |
| runtime release consistent | true |
| active required workers | 12 |
| dispatcher | active |
| app DB `pg_stat_statements` extension | installed |
| app DB `pg_stat_statements` rows | 77 |

Stage 17 baseline JSON：
`/tmp/finops-sync-slo-baseline-stage17-20260613014328.json`。

Stage 17 同步基线：

| 指标 | 值 |
|---|---:|
| `failed_jobs` | 0 |
| `stale_dirty_scope_count` | 0 |
| `max_pending_age_seconds` | null |
| `queue_backlog.done` | 36021 |
| `dirty_scopes.done` | 30745 |
| runtime read model attention | 0 |
| runtime outbox attention | 0 |
| `pg_stat_statements.status` | available |
| metric version | `pg_stat_statements_total_exec_time` |
| `read_model_refresh_duration_ms.p95` | 17759.437ms |

Stage 17 top SQL 样本：

| rank | total_exec_time | calls | mean_exec_time | query 摘要 |
|---:|---:|---:|---:|---|
| 1 | 2864.602ms | 1 | 2864.602ms | `read_model.workbench_generation_consistency` inconsistent count |
| 2 | 400.821ms | 29 | 13.821ms | `job.outbox_events` status count by event type |
| 3 | 367.547ms | 399 | 0.921ms | `app.app_settings` settings payload lookup |
| 4 | 334.678ms | 29 | 11.541ms | workbench generation consistency aggregate over rows/groups/group_rows/summary |
| 5 | 179.012ms | 1 | 179.012ms | `read_model.workbench_candidate_matches` full candidate load |

Rollback：

1. `ALTER SYSTEM RESET shared_preload_libraries;`
2. `systemctl restart postgresql.service`
3. `/usr/local/sbin/finops-deploy-control restart`
4. 若 worker 曾被停止，执行
   `/usr/local/sbin/finops-ensure-runtime-workers /opt/fin-ops/releases/main-688ce928-stage16-202606130133/src`
   并启动 `fin-ops-rabbitmq-dispatcher.service`。
5. 重新跑 `/health/ready` 和 `sync_slo_baseline`，确认 current-effective blocker 仍为 0。

Stage 17 结论：

- 数据库 top SQL 证据链已补齐；下一阶段可以对 top SQL 做 EXPLAIN ANALYZE 和索引/retention impact analysis。
- 这仍不是“几秒内全部同步”验收通过：当前缺少真实用户登录态页面/API p95 采样，且 global historical
  read model p95 仍保留 17.76s 历史样本。
- 运维 caveat：`finops-deploy-control restart` 不适合在 worker 已全部停止后单独恢复 worker；维护脚本或手册应补
  `finops-ensure-runtime-workers` 步骤。

## Stage 18：移除状态页热路径重型 consistency 视图

Stage 18 Release：`main-8f123cb4-stage18-202606130151`

Stage 18 Commit：`8f123cb4`

Stage 17 top SQL 证明 `RuntimeMonitoringRepository.dashboard_read_model_metrics()` 每次统计 workbench
一致性时会查询 `read_model.workbench_generation_consistency` 视图。该视图会 live recompute
`workbench_group_rows`、`workbench_groups`、`workbench_rows`、`workbench_summary` 和 duplicate identity
聚合；生产 EXPLAIN ANALYZE 显示单次 count 约 `2484.731ms`，且会读 `142880` 个 shared blocks，
还有外部排序 temp I/O。

Stage 18 将监控热路径改为读取持久字段：

```sql
select count(*)::bigint as inconsistent_count
from read_model.workbench_generations
where tenant_id = 'default'
  and status = 'active'
  and consistency_status = 'inconsistent';
```

这个字段由 workbench generation 发布/失败边界写入：building 时为 `validating`，activate 时为
`consistent`，fail 时为 `inconsistent`。重型 `_workbench_generation_consistency_failures(...)`
仍保留在 generation 构建、发布和 all-scope 聚合边界，不从状态页热路径删除真实校验。

本地验证：

- `PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_monitoring tests.test_operations_dashboard_service -v`
- `bash scripts/verify.sh backend`：2833 tests pass，25 skipped

生产部署：

- 使用干净 worktree `/tmp/finops-stage18-deploy`。
- 复用已验证 `web/dist`，执行
  `./scripts/deploy-oa.sh --skip-build --release-name main-8f123cb4-stage18-202606130151`。
- migrations `0001`-`0067` 均为 skipped/accepted drift；backend readiness、worker ensure、frontend hash、
  public session route checks 均通过；旧 release `main-02dc9317-stage13-202606130103` 被清理。

生产验证：

| 指标 | Stage 17 旧视图 | Stage 18 持久字段 |
|---|---:|---:|
| consistency count EXPLAIN execution | 2484.731ms | 0.796ms |
| root node | Aggregate | Aggregate |
| shared read blocks | 142880 | 2 |
| `dashboard_read_model_metrics()` elapsed | 未单独计时 | 161.423ms |
| workbench stale/unavailable | 0 / 0 | 0 / 0 |

Stage 18 baseline JSON：
`/tmp/finops-sync-slo-baseline-stage18-20260613015259.json`。

该 baseline 仍包含 Stage 17 的累计 pg_stat 旧慢 SQL，因此采集后执行
`pg_stat_statements_reset()`，再跑 5 次 runtime monitoring 采样，生成 clean baseline：
`/tmp/finops-sync-slo-baseline-stage18-clean-20260613015555.json`。

clean pg_stat top SQL：

| rank | total_exec_time | calls | mean_exec_time | query 摘要 |
|---:|---:|---:|---:|---|
| 1 | 816.466ms | 6 | 136.078ms | `dashboard_read_model_metrics` duration window over `job.outbox_events` |
| 2 | 245.948ms | 330 | 0.745ms | `app.app_settings` lookup |
| 3 | 227.786ms | 6 | 37.964ms | read model refresh percentile over `job.outbox_events` |
| 4 | 212.163ms | 27 | 7.858ms | `workbench.read_model.refresh` outbox status count |
| 5 | 207.472ms | 27 | 7.684ms | scoped workbench generation consistency aggregate |

Stage 18 结论：

- 状态页 current-effective blocker 仍为 0：`failed_jobs=0`、`stale_dirty_scope_count=0`、
  outbox/read model attention 为空。
- Stage 17 的 2.5s 状态页慢 SQL 已从热路径移除，clean top SQL 不再出现
  `read_model.workbench_generation_consistency` 全量视图。
- 下一阶段数据库优化重点应转向 `job.outbox_events` 的 runtime metric window/percentile 查询，以及
  `workbench` 单 scope consistency aggregate 是否需要更便宜的缓存或按需采样。
- 页面/API p95 仍未采集，因此“几秒内全部同步”仍未验收。

## Stage 19：优化状态页 read model duration metric 查询

Stage 19 Release：`main-20148900-stage19-202606130212`

Stage 19 Commit：`20148900`

Stage 18 clean top SQL 证明 `dashboard_read_model_metrics()` 的 duration window 查询会在
`job.outbox_events` 上做 `row_number() over (partition by event_type order by updated_at desc)`。
生产 EXPLAIN 显示约 `145.680ms`，`temp_read=2635`、`temp_written=2641`，并对约 3.5 万条历史
refresh event 做外部排序。该查询只服务 App Health/运行状态面板，不参与真实 read model refresh。

Stage 19 做两个最小改动：

- 新增 migration `0068_outbox_read_model_refresh_metric_samples.sql`，创建
  `outbox_events_read_model_refresh_metric_samples_idx`，索引键包含 `event_type`、`updated_at desc`、
  JSONB 派生的 metric scope marker 和 `duration_ms`。
- 将 duration SQL 改为 `event_type_filter -> cross join lateral -> order by updated_at desc limit 512`，
  每个 read model event type 只取有界最近样本，再按 `recent_15m`、`recent_1h`、`all_time`
  聚合 percentiles。

本地验证：

- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_operations_dashboard_service tests.test_runtime_monitoring tests.test_postgres_migrations tests.test_postgres_test_utils -v`
- `bash scripts/verify.sh backend`：2833 tests pass，25 skipped

生产部署：

- 使用干净 worktree `/private/tmp/finops-stage19-deploy`。
- 复用已验证 `web/dist`，执行
  `./scripts/deploy-oa.sh --skip-build --release-name main-20148900-stage19-202606130212`。
- 首次 SSH 未建立 ControlMaster 导致认证失败，远端未进入部署步骤；建立脚本使用的 SSH ControlMaster 后重跑。
- migration `0068` applied，用时 `85ms`；backend readiness、worker ensure、frontend hash、
  public session route checks 均通过；旧 release `main-3d103ceb-stage14-202606130115` 被清理。

生产验证：

| 指标 | Stage 18 clean | Stage 19 |
|---|---:|---:|
| duration metric SQL mean | 136.078ms | 49.806ms |
| duration metric SQL temp I/O | `2635/2641` blocks | `0/0` blocks |
| duration metric SQL index | old partial index / bitmap + sort | `outbox_events_read_model_refresh_metric_samples_idx` |
| `dashboard_read_model_metrics()` cold run | 161.423ms | 168.786ms |
| `dashboard_read_model_metrics()` warm run | 未单独采样 | 63-71ms |
| failed jobs | 0 | 0 |
| stale dirty scopes | 0 | 0 |
| RabbitMQ queue / DLQ | 0 / 0 | 0 / 0 |

Stage 19 baseline JSON：

- 累计 baseline：`/tmp/finops-sync-slo-baseline-stage19-202606130216.json`
- clean baseline：`/tmp/finops-sync-slo-baseline-stage19-clean-202606130218.json`

Stage 19 clean baseline 仍发现一个历史 optional worker heartbeat
`operator-cost-statistics-drain-after-deploy-20260606`，实例名 `cost-tax-read-model`，它不是当前 required
`cost-tax` worker，但会进入 `worker_attention`。这不是刷新链路失败，但会污染“当前有效 blocker”视图。

Rollback：

1. 回滚到 `main-8f123cb4-stage18-202606130151` release。
2. 如需移除索引，可在维护窗口执行：
   `drop index if exists job.outbox_events_read_model_refresh_metric_samples_idx;`
3. 重新跑 `/health/ready`、`dashboard_read_model_metrics()` direct probe 和 `sync_slo_baseline`。

## Stage 20：App Status worker snapshot 只看 current-effective worker

Stage 20 Release：`main-9498e9e0-stage20-202606130220`

Stage 20 Commit：`9498e9e0`

Stage 20 不删除历史 heartbeat 事实，只在 worker metric row 上新增 `current_effective` 标记：
required worker 总是 current-effective；optional worker 如果超过对应 registration 的
`heartbeat_stale_after_seconds`，在 App Status worker snapshot 中跳过。Operations dashboard 明细仍可看到
历史 optional worker，用于审计。

本地验证：

- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_runtime_monitoring tests.test_operations_dashboard_service -v`
- `bash scripts/verify.sh backend`：2834 tests pass，25 skipped

生产部署：

- 使用干净 worktree `/private/tmp/finops-stage20-deploy`。
- 复用已验证 `web/dist`，执行
  `./scripts/deploy-oa.sh --skip-build --release-name main-9498e9e0-stage20-202606130220`。
- migration `0068` skipped；backend readiness、worker ensure、frontend hash、public session route checks 均通过；
  旧 release `main-53b148b3-stage15-202606130124` 被清理。

Stage 20 clean baseline JSON：
`/tmp/finops-sync-slo-baseline-stage20-clean-202606130222.json`。

Stage 20 clean baseline：

| 指标 | 值 |
|---|---:|
| release | `main-9498e9e0-stage20-202606130220` |
| schema_version | 68 |
| runtime_release.consistent | true |
| `failed_jobs` | 0 |
| `stale_dirty_scope_count` | 0 |
| RabbitMQ queue depth | 0 |
| RabbitMQ DLQ | 0 |
| read model attention | 0 |
| outbox attention | 0 |
| worker attention | 0 |
| queue unknown count | 0 |
| `dashboard_read_model_metrics()` cold run | 166.028ms |
| `dashboard_read_model_metrics()` warm run | 62.758-68.631ms |
| duration metric SQL mean | 49.089ms |

Stage 20 结论：

- 状态页 read model/outbox/worker current-effective blocker 全部清零。
- 状态页 duration metric 查询不再对 outbox 历史做全局窗口排序，不再产生 temp I/O。
- 这仍不是“几秒内全部同步”最终验收：read model 历史 refresh p95 仍含重型构建样本，页面首包/API p95
  仍需登录态 HTTP 采样。

## Stage 21：补齐登录态 HTTP SLO 采样入口

Stage 21 Release：`main-d206d545-stage21-202606130231`

Stage 21 Commit：`d206d545`

Stage 20 之后的主要证据缺口不是 App Status，而是用户真实页面体验：页面 shell 首包、关键 read model API 首包、
以及这些 API 返回时的 `read_model_status` / `cache_status`。只看 `/health` 或数据库 baseline 不能证明用户页面
已在几秒内拿到 fresh snapshot。

Stage 21 新增只读采样工具：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe \
  --base-url https://www.yn-sourcing.com \
  --api-prefix /fin-ops-api \
  --page-path /fin-ops/ \
  --iterations 20 \
  --warmup 2 \
  --output /tmp/finops-http-slo-$(date +%Y%m%d%H%M%S).json
```

工具默认要求真实登录态凭证：

- `FIN_OPS_HTTP_SLO_ADMIN_TOKEN`
- `FIN_OPS_HTTP_SLO_BEARER_TOKEN`
- `FIN_OPS_HTTP_SLO_COOKIE`

没有真实凭证时返回 `auth_missing`，不能生成最终生产 SLO 证据；`--allow-unauthenticated` 仅用于 public page
shell smoke。输出不会包含 token、cookie 或 Authorization header。

默认采样覆盖 `/fin-ops/` 页面 shell，以及 session、App Health、Operations Dashboard、workbench、bank details、
pending invoices、input invoice usage、OA pending payments、output invoice collections、tax offset、cost statistics
和 search 首屏 API。默认目标是每个 probe p95 `< 1000ms`，read model API 同时记录响应中的 freshness/cache
元数据，避免把“假同步”当作通过。

本地验证：

- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_http_slo_probe -v`
- `bash scripts/verify.sh backend`：2838 tests pass，25 skipped

生产部署：

- 使用干净 worktree `/private/tmp/finops-stage21-deploy`。
- 复用已验证 `web/dist`，执行
  `./scripts/deploy-oa.sh --skip-build --release-name main-d206d545-stage21-202606130231`。
- migration `0068` skipped，没有新增数据库变更。
- deploy script 在 release activation 后返回 SSH `255`，但线上已切到
  `main-d206d545-stage21-202606130231`。随后手动补跑后半段验证：`/health/ready`、deploy-control status、
  runtime worker ensure、frontend hash、public session route 和 cleanup releases 均通过。

生产 post-deploy summary：

| 指标 | 值 |
|---|---:|
| release | `main-d206d545-stage21-202606130231` |
| schema_version | 68 |
| runtime_release.consistent | true |
| `failed_jobs` | 0 |
| `stale_dirty_scope_count` | 0 |
| RabbitMQ queue depth | 0 |
| RabbitMQ DLQ | 0 |
| missing required workers | 0 |
| stale required workers | 0 |

生产 smoke：

- public page shell only：
  `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe --base-url https://www.yn-sourcing.com --page-path /fin-ops/ --replace-default-probes --iterations 5 --warmup 1 --allow-unauthenticated`
- pre-deploy 工具链路结果：`/tmp/finops-http-slo-stage21-public-shell-20260613023043.json`，
  5 个 measured samples，status `200`，p95 `108.325ms`。
- post-deploy release 结果：`/tmp/finops-http-slo-stage21-release-public-shell-20260613023350.json`，
  5 个 measured samples，status `200`，p95 `107.950ms`。
- 不带 token 采集登录态 API 时返回 exit code `2` / `auth_missing`，符合“缺真实登录态不生成生产 SLO 证据”的保护。

Stage 21 结论：

- 现在具备可重复、不会泄露凭证的登录态 HTTP SLO 采样入口。
- 尚未形成最终生产 SLO 证据：仍需要在真实管理员登录态下采集 20+ 次样本，并把结果与 runtime freshness
  baseline 放在同一阶段报告中。

## Stage 22：Redis fresh-cache 增加 fresh-gate envelope

Stage 22 Release：`main-0c9a3c68-stage22-202606130242`

Stage 22 Commit：`0c9a3c68`

Stage 22 修复 fresh-cache 的基础契约：不能只因为 Redis key 命中就把 payload 标记成 fresh。通用
`ReadModelQueryGateway` 现在要求 Redis payload 通过 fresh-gate 校验：

- `fresh_gate.scope_key` 与当前 scope 一致。
- `fresh_gate.read_model_status=fresh`。
- `fresh_gate.source_versions` 与当前 expected source versions 一致。
- `fresh_gate.schema_version` 存在时必须与当前 expected schema version 一致。

命中失败时不返回旧 payload，不 enqueue 伪刷新，而是 fail closed 回 SQL read model 路径；只有 SQL view
再次通过 freshness/source-version gate 后，才会写入新的 fresh-gate envelope。

同步更新的写入路径：

- `ReadModelQueryGateway` fresh SQL view cache write。
- 成本统计 runtime cache warmup。
- 成本/税金 SQL projection legacy Redis writes。
- 税金抵扣 worker refresh 后的 month/summary Redis warmup。

本地验证：

- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_read_model_query_gateway tests.test_cost_statistics_sql_runtime tests.test_tax_offset_sql_runtime -v`
- `bash scripts/verify.sh backend`：2839 tests pass，25 skipped

生产部署：

- 使用干净 worktree `/private/tmp/finops-stage22-deploy`。
- 复用已验证 `web/dist`，执行
  `./scripts/deploy-oa.sh --skip-build --release-name main-0c9a3c68-stage22-202606130242`。
- migration `0068` skipped，没有新增数据库变更。
- deploy script 完整通过：backend readiness、deploy-control status、runtime worker ensure、frontend hash、public session route
  和 cleanup releases 均通过；旧 release `main-8f123cb4-stage18-202606130151` 被清理。

生产 post-deploy summary：

| 指标 | 值 |
|---|---:|
| release | `main-0c9a3c68-stage22-202606130242` |
| schema_version | 68 |
| runtime_release.consistent | true |
| `failed_jobs` | 0 |
| `stale_dirty_scope_count` | 0 |
| RabbitMQ queue depth | 0 |
| RabbitMQ DLQ | 0 |
| missing required workers | 0 |
| stale required workers | 0 |

生产 smoke：

- public page shell only：
  `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe --base-url https://www.yn-sourcing.com --page-path /fin-ops/ --replace-default-probes --iterations 5 --warmup 1 --allow-unauthenticated`
- 结果文件：`/tmp/finops-http-slo-stage22-public-shell-20260613024403.json`
- 5 个 measured samples，status `200`，p95 `112.874ms`。
- `/fin-ops-api/api/session/me` 和 `/fin-ops/api/session/me` 仍返回 JSON `401`，代理路由正常。

Stage 22 结论：

- 通过 gateway 的 Redis fresh-cache 不再接受无 source-version gate 的旧 payload 作为 fresh。
- 这仍不是全部页面 fresh-cache 完成：workbench groups 使用 generation/version key 的专用 cache；bank detail、pending invoice、
  invoice lifecycle、input/output invoice usage、OA pending payment 等页面仍需要逐页按相同契约迁移或确认已有等价 fresh gate。

## Stage 23：Prometheus 指标出口

Stage 23 将已有 `/health/ready` runtime facts 转换为 Prometheus text exposition：

```text
GET /metrics
Authorization: Bearer <FIN_OPS_PROMETHEUS_BEARER_TOKEN>
```

该接口复用现有 readiness/runtime monitoring payload，不执行 workbench deep self-test，不写数据，不执行 retry/repair。
`FIN_OPS_PROMETHEUS_BEARER_TOKEN` 未配置时返回 `404`；配置后必须带同值 bearer token。
生产 scrape 应限制在内网或本机端口；公网代理是否暴露由部署层控制，即使公网路径可达也必须由 token 和代理 ACL 双重保护。

新增指标覆盖：

- release / production guard：`finops_ready`、`finops_runtime_release_consistent`、`finops_production_runtime_guard_consistent`。
- PostgreSQL durable queue：`finops_outbox_events{status=...}`、`finops_read_model_dirty_scopes{status=...}`、
  `finops_failed_jobs`、`finops_stale_dirty_scope_count`。
- read model performance：`finops_read_model_refresh_duration_ms{quantile=...}`、
  `finops_read_model_refresh_failure_rate`。
- RabbitMQ：`finops_rabbitmq_queue_depth`、`finops_rabbitmq_dlq_count`、`finops_rabbitmq_consumer_count`、
  `finops_rabbitmq_publish_confirm_latency_ms{quantile=...}`。
- worker：`finops_worker_heartbeat_lag_seconds{worker_instance=...,worker_kind=...,status=...}`、
  `finops_worker_required`、`finops_worker_current_effective`、`finops_worker_warning`。
- API p95：`finops_api_duration_ms{endpoint=...,quantile=...}`、
  `finops_api_connection_acquire_ms{endpoint=...,quantile=...}`、
  `finops_api_sql_execute_fetch_ms{endpoint=...,quantile=...}`。
- workbench generation：`finops_workbench_read_model_active_scope_count`、
  `finops_workbench_read_model_active_row_count`、`finops_workbench_read_model_failed_scope_count`。

本地验证：

- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_prometheus_metrics tests.test_app tests.test_app_postgres_mode tests.test_runtime_monitoring -v`
- `bash scripts/verify.sh docs`
- `bash scripts/verify.sh backend`

生产发布：

- commit：`d648c9b3 Expose protected Prometheus runtime metrics`
- release：`main-d648c9b3-stage23-202606130256`
- `/health/ready`：`status=ready`，`runtime_release.consistent=true`，schema `68`。
- runtime health：`failed_jobs=0`，`stale_dirty_scope_count=0`，`rabbitmq_queue_depth=0`，`rabbitmq_dlq_count=0`，
  `missing_required_worker_count=0`，`stale_required_worker_count=0`。
- `/metrics` 未带 token 本机访问返回 `404 application/json`；公网 `/fin-ops-api/metrics` 同样返回 `404 application/json`。
- 公网 `/metrics` 返回外层站点 `200 text/html`，不是 fin-ops API。
- 未通过无交互 root 权限配置 `FIN_OPS_PROMETHEUS_BEARER_TOKEN`，因此生产 Prometheus scrape token 仍待人工写入
  `/etc/fin-ops/fin-ops.secrets.env` 并重启 `fin-ops.service` 后启用。
- 未登录页面 shell smoke：
  `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe --base-url https://www.yn-sourcing.com --page-path /fin-ops/ --replace-default-probes --iterations 5 --warmup 1 --allow-unauthenticated`
  通过，`/fin-ops/` p95 `116.127ms`。

## Stage 24：health / metrics outbox percentile 热路径收敛

Stage 24 收敛 `/health/ready`、`/health`、Prometheus `/metrics` 和 App Health dashboard 复用的 runtime
monitoring 热路径：

- `queue_backlog` 只统计 current backlog / attention status，不再把历史 `done` outbox 放进健康检查热路径。
- `read_model_refresh_duration_ms` 和 `read_model_refresh_failure_rate` 改为按 read model event type 最近
  `512` 条样本聚合，仍来自 PostgreSQL `job.outbox_events` 事实源，但不做全历史 percentile sort。
- `rabbitmq_publish_confirm_latency_ms` 改为按 RabbitMQ dispatch event type 最近 `512` 条样本聚合，不做全历史
  published outbox percentile sort。
- `dashboard_outbox_metric()` 增加 current-attention `WHERE`，只扫描 pending / failed / dead-lettered / publish failed
  相关 outbox。
- Prometheus 增加 `finops_read_model_refresh_sample_count` 和
  `finops_rabbitmq_publish_confirm_sample_limit`，避免把低样本 percentile 误读成稳定 SLO。

本地验证：

- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_runtime_monitoring tests.test_operations_dashboard_service tests.test_prometheus_metrics tests.test_app_postgres_mode -v`
- `bash scripts/verify.sh docs`
- `bash scripts/verify.sh backend`

生产发布：

- commit：`2535765a Bound runtime outbox metric scans`
- release：`main-2535765a-stage24-202606130306`
- `/health/ready`：`status=ready`，`runtime_release.consistent=true`，schema `68`。
- runtime health：`queue_backlog_keys=[]`，`failed_jobs=0`，`stale_dirty_scope_count=0`，`rabbitmq_queue_depth=0`，
  `rabbitmq_dlq_count=0`，`missing_required_worker_count=0`，`stale_required_worker_count=0`。
- bounded runtime metric：`read_model_refresh_duration_ms.p95=8301.8155ms`，`read_model_refresh_sample_count=5940`，
  `read_model_refresh_failure_rate=0.0`。
- RabbitMQ confirm metric：`rabbitmq_publish_confirm_latency_ms.p95=10.467ms`，
  `rabbitmq_publish_confirm_sample_limit=512`。
- 本机 `/health/ready` 连续 5 次 curl `time_total`：`0.420397s`、`0.339751s`、`0.333093s`、
  `0.333778s`、`0.332786s`。
- `/metrics` 未带 token 本机访问返回 `404 application/json`；公网 `/fin-ops-api/metrics` 返回
  `404 application/json`；公网 `/metrics` 返回外层站点 `200 text/html`，不是 fin-ops API。
- 未登录页面 shell smoke：
  `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.http_slo_probe --base-url https://www.yn-sourcing.com --page-path /fin-ops/ --replace-default-probes --iterations 5 --warmup 1 --allow-unauthenticated`
  通过，`/fin-ops/` p95 `121.826ms`。

Stage 24 结论：

- health / Prometheus runtime 指标热路径已避免全历史 outbox percentile / done count 扫描。
- `read_model_refresh_duration_ms.p95` 在 bounded recent sample 口径下约 `8.3s`，比旧全历史约 `17.76s`
  更接近当前有效状态，但仍未达到轻量 read model enqueue-to-fresh p95 `< 3s` 的目标。
- 下一步仍必须定位 `workbench`、`invoice_lifecycle`、`input_invoice_usage` 等重型 refresh 的真实执行耗时，
  不能把观测口径优化误当作业务同步 SLO 达标。

## Stage 25：read model refresh by-key breakdown

Stage 25 在 Stage 24 的 bounded recent sample 基础上，给 `/health/ready` / `/health` runtime payload 增加
`read_model_refresh_by_key`：

- 每个 read model event type 一行，包含 `key`、`event_type`、`scope_type`。
- 每行包含最近 bounded sample 的 `duration_ms.p50/p95/p99`、`sample_count`、`completed_sample_count`、
  `failed_count`、`failure_rate` 和 `last_completed_at`。
- 仍复用同一个 `job.outbox_events` bounded lateral sample CTE，通过 `grouping sets` 同时产生 overall 与 by-key
  聚合，不新增事实源，不扫描全历史。
- Prometheus 增加 `finops_read_model_refresh_by_key_duration_ms{read_model_key=...,event_type=...,scope_type=...,quantile=...}`、
  `finops_read_model_refresh_by_key_sample_count{...}` 和
  `finops_read_model_refresh_by_key_failure_rate{...}`。

本地验证：

- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_runtime_monitoring tests.test_prometheus_metrics tests.test_app_postgres_mode -v`
- `bash scripts/verify.sh docs`
- `bash scripts/verify.sh backend`

生产发布：

- commit：`a227d0ff Report read model refresh metrics by key`
- release：`main-a227d0ff-stage25-202606130315`
- `/health/ready`：`status=ready`，`runtime_release.consistent=true`，schema `68`。
- bounded runtime metric：`read_model_refresh_duration_ms.p95=8301.8155ms`，`read_model_refresh_sample_count=5940`，
  `read_model_refresh_failure_rate=0.0`。
- runtime health：`queue_backlog={}`，`failed_jobs=0`，`stale_dirty_scope_count=0`，`rabbitmq_queue_depth=0`，
  `rabbitmq_dlq_count=0`，`missing_required_worker_count=0`，`stale_required_worker_count=0`。
- `read_model_refresh_by_key` 生产样本共 `14` 个 event type，按 p95 降序前 8 项：
  - `search.read_model.refresh`：p95 `35107.029ms`，sample `174`，failure `0.0`。
  - `workbench.read_model.refresh`：p95 `28180.444ms`，sample `512`，failure `0.0`。
  - `cost_statistics.read_model.refresh`：p95 `6639.672ms`，sample `512`，failure `0.0`。
  - `invoice_lifecycle.read_model.refresh`：p95 `6318.668ms`，sample `512`，failure `0.0`。
  - `input_invoice_usage.read_model.refresh`：p95 `5780.509ms`，sample `512`，failure `0.0`。
  - `turnover_ledger.read_model.refresh`：p95 `4482.926ms`，sample `133`，failure `0.0`。
  - `workbench_relation.read_model.refresh`：p95 `1896.104ms`，sample `512`，failure `0.0`。
  - `bank_detail.read_model.refresh`：p95 `1757.164ms`，sample `512`，failure `0.0`。
- 本机 `/health/ready` 连续 5 次 curl `time_total`：`0.339808s`、`0.338427s`、`0.325668s`、
  `0.330065s`、`0.344222s`。
- 公网 `/fin-ops/` 未登录页面 shell smoke 通过，p95 `114.807ms`。
- 公网 `/fin-ops-api/metrics` 未带 token 返回 `404 application/json`，符合未配置 token 时安全关闭预期。

Stage 25 结论：

- by-key breakdown 已证实 SQL 在生产 PostgreSQL 上可执行，且不会明显拖慢 `/health/ready`。
- 当前总 p95 `8.3s` 不是单纯观测查询慢，而是被真实 refresh event 的长尾拖住。
- 下一阶段应优先检查 `search` 与 `workbench` 的 refresh 触发范围、coalescing、worker 执行计划和索引命中；随后处理
  `cost_statistics`、`invoice_lifecycle`、`input_invoice_usage` 这三个 5-7s 级 event type。

## Stage 26：defer workbench all aggregation from month shard refresh

Stage 26 针对 Stage 25 暴露的 `workbench.read_model.refresh` 长尾先做一个小范围、可回滚的 worker 热路径收敛：

- 保留 `PostgresReadModelRepository.save_workbench_read_models(...)` 默认旧行为，避免破坏仍直接调用 repository 的旧路径。
- `WorkbenchSqlProjectionBuilder.rebuild_workbench_read_model_scope(month)` 保存单月 shard 时显式传
  `refresh_all_scope_from_month_shards=False`，不再在同一事务内重建 `all` scope。
- `all` scope 仍由既有 `WorkbenchReadModelRefreshService` aggregate event 通过
  `refresh_workbench_all_scope_from_active_shards()` 原子发布，不绕过 active generation 模型。
- `WorkbenchReadModelRefreshService`、`SearchPendingReadModelRefreshService` 在 rebuild/expand 前复用
  `RuntimeQueueRepository.read_model_refresh_is_current(...)`，对过期 `source_version` 事件返回
  `skipped/stale_source_version`，避免 stale outbox 占用 worker 做无效重建。

本地验证：

- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_workbench_sql_runtime tests.test_search_pending_sql_runtime -v`
- `PYTHONPATH=backend/src:tests python3 -m unittest tests.test_runtime_queue tests.test_runtime_worker tests.test_rabbitmq_runtime tests.test_app_postgres_mode tests.test_platform_runtime_boundary_guards -v`
- `python3 -m py_compile backend/src/fin_ops_platform/services/workbench_read_model_refresh.py backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py backend/src/fin_ops_platform/services/workbench_sql_projection.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `bash scripts/verify.sh docs`
- `bash scripts/verify.sh backend`

生产发布：

- commit：`fd8cc3c7 Defer workbench all aggregation from shard refresh`
- release：`main-fd8cc3c7-stage26-202606130329`
- `/health/ready`：`status=ready`，`runtime_release.consistent=true`，schema `68`。
- runtime health：`queue_backlog={}`，`failed_jobs=0`，`stale_dirty_scope_count=0`，`rabbitmq_queue_depth=0`，
  `rabbitmq_dlq_count=0`，`missing_required_worker_count=0`，`stale_required_worker_count=0`。
- bounded runtime metric 暂未变化：`read_model_refresh_duration_ms.p95=8301.8155ms`，`read_model_refresh_sample_count=5940`，
  `read_model_refresh_failure_rate=0.0`。
- `read_model_refresh_by_key` 暂未变化：`search` p95 `35107.029ms`，`workbench` p95 `28180.444ms`，
  `cost_statistics` p95 `6639.672ms`，`invoice_lifecycle` p95 `6318.668ms`，
  `input_invoice_usage` p95 `5780.509ms`。
- 本机 `/health/ready` 连续 5 次 curl `time_total`：`0.330925s`、`0.333933s`、`0.343484s`、
  `0.325625s`、`0.341890s`。
- 公网 `/fin-ops/` 未登录页面 shell smoke 通过，p95 `104.213ms`。
- 公网 `/fin-ops-api/metrics` 未带 token 返回 `404 application/json`，符合未配置 token 时安全关闭预期。

Stage 26 结论：

- 发布后 runtime health 正常，未引入 failed jobs / DLQ / worker missing。
- by-key p95 仍是部署前历史 bounded sample；Stage 26 代码路径已消除月 shard 内联 all 聚合，但生产 p95 降幅需要
  新 workbench refresh 样本才能证明。
- deploy 用户没有 root-only PostgreSQL DSN，不能直接运行 production scope/event_id drilldown；如需 scope 级证据，
  应新增受保护的只读诊断入口或由 root 环境执行只读 collector，不打印 secrets。

## 当前闭环状态

已闭环：

- current-effective App Status blocker 只看当前有效 dirty/outbox/readiness，不再被历史 legacy scope 污染。
- current-effective worker attention 不再被历史 optional worker heartbeat 污染。
- legacy `cost_statistics` scope 已受控 repair，并由 replacement scope 真实重建完成。
- covered historical dead-letter 已通过 repository 工具归档，`failed_jobs=0`。
- worker shutdown 不再依赖 300 秒 lock timeout 回收 `processing` lease。
- RabbitMQ topology、Management metrics、required worker real consumers 和 DLQ 清理已完成。
- candidate relation 已通过 workbench relation read model 传播到下游页面，页面不再把候选关系误计为 confirmed/paid/closed。
- 发票使用详情在 fresh gate 后走 SQL read model 单行 payload，避免详情抽屉请求热路径 N+1/live assembly。
- 应用启动默认不再执行 startup stale scan；显式启用时也只会重算缺少 completed scope run proof 的 matching 月份。
- 生产 SLO baseline collector 已部署，可重复采集 runtime、worker、PostgreSQL catalog、固定 EXPLAIN 和缺口状态。
- `pg_stat_statements` 已在生产 PostgreSQL preload 并可在 app DB 读取 top SQL。
- 状态页 read model health 热路径不再 live recompute `workbench_generation_consistency` 全量视图。
- 状态页 read model duration metric 热路径不再全局排序 `job.outbox_events` 历史样本，clean mean 约 `49ms`，
  `dashboard_read_model_metrics()` warm run 约 `63-69ms`。
- health / Prometheus runtime percentile 热路径不再全历史排序 outbox，而是按 event type 使用 bounded recent samples。
- health / Prometheus 已具备按 read model key 拆分的 refresh p95/failure/sample breakdown，可定位下一阶段优化目标。
- workbench 月度 SQL projection refresh 已从内联 all-scope aggregation 中解耦，all scope 改由既有 aggregate event
  发布；workbench/search/pending_invoice refresh handler 会跳过 stale source_version 事件。
- 登录态 HTTP SLO probe 已具备，可重复采集页面 shell 和关键读 API p95，并记录 freshness/cache 元数据。
- 通用 Redis fresh-cache 已具备 fresh-gate envelope，旧格式或 source-version 不匹配的缓存不会被当作 fresh 返回。
- Prometheus `/metrics` 应用侧已具备，可输出 runtime/read-model/RabbitMQ/worker/API p95 指标；生产 token 未配置时保持 `404` 安全关闭。

尚未完成“几秒内全部同步”性能 SLO：

- `read_model_refresh_duration_ms.p95` 在 Stage 25 bounded recent sample 口径下仍为 `8301.8155ms`，未达到轻量
  read model enqueue-to-fresh p95 `< 3s`；当前长尾主要来自 `search` p95 `35107.029ms`、`workbench` p95
  `28180.444ms`，以及 `cost_statistics`、`invoice_lifecycle`、`input_invoice_usage` 的 5-7s 级 p95。
- 生产真实登录态页面首包/API p95 仍未采集；Stage 21 已补工具，但需要真实管理员 token/cookie 才能生成最终证据。
- Stage 20 clean top SQL 显示状态页剩余热查询主要是 bounded duration metric、dirty scope group by、
  outbox percentile 和 outbox summary；Stage 24 已收敛 health/metrics percentile 与 outbox summary，Stage 25
  已确认具体慢 projection，仍需生产 pg_stat / EXPLAIN 复测具体 refresh worker 热查询。
- Redis fresh-cache 尚未覆盖全部页面。
- 生产 `FIN_OPS_PROMETHEUS_BEARER_TOKEN`、Grafana dashboard、alert rules 和 scrape 配置尚未落地；`/metrics` 是应用侧指标出口，不等同于完整 Grafana 告警闭环。

下一阶段优先级：

1. 对 `search` 与 `workbench` refresh 做 scope/event drilldown、worker trace、pg_stat 和 EXPLAIN，判断是否存在
   过宽 scope、重复 rebuild、缺索引、低效 join 或可增量化路径。
2. 对 `cost_statistics`、`invoice_lifecycle`、`input_invoice_usage` 做同样分析，把 5-7s p95 收敛到轻量 read model
   `< 3s` 或把明确重型路径纳入局部收敛 `< 10-15s` 的 SLO 分类。
3. 用登录态 HTTP/browser 采样补齐页面首包 p95、关键页面 rows/detail API p95，并与 runtime freshness 关联。
4. 为 fresh gate 后 payload 引入 Redis fresh-cache，确保页面秒开读取的是已通过 readiness/source version 的 snapshot。
5. 在 root-only `/etc/fin-ops/fin-ops.secrets.env` 配置 `FIN_OPS_PROMETHEUS_BEARER_TOKEN`，重启 API 后配置 Prometheus scrape、Grafana dashboard 和 alert rules，把 enqueue-to-fresh latency、pending age、failure rate、RabbitMQ DLQ、consumer count、API p95 和 DB p95 变成持续告警。
6. 对 workbench/search 大表和大索引做 impact analysis，先优化查询/索引/retention，再决定是否分区；不做盲目全库分区。
7. 只有当 worker 并发提高后出现连接等待或连接数接近阈值，再启用 PgBouncer；当前 baseline 为 35/100 connections，PgBouncer 不是当前第一瓶颈。
