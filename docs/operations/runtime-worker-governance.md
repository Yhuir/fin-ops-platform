# Worker + Legacy Read Model 统一治理

本页描述生产和开发环境如何统一管理 `fin-ops-platform` runtime worker 与 legacy SQL read model。
治理闭环不引入 Celery/RQ/Redis Queue 等新任务框架：PostgreSQL durable queue 是任务和
read model 刷新状态事实源，systemd 管 worker 进程，App 只负责写入任务、记录 heartbeat、
暴露健康状态和给出运维提示。

2026-06-26 起，页面读路径目标改为 direct API，read model refresh worker、dirty scope、readiness 和 SLO smoke 是下线对象。新增 worker 只允许用于导入、OA 同步、文件迁移、外部系统同步和受控修复等真实异步任务。目标架构见 `../architecture/direct-api-read-architecture.md`。

本文同时维护 legacy projection production audit、SQL-native hardening、bank detail/legacy projection backfill、
invoice usage/output collection backfill、App Health/workbench performance 和 worker 运维治理的长期结论。
阶段报告和一次性执行记录不再单独保留。

## Hardening 基线

- legacy SQL projection 是下线对象；不得把旧 projection/readiness 恢复为页面 freshness proof。
- 真实后台 rebuild/backfill 应按业务事实或 outbox 批量执行，避免逐行重建。
- 请求线程不做高成本 live rebuild；miss/stale 返回 refresh 状态并 enqueue。
- 关键 query 需要保留 EXPLAIN/性能观测入口；性能结论进入 `monitoring.md` 或本文，而不是保留一次性 audit。
- Redis payload 必须在 fresh gate 后写入，并设置可解释 TTL。

## 管理边界

- App 负责：通过 `RuntimeQueueRepository` 写入 `job.outbox_events`，接收 worker heartbeat，并在 `/health` 与 App Health 中暴露 missing/stale/mismatch/backlog。
- systemd 负责：启动、停止、重启 worker 进程，保持进程常驻。
- deploy helper 负责：从 registry 生成 required worker 矩阵，安装 env，执行 `--check`，重启
  systemd unit，并在发布阶段等待 worker readiness 收敛。
- 用户只看到业务状态：queued、running、refreshing、stale、failed。用户不直接 start/stop worker。
- legacy projection query service / refresh worker 是下线对象；新页面不得新增 freshness/status gate、dirty scope 或 page read-model refresh worker。
  worker 不构造页面 payload，也不读取 HTTP cookie/header。

## 单一事实源

Worker manifest 的唯一事实源是：

```bash
PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_worker_manifest --json
```

常用查询：

```bash
# required worker instance 列表
python -m fin_ops_platform.tools.runtime_worker_manifest --required-instances

# 某个 worker 的 env 模板名
python -m fin_ops_platform.tools.runtime_worker_manifest --env-example workbench

# 某个 worker 的生产 smoke check 命令
python -m fin_ops_platform.tools.runtime_worker_manifest --worker-check-command workbench
```

不要在部署脚本、文档或 runbook 中手写另一份 required worker 列表。不得新增页面 read model refresh event。新增真实后台 worker instance 时，必须先更新 registry，再让 deploy/preflight/monitoring 从 registry 推导；迁移 read model 下线时同步删除 registry、env、systemd、RabbitMQ dispatch 和 smoke 引用。

本地 parity 门禁必须把这些事实源绑在一起：

- `APP_STATUS_READ_MODEL_REGISTRY` 中的每个 legacy read model 必须有对应 required worker registration、refresh event 和 RabbitMQ dispatch event，直至该 read model 下线。
- `tests/test_postgres_migrations.py` 的 read model storage contract 必须覆盖每个 App Status read model；新增 SQL projection 表时不能只写 migration 而不更新本地 schema 基线。
- `fin-ops.rabbitmq-worker.env` 只放共享 RabbitMQ 凭据和 consumer fallback 参数，不设置 `FIN_OPS_QUEUE_BACKEND`；RabbitMQ 灰度切换只能发生在单 worker instance env。
- Redis 生产 env 模板必须和 `RuntimeRedisSettings.from_env()` 保持一致；Redis 只能缓存 fresh gate 后 payload，不能成为 worker/readiness 状态事实源。

