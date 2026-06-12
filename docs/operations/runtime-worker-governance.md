# Worker + Read Model 统一治理

本页描述生产和开发环境如何统一管理 `fin-ops-platform` runtime worker 与 SQL read model。
治理闭环不引入 Celery/RQ/Redis Queue 等新任务框架：PostgreSQL durable queue 是任务和
read model 刷新状态事实源，systemd 管 worker 进程，App 只负责写入任务、记录 heartbeat、
暴露健康状态和给出运维提示。

本文同时维护 read model production audit、SQL-native hardening、bank detail/read model backfill、
invoice usage/output collection backfill、App Health/workbench performance 和 worker 运维治理的长期结论。
阶段报告和一次性执行记录不再单独保留。

## Hardening 基线

- SQL-native read model 必须有 source version guard，避免读取旧 projection 并标记为 fresh。
- rebuild/backfill 应按 scope 批量执行，避免逐行重建。
- 请求线程不做高成本 live rebuild；miss/stale 返回 refresh 状态并 enqueue。
- 关键 query 需要保留 EXPLAIN/性能观测入口；性能结论进入 `monitoring.md` 或本文，而不是保留一次性 audit。
- Redis payload 必须在 fresh gate 后写入，并设置可解释 TTL。

## 管理边界

- App 负责：通过 `RuntimeQueueRepository` 写入 `job.outbox_events`、`job.read_model_dirty_scopes`，
  接收 worker heartbeat，并在 `/health` 与 App Health 中暴露 missing/stale/mismatch/backlog。
- systemd 负责：启动、停止、重启 worker 进程，保持进程常驻。
- deploy helper 负责：从 registry 生成 required worker 矩阵，安装 env，执行 `--check`，重启
  systemd unit，并在发布阶段等待 worker readiness 收敛。
- 用户只看到业务状态：queued、running、refreshing、stale、failed。用户不直接 start/stop worker。
- read model query service 负责：通过统一 freshness/status gate 判定是否可读 SQL projection；
  missing、dirty、schema mismatch、source version mismatch 都必须返回 refreshing 并入队。
- read model refresh worker 负责：消费 durable queue event，重建 projection，完成 dirty scope。
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

不要在部署脚本、文档或 runbook 中手写另一份 required worker 列表。新增 read model refresh
event 或 worker instance 时，必须先更新 registry，再让 deploy/preflight/monitoring 从 registry
推导。

## Read Model 查询合同

页面读取 SQL read model 时，必须先经过统一 freshness/status 边界：

1. route 只解析 HTTP 参数并调用 query service。
2. query service 调 `ReadModelQueryGateway` 或同等统一 freshness resolver。
3. fresh 时才允许读取 SQL payload，并且 Redis 只可缓存 fresh gate 之后的 payload。
4. missing、dirty、schema mismatch、source version mismatch 时返回 `read_model_status=refreshing`，
   同时通过 `ReadModelRefreshGateway` 入队。
5. unavailable 时由 route 映射 HTTP 状态，不能把不可用 projection 包装成 fresh。

统一响应至少应包含：

- `read_model_status`
- `read_model_scope_key`
- `source_versions`
- `read_model_stale_reasons`
- `refresh_enqueued`

Redis cache key 必须包含 schema/source versions/generation/query hash。RabbitMQ 只能作为可选
transport/wakeup，不能作为 read model 状态事实源。

## Read Model 刷新链路

刷新请求只允许写入 PostgreSQL durable queue：

- `ReadModelRefreshGateway` / scope policy registry：在写入 durable queue 前统一做 read model scope normalize、validate 和 dedupe；具体 read model 的 scope contract 不放进 `RuntimeQueueRepository`。
- `job.read_model_dirty_scopes`：scope 的刷新状态事实源。
- `job.outbox_events`：worker 可 claim 的事件事实源。
- `RuntimeQueueRepository.enqueue_read_model_refresh(...)`：gateway 和事务内 writer 委托的 durable queue 写入入口。
- 事务内 writer：写业务数据时需要同事务标记 dirty/outbox 时使用。

业务 service 不直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。refresh service
完成 projection 后调用 queue repository 完成 dirty scope；失败或 dead-letter 后由运维 inspect/requeue。