## Legacy Read Model 查询合同

页面读路径目标是 direct API，不能再新增页面级 read model freshness/status 合同。保留的 SQL read model 查询只用于后台兼容、运维诊断、worker 闭环或尚未完成的 legacy projection。

保留 legacy 查询时必须满足：

1. 不作为页面 GET 返回前置条件。
2. 不把 `read_model_status`、scope、stale reasons 或 `refresh_enqueued` 透传给页面合同。
3. 缺少 expected freshness contract 属于代码配置错误，应 fail fast，不能默认空 versions 后继续返回 fresh。
4. Redis 只能缓存已证明 fresh 的后台 payload，不能成为 worker/readiness 状态事实源。
5. RabbitMQ 只能作为可选 transport/wakeup，不能作为 read model 状态事实源。

## Read Model 刷新链路

Legacy read-model 刷新请求是下线对象。保留本节只用于识别并删除旧兼容面：

- `ReadModelRefreshGateway` / scope policy registry：legacy compatibility shell；不得作为页面同步路径。
- `job.read_model_dirty_scopes`：legacy page read-model scope 状态表；不得作为 App Health、`/health` 或页面可读证明。
- `job.outbox_events`：真实 worker 可 claim 的事件事实源。
- `RuntimeQueueRepository.enqueue_read_model_refresh(...)`：已删除兼容入口；未登记 `.read_model.refresh` 必须 no-op。
- 事务内 writer：真实业务后台事件使用 `job.outbox_events`；不得直接 SQL 写 legacy read-model scope。

业务 service 不直接 SQL 写 `job.outbox_events` 或 legacy read-model scope 表。真实后台失败或 dead-letter 后由运维 inspect/requeue；页面 read-model dirty/readiness 残留留给 cleanup wave。

如果 downstream refresh handler 抛出 `*_read_model_not_fresh` / `read_model_not_fresh`，runtime worker
会调用 `RuntimeQueueRepository.defer_event(...)`，把该 outbox event 短延迟放回 `pending`，生产模板默认 0.25 秒后
重新 claim。这只用于依赖顺序竞态，不写 fresh readiness、不缓存 payload，也不进入 failed/dead-letter。

### Deleted read-model scope repair

旧 `read-model-scope-contract` deploy helper、`scripts/check-read-model-scope-contracts.py` 和对应服务/测试已删除。页面级 read model scope repair 不再是生产恢复入口；不得通过删除 legacy scope、补投 replacement scope 或写 readiness 来制造“已同步”。

App Status 仍出现历史 read-model dirty/outbox/readiness 残留时，处理原则是：

- 先判断是否影响当前 direct API 页面读取；direct API 不应依赖这些旧行。
- 对真实后台任务 outbox 使用 `runtime_queue_ops inspect`、`requeue`、`release-stale-processing` 或 `resolve-superseded-processing`。
- 对仅属于已删除页面 read model 的残留，记录为 legacy residue，优先在后续 migration/cleanup wave 删除存储和监控入口，而不是恢复 repair helper。
- 禁止新增页面 `.read_model.refresh` worker、freshness proof 或 scope cleanup 工具。

### Legacy Workbench Projection Residue

Workbench 页面读路径不再保留 active generation 原子发布模型；`read_model.workbench_generations.status='active'`
只属于 legacy storage/migration residue，不再是页面 GET 读路径、readiness proof 或 freshness gate。

如果 legacy Workbench projection 表再次增长，先排查旧写入路径是否回归，再看 `pg_wal` 大小和
`/health/ready`。不得恢复 pruning worker、refresh worker 或页面 freshness gate 来掩盖增长；也不得直接
`VACUUM FULL` 大表，除非根分区或临时表空间已满足重写空间需求。旧 projection 可迁移/删除，但
`app.*`、`job.*` 和 matching/decision facts 不可按 read model 清空。