### Read model scope contract 检查

发布前后或 App Status 出现无法解释的 cost statistics failed/refreshing scope 时，先运行只读检查：

```bash
cd /opt/fin-ops/current
set -a
source /etc/fin-ops/fin-ops.api.env
set +a
PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python scripts/check-read-model-scope-contracts.py --json
```

脚本会检查 `job.read_model_dirty_scopes`、`job.outbox_events` 与 `read_model.app_status_readiness`
中不符合当前 registry 的 `cost_statistics` scope，同时扫描 failed/dead_lettered/publish_failed
read model outbox event 是否已有 later done 或 fresh readiness 覆盖。发现 violation、历史已覆盖 failure
或 current uncovered failure 时默认返回非 0，JSON 的 `repair_manifest` 会区分：

- `legacy`：如 `2026-03`、裸 `all`，可归一化为规范 `active/all` scope。
- `invalid`：如未知 project scope，当前 registry 无法解释，不猜测 replacement。
- `covered_historical_outbox_failures`：同一 tenant/event/scope 后续已有 `done` 或 `fresh` readiness，可进入人工 resolve/归档候选。
- `current_uncovered_outbox_failures`：没有后续成功或 fresh 证明，仍然是当前真实 blocker，必须调查 worker、query、数据或重投原因。

dry-run JSON 必须随发布/修复记录归档，至少保留 `repair_manifest.items[]` 的 `scope_type`、`scope_key`、
`event_type`、`status`、`last_error`、`updated_at`、`covered_by`、`proposed_action` 和 `rollback_hint`。

确认报告后执行受控修复：

```bash
PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python scripts/check-read-model-scope-contracts.py \
    --apply \
    --reason production_scope_contract_repair \
    --json
```

`--apply` 只删除非规范的 `cost_statistics` runtime 状态，并通过 `ReadModelRefreshGateway` 补投
可归一化的 replacement scope；不会手工把 readiness 改成 `fresh`，也不会删除 current uncovered
outbox failure。apply 报告必须包含：

- `cleanup.deleted`：本次实际删除的 dirty/outbox/readiness 行数。
- `replacement_enqueue`：补投的规范 replacement scope。
- `repair_audit`：写入 `audit.events` 的修复审计 id。
- `rollback`：基于 `repair_manifest.items[].row` 恢复被删 runtime 行的策略。

如果只需要删除旧状态而不补投 replacement scope，可加 `--no-enqueue-replacements`。如果 dry-run
存在 `current_uncovered_outbox_failures`，先按 App Health/worker log/EXPLAIN 定位并 requeue 或修复
worker/query；不能通过删除 failed event 或批量写 fresh readiness 达成“已同步”。

### Workbench generation retention

Workbench 使用 active generation 原子发布模型，`read_model.workbench_generations.status='active'`
是页面读路径的边界。发布新的月份或 `all` active generation 后，repository 会对本次发布涉及的
scope 执行 bounded retention：保留每个 scope 最近 3 个非 active generation，且只删除超过 1 天的
旧 generation，每次最多 100 个。retention 只删除 `read_model.workbench_*` generation 投影行，
不删除 `app.*`、`job.*` 或其他业务事实；删除条件始终包含 `status <> 'active'`。

retention 是发布后的维护动作，不得让清理失败回滚已经发布成功的 fresh generation。生产环境还应
保留 `finops-prune-workbench-generations.timer` 作为兜底防线，低峰期运行同一保留策略并记录：

```bash
systemctl list-timers finops-prune-workbench-generations.timer
journalctl -u finops-prune-workbench-generations.service -n 100 --no-pager
tail -n 100 /var/log/fin-ops/workbench-generation-prune-$(date +%Y%m%d).log
```

如果 Workbench read model 表再次膨胀，先确认 retention timer、`workbench_generations` 状态分布、
`pg_wal` 大小和 `/health/ready`。不得直接 `VACUUM FULL` 大表，除非根分区或临时表空间已满足重写
空间需求；read model 可重建但业务事实表不可清空。

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

## App Status Readiness Convergence