### Workbench matching source-version recovery

`workbench-matching` worker 是 matching 规则版本发布后的常驻一致性边界。每轮 claim matching scope 前，
worker 会通过 `WorkbenchReconciliationDirtyQueue` / repository 检查
`job.workbench_matching_dirty_scopes.status='completed'` 的 scope run；如果 row 的 `source_versions`
不包含当前 matching source versions（例如 `workbench_matching_rules_version`），repository 使用
`for update skip locked` 把该 scope 原子转回 `dirty`，再由同一 worker 正常 claim、重建候选/decision、
complete。不要手工改 `job.workbench_matching_dirty_scopes` 状态来补指定月份；生产恢复应走发布后的
worker 和只读审计验证。

Workbench matching source version 以 `job.workbench_matching_dirty_scopes`、candidate matches 和
reconciliation decisions 为准；不要通过重建 month/all active generation 来修复 matching 规则版本。

## 生产启动合同

生产 worker 只使用 registration contract：

```bash
python -m fin_ops_platform.app.worker \
  --registration workbench \
  --worker-instance workbench \
  --check
```

`--check` 必须在重启前通过，输出至少包含：

- `worker_instance`
- `worker_kind`
- `event_types`
- `handlers`
- `registration.postgres_claim_event_types`
- `registration.rabbitmq_claim_event_types`

旧的 `--enable-*` flag 保留给本地开发和迁移期测试，不作为生产 systemd 主合同。

## 开发者日常操作

本地检查 worker manifest：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_worker_manifest --json
```

本地检查单个 worker：

```bash
PYTHONPATH=backend/src DATABASE_URL=postgresql://... \
  python3 -m fin_ops_platform.app.worker --registration import --worker-instance import --check
```

服务器查看状态：

```bash
sudo systemctl status 'fin-ops-worker@*.service'
sudo systemctl status fin-ops-worker@workbench.service
sudo journalctl -u fin-ops-worker@workbench.service -n 200 --no-pager
```

服务器重启单个 worker：

```bash
sudo systemctl restart fin-ops-worker@workbench.service
```

重启前先跑对应 check：

```bash
cd /opt/fin-ops/current
set -a
source /etc/fin-ops/fin-ops.worker.workbench.env
set +a
PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.app.worker \
    --registration workbench \
    --worker-instance workbench \
    --check
```

## 发布闭环

`finops-deploy-control activate <release>` 的 worker 顺序是：

1. 执行 PostgreSQL migration。
2. 写入 API、worker、dispatcher release drop-in。
3. 调用 `/usr/local/sbin/finops-ensure-runtime-workers <release-src>`。
4. 重启 API、worker、dispatcher。
5. 等待 `/health` worker readiness 收敛。
6. 输出状态。

worker readiness 不是 systemd active。发布脚本会等待：

- `runtime_infrastructure.missing_required_worker_count == 0`
- `runtime_infrastructure.stale_required_worker_count == 0`
- `runtime_infrastructure.mismatched_required_worker_count == 0`
- 没有 `worker_kind_mismatch`
- 没有 `worker_event_type_mismatch`

默认等待 90 秒，可用 `FINOPS_WORKER_READY_TIMEOUT_SECONDS` 调整。超时应视为发布失败，不能继续把
“进程已启动”当成“worker 已就绪”。

Worker 在收到 `SIGTERM` 或 `SIGINT` 时必须释放当前持有的 PostgreSQL outbox lease：如果事件仍由当前
`worker_id` 以 `processing` 状态持有，worker 将其恢复为 `pending`、清理 lock、回退本次 claim 增加的
`attempts`，并写入 `raw_payload.runtime_shutdown_release`。这样发布重启或 systemd stop 不应再让页面等待
`FIN_OPS_WORKER_LOCK_TIMEOUT_SECONDS` 默认 300 秒后才重新 claim。该 release 只适用于同一 worker lock，
不能释放其他 worker 持有的事件。

2026-06-12 Stage 6 生产发布 `main-3933b00f-stage6-202606122329` 已验证该路径：发布期间
`fin-ops-worker@workbench.service` 两次 stop 均记录 `runtime_worker.event_released`，
后续 `job.outbox_events` processing lease 及时释放并重新 claim。该验证只证明发布/重启不再依赖 300 秒
lock timeout；单个重型 read model rebuild 的执行时间仍需通过 worker 增量化、索引/分区和缓存阶段优化。

## RabbitMQ Real Consumer 运维

RabbitMQ 是 worker transport/wakeup，不是状态事实源。切换前后都必须以 PostgreSQL durable outbox 和 worker heartbeat 为准：

- `job.outbox_events`

生产启用 required RabbitMQ real consumers 的顺序：

1. 发布包含 RabbitMQ preflight、systemd env hook 和 consumer clean interrupt 的 release。
2. 确认 RabbitMQ topology env 只加载给 bootstrap，不加载给 API 或 worker。
3. 执行 required-only preflight：

   ```bash
   cd /opt/fin-ops/current
   set -a
   source /etc/fin-ops/fin-ops.api.env
   source /etc/fin-ops/fin-ops.rabbitmq-monitoring.env
   set +a
   PYTHONPATH=/opt/fin-ops/current/backend/src \
     /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.run_rabbitmq_staging_preflight \
       --json \
       --output /tmp/finops-rabbitmq-staging-preflight.json
   ```

   默认只检查 registry 中 `required=true` 且 `rabbitmq_eligible=true` 的 worker。只有本次明确启用
   optional worker 时才加 `--include-optional-workers`。

4. 如果 `/health/ready.runtime_infrastructure.rabbitmq_metric_error` 是 queue/DLQ missing，先使用
   `/etc/fin-ops/fin-ops.rabbitmq-topology.env` 执行 topology apply，再重新检查 Management metrics。
5. 创建或更新 root-only `/etc/fin-ops/fin-ops.rabbitmq-worker.env`，只写共享 `RABBITMQ_URL`。该文件
   权限必须是 `0600 root root`，且不得设置 `FIN_OPS_QUEUE_BACKEND`。
6. 备份准备切换的 `/etc/fin-ops/fin-ops.worker.<instance>.env` 到带时间戳的目录。
7. 逐个或按小批量把 required eligible worker 的 per-instance env 改为 `FIN_OPS_QUEUE_BACKEND=rabbitmq`，
   重启对应 `fin-ops-worker@<instance>.service`。
8. 每批切换后检查：

   ```bash
   curl -fsS http://127.0.0.1:18001/health/ready
   rabbitmqctl -p /finops list_queues name messages consumers messages_unacknowledged
   ```

验收条件：

- required event queue 均有 consumer，且 `messages`、`messages_unacknowledged` 不持续增长。
- RabbitMQ DLQ 为 0；若有 DLQ，必须先确认 PostgreSQL `job.outbox_events` 是否存在对应 `event_id`。
- `/health/ready.runtime_infrastructure.rabbitmq_metric_error=null`。
- `/health/ready.runtime_infrastructure.rabbitmq_queue_depth=0` 或短时间内下降。
- `/health/ready.runtime_infrastructure.rabbitmq_consumer_count` 覆盖已切换 required queues。
- PostgreSQL `job.outbox_events` 没有 active failed/dead-lettered current blocker。

如果 RabbitMQ DLQ 中 envelope 没有 PostgreSQL outbox 对应行，它是 transport orphan，不是 read model
事实 blocker。处理顺序是先导出审计摘要，再 purge 该 DLQ；禁止反向根据 broker-only envelope 写入
PostgreSQL done/fresh。

生产 Stage 9 已验证 required worker cutover：`main-99a98feb-stage9-202606130000` 切换后
`rabbitmq_consumer_count=15`、`rabbitmq_queue_depth=0`、`rabbitmq_dlq_count=0`、
`rabbitmq_metric_error=null`，同时 PostgreSQL outbox 与 worker heartbeat 保持收敛。

回滚步骤：

1. 从切换前备份目录恢复 `/etc/fin-ops/fin-ops.worker.<instance>.env`，或把目标实例改回
   `FIN_OPS_QUEUE_BACKEND=postgres`。
2. 重启对应 worker unit。
3. 检查 `/health/ready.runtime_infrastructure` 的 required worker missing/stale/mismatch 为 0。
4. 检查 PostgreSQL durable outbox 和 worker heartbeat 是否收敛。
5. RabbitMQ 残留消息只按 transport envelope 处理；不要把清空 RabbitMQ 当成 read model 修复。

## App Status Readiness Convergence

`app_status_readiness_backfill` 已删除。不得再通过 backfill 或批量 `insert fresh` 修复页面 read model readiness；App Health 只能展示真实 worker、outbox、RabbitMQ、dependency 和 direct API facts。

### Cost Statistics Scope Readiness

`cost-tax`、`cost-statistics`、`tax-offset`、`invoice-lifecycle` 和 `invoice-lifecycle-secondary` page read-model worker lanes 已删除。成本统计、税金抵扣和发票生命周期页面验收走 direct API / query service / export regression，不再以 scope readiness 或 enqueue-to-fresh 作为页面证明。

成本统计 scope 分为：

- 父 scope：`active:all`、`all:all`。
- 月份 shard：`active:YYYY-MM`、`all:YYYY-MM`。

处理规则：不要恢复 `cost_statistics.read_model.refresh` / `tax_offset.read_model.refresh` worker lane、readiness proof 或 dirty scope repair。若 direct API 性能退化，优化 query service、索引或 canonical facts，不恢复页面 read model。

## 健康字段

`/health` 中的 `runtime_infrastructure` 是 App 对 worker 的管理入口。关键字段：

- `missing_required_worker_count`：required registration 没有匹配 instance heartbeat。
- `stale_required_worker_count`：required registration 有 heartbeat 但超过 stale threshold。
- `mismatched_required_worker_count`：heartbeat 的 kind 或 configured event types 与 registry 不一致。
- `worker_metrics[]`：每个 expected instance 的明细。

`runtime_infrastructure` 还暴露 runtime 运维入口：

- `queue_backlog`：outbox event 状态汇总。
- `pending_outbox_events_by_scope`：按 event/scope 定位 pending outbox。

每行 `worker_metrics` 至少应包含：

- `worker_instance`
- `worker_kind`
- `expected_worker_kind`
- `expected_event_types`
- `configured_event_types`
- `expected_transport`
- `heartbeat_lag_seconds`
- `warning_code`

## 用户侧表现

用户不需要知道 worker 进程名。页面只展示与业务相关的状态：

- `queued`：任务已进入 durable queue，等待 worker claim。
- `running`：后台 job 已被 worker 处理。
- `refreshing`：后台 outbox/job 正在处理，页面按 direct API 返回当前事实或明确 loading。
- `stale`：数据已经过期，App Health 会提示 worker 或 dependency 未收敛。
- `failed`：worker 处理失败或任务进入 failed/dead-letter 状态。

运维侧 heartbeat 可能看到 `deferred`：表示 worker 已识别依赖尚未 ready，并将事件短延迟回
`pending`。用户侧仍应表现为 `refreshing`，不能把 deferred 解释为已同步。

当 worker 缺失或 stale 时，App 不直接启动 worker；App Health 负责把问题定位到具体 worker instance，
运维通过 manifest CLI、systemctl、journalctl 和 deploy helper 处理。

## 运维修复流程

查看 outbox 汇总：

```sql
select event_type, status, count(*)
from job.outbox_events
group by event_type, status
order by event_type, status;
```

定位失败事件：

```sql
select event_id, event_type, scope_type, scope_key, status, attempts, last_error, updated_at
from job.outbox_events
where status in ('failed', 'dead_lettered')
order by updated_at desc
limit 50;
```

修复代码或配置后重放：

```bash
PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops inspect --event-id <uuid>

PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops requeue \
    --event-id <uuid> \
    --reason operator_repair
```

RabbitMQ worker 下如果 PostgreSQL `processing` event 已超过 lock timeout 且没有对应 envelope 被消费，先处理已被更新同
dedupe event 覆盖的旧 `processing`，再释放仍需真实重跑的 stale `processing`。两步都必须先 dry-run；
superseded resolution 只清理旧重复事件，release 只会重新 publish/处理，不会伪造 readiness：

```bash
PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops resolve-superseded-processing \
    --dry-run \
    --stale-after-seconds 300 \
    --event-type <real-background-event-type> \
    --limit 100 \
    --reason rabbitmq_stale_processing_superseded

PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops resolve-superseded-processing \
    --execute \
    --stale-after-seconds 300 \
    --event-type <real-background-event-type> \
    --limit 100 \
    --reason rabbitmq_stale_processing_superseded
```

随后释放仍需重跑的 stale processing：

```bash
PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops release-stale-processing \
    --dry-run \
    --stale-after-seconds 300 \
    --event-type <real-background-event-type> \
    --limit 100 \
    --reason rabbitmq_stale_processing_repair

PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops release-stale-processing \
    --execute \
    --stale-after-seconds 300 \
    --event-type <real-background-event-type> \
    --limit 100 \
    --reason rabbitmq_stale_processing_repair