`read_model.app_status_readiness` 是全局状态 icon 允许变绿的 read model 证明层。上线该表或新增 read model 后，不能用批量 `insert fresh` 伪造状态；必须先用真实 read model 表、active generation、schema/source version 和 row count 做 convergence。

发布或迁移后的固定顺序：

1. 部署包含 `ReadModelReadinessReporter` 和 backfill tool 的版本。
2. 执行 dry-run：

   ```bash
   cd /opt/fin-ops/current
   set -a
   source /etc/fin-ops/fin-ops.api.env
   set +a
   PYTHONPATH=/opt/fin-ops/current/backend/src \
     /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.app_status_readiness_backfill --dry-run
   ```

3. 如果 dry-run 输出 `schema_mismatch`、`source_mismatch`、`failed` 或 `missing`，先修复对应 projection/refresh/rebuild 原因；不要把这些状态改写成 `fresh`。
4. dry-run 判定合理后再 apply：

   ```bash
   PYTHONPATH=/opt/fin-ops/current/backend/src \
     /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.app_status_readiness_backfill --apply
   ```

5. 只读核对 `read_model.app_status_readiness`、`job.read_model_dirty_scopes`、`job.outbox_events`、`job.runtime_worker_heartbeats` 和 `/api/app-health.app_status`。如果还有 dirty scope、outbox backlog、worker stale/missing 或 dependency issue，global icon 仍应保持 yellow/red。

空业务结果可以是 `fresh`，但必须有真实生成事实；没有 readiness 记录的 read model 必须显示 `missing`，不能因为当前没有 dirty scope 而显示 ready。

### Cost Statistics Scope Readiness

`cost-tax` worker 同时处理 `cost_statistics.read_model.refresh` 与 `tax_offset.read_model.refresh`。成本统计是跨银行流水、发票、OA 关系、项目归因和费用分类的派生 read model，因此 App Status 必须展示 scope 级 readiness，而不是只显示一个聚合后的 `cost_statistics=failed`。

成本统计 scope 分为：

- 父 scope：`active:all`、`all:all`。
- 月份 shard：`active:YYYY-MM`、`all:YYYY-MM`。

处理规则：

- refresh `active:YYYY-MM` 或 `all:YYYY-MM` 时，worker 从对应工作台月份 read model 构建成本统计 shard，发布成功后重新入队同 project scope 的父 scope，推动全期间视图收敛。
- refresh `active:all` 或 `all:all` 时，worker 先检查对应月份 shard readiness。缺失、stale 或 failed 的 shard 通过 `ReadModelRefreshGateway` 入队，父 scope 记录 `refreshing`，不完成 dirty scope，不伪造 `fresh`。
- 所有所需月份 shard fresh 后，worker 从 `read_model.cost_statistics_rows` 中的月份 rows 聚合生成父 scope，原子写入 `read_model.cost_statistics_read_models` snapshot，并写入父 scope `fresh` readiness。`read_model.cost_statistics_rows` 只承载月份 shard 明细，不承载 `active:all` / `all:all` parent rows。
- 父 scope 不直接读取 `read_model.workbench_groups(scope_key='all')` 的全量 JSON payload；工作台 `all` scope 超时不能再成为成本统计全期间父 scope rebuild 的关键路径。
- 父 scope failed/unavailable 代表成本统计主体验不可用，App Status domain 可以 blocked/red。
- 单个月份 shard failed/unavailable 只代表该分片需要重试，App Status domain 应保持 busy/yellow，并暴露 `read_model_scopes[].scope_key`、`last_error` 和 `updated_at`。
- historical failed readiness 只能由同一 `read_model_key + scope_type + scope_key` 的真实 successful rebuild 覆盖；运维不得手工改写 readiness 为 fresh。
- 重新入队必须走 `ReadModelRefreshGateway` 或受控运维工具，保留 dirty scope/outbox 事实链路。

## 健康字段

`/health` 中的 `runtime_infrastructure` 是 App 对 worker 的管理入口。关键字段：

- `missing_required_worker_count`：required registration 没有匹配 instance heartbeat。
- `stale_required_worker_count`：required registration 有 heartbeat 但超过 stale threshold。
- `mismatched_required_worker_count`：heartbeat 的 kind 或 configured event types 与 registry 不一致。
- `worker_metrics[]`：每个 expected instance 的明细。