```

`resolve-dead-letter` 和 `resolve-covered-dead-letters` 已删除，因为它们依赖 legacy readiness/dirty-scope proof。不要直接 SQL 把 `dead_lettered` 改成 `done`；可重放事件走 `requeue`，被更新同 dedupe event 覆盖的旧 `processing` 走 `resolve-superseded-processing`，其余页面 read-model 历史残留留给后续 migration/cleanup wave。

重放后必须确认：

- 对应 worker heartbeat fresh 且 `warning_code` 为空。
- outbox event 不再 failed/dead-letter。
- 页面 API 仍按 direct business contract 验证。

## 统一关系与发票生命周期分发回填顺序

涉及 OA、银行流水、进项发票、销项发票通用关系展示和发票生命周期展示的后台 projection 回填，必须先回填
canonical relation facts，再验证仍保留的真实后台任务。`workbench_relation` 和 `invoice_lifecycle` read model worker 已下线，不再作为回填前置条件。

1. 确认 `app.workbench_pair_relations`、`read_model.workbench_reconciliation_decisions` 和相关 canonical invoice/OA/bank facts 已完成导入或修复。
2. 运行目标页面 direct API smoke，验证关系上下文、空关系、候选关系和已确认关系展示正确。
3. 需要后台任务时，只 enqueue 真实导入、OA 同步、文件迁移、外部系统同步或受控修复任务；不得 enqueue 页面 read model refresh。
4. 页面验证以 direct API 业务结果为准；legacy stale/missing 只能作为历史诊断信息，不能让下游页面用旧 SQL、pair relation snapshot 或页面私有 lifecycle 规则同步补数据伪装 fresh。

## Legacy ensure refresh 边界归档

`dependency_not_fresh`、`api_*`、`pending_invoice_sql_projection`、`bank_detail_relation_tags_read`、
`workbench_relation_write_precondition`、`downstream_bank_tag_read` 曾属于 ensure/wakeup 类刷新请求。该机制只作为
legacy archive 保留；当前页面读取不得依赖 ensure refresh、gateway coalesce 或 page read-model source version。

真实写入原因，例如 `workbench_relation_changed`、`confirm_link`、`withdraw_link`、导入/设置/标签变更，应返回
affected scope/ids/months 或写真实 outbox/lifecycle side effect，再由页面 direct API 重读证明结果。