`runtime_infrastructure` 还暴露 read model/backlog 运维入口：

- `queue_backlog`：outbox event 状态汇总。
- `dirty_scopes`：dirty scope 状态汇总。
- `pending_outbox_events_by_scope`：按 event/scope 定位 pending refresh。
- `dirty_scopes_by_scope`：按 scope 定位刷新卡住的位置。
- `stale_dirty_scope_count` 和 `stale_dirty_scopes[]`：超过阈值仍未完成的 scope。

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
- `refreshing`：read model 已发起刷新，页面可展示旧数据或刷新提示。
- `stale`：数据已经过期，App Health 会提示 worker 或 read model 未收敛。
- `failed`：worker 处理失败或任务进入 failed/dead-letter 状态。

当 worker 缺失或 stale 时，App 不直接启动 worker；App Health 负责把问题定位到具体 worker instance，
运维通过 manifest CLI、systemctl、journalctl 和 deploy helper 处理。

## 运维修复流程

查看 read model dirty/outbox 汇总：

```sql
select scope_type, status, count(*)
from job.read_model_dirty_scopes
group by scope_type, status
order by scope_type, status;

select event_type, status, count(*)
from job.outbox_events
where event_type like '%.read_model.refresh'
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

如果 dead-letter 来自历史 invalid-scope cost statistics 事件，优先使用 `scripts/check-read-model-scope-contracts.py`
检查和清理同类 legacy/invalid scope，避免逐个重放必然再次失败的旧事件。对于其他 read model，且当前版本
已经通过真实 readiness convergence 证明对应 read model fresh，可以使用受控 resolve：

```bash
PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops resolve-dead-letter \
    --event-id <uuid> \
    --reason readiness_converged_obsolete_invalid_scope
```

`resolve-dead-letter` 只适用于注册的 read model refresh event。命令会先检查：

- 事件当前必须仍是 `dead_lettered`。
- 对应 `read_model_key` 在 `read_model.app_status_readiness` 中已经有 `fresh` 证明。
- 同一 `scope_type` 没有 `pending`、`processing` 或 `failed` dirty scope。

不满足这些条件时命令必须拒绝处理。禁止直接 SQL 把 `dead_lettered` 改成 `done`；需要保留
`raw_payload.operator_resolution` 审计记录。

重放后必须确认：

- 对应 worker heartbeat fresh 且 `warning_code` 为空。
- outbox event 不再 failed/dead-letter。
- dirty scope 进入 done 或明确仍在 processing。
- API 返回 fresh，或在 worker 尚未完成时返回明确 refreshing。

## 统一关系与发票生命周期分发回填顺序

涉及 OA、银行流水、进项发票、销项发票通用关系展示和发票生命周期展示的页面，必须先回填
`workbench_relation` read model，再回填 `invoice_lifecycle` read model，最后回填页面自己的 read model。推荐顺序：

1. 启动并检查 `workbench-relation` worker，确认
   `workbench_relation.read_model.refresh` 可 claim。
2. 对历史月份 enqueue `workbench_relation` scope；`all` 只作为 fan-out 入口，实际重建必须落到
   `YYYY-MM` shard。
3. 启动并检查 `invoice-lifecycle` worker，确认
   `invoice_lifecycle.read_model.refresh` 可 claim。
4. 等 `read_model.workbench_relation_rows/groups` 对目标月份 fresh 后，再 enqueue
   `invoice_lifecycle` scope；`all` 同样只作为 fan-out 入口。
5. 等 `read_model.invoice_lifecycle_rows` 对目标月份 fresh 后，再 enqueue
   `pending_invoice`、`bank_detail`、`input_invoice_usage`、`output_invoice_collection`、
   `oa_pending_payment`、`no_oa_bank_batch`、`cost_statistics`、`tax_offset`、`search`。
6. 页面验证以 facade/read model 状态为准：如果 `workbench_relation` 或 `invoice_lifecycle` stale/missing，
   下游页面不能用旧 SQL、pair relation snapshot 或页面私有 lifecycle 规则同步补数据伪装 fresh。
