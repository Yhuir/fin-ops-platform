# Worker + Read Model 统一治理

本页描述生产和开发环境如何统一管理 `fin-ops-platform` runtime worker 与 SQL read model。
治理闭环不引入 Celery/RQ/Redis Queue 等新任务框架：PostgreSQL durable queue 是任务和
read model 刷新状态事实源，systemd 管 worker 进程，App 只负责写入任务、记录 heartbeat、
暴露健康状态和给出运维提示。

本文同时维护 read model production audit、SQL-native hardening、bank detail/read model backfill、
invoice usage/output collection backfill、App Health/workbench performance 和 worker 运维治理的长期结论。
阶段报告和一次性执行记录不再单独保留。

## 可逆关系 checkpoint 证据边界

- mutation 仍只走 Workbench action API → relation command → UoW；runner 不写 relation、outbox、dirty、readiness 或 read model。
- mutation 与 worker 证据通过 durable idempotency committed record 的精确 event ID 集关联；`started_at` 只是下界，不能让同 profile 并发事件串入。合法 optional scope 可记录为 skipped/pass，未知 scope 或未匹配 event ID fail closed。
- bank+invoice、bank+turnover closure、bank+OA+invoice 的可执行 profile pair、mutation contract 与 affected/non-consumer 页面由部署包内 `write_operation_e2e_smoke.REVERSIBLE_RELATION_*_CONTRACTS` 负责；`docs/dev/write-operation-impact-matrix.json` 是由测试机械约束的运维/架构镜像，不是运行时文件 I/O。bank+invoice 必须包含真实 `cost_statistics` fan-out；完整三方关系还必须包含 `oa_pending_payment`；税金抵扣是 Workbench relation 非消费者，不得产生 relation dirty/outbox。bank+turnover 只走正式 turnover closure confirm/withdraw，不得用 Workbench profile 反向伪造事件。
- discovery 不再把普通生产 turnover/Workbench/no-OA 事实转换成可执行 relation mutation；只保留 read-only context。现有 bank-flow submit 仍由自己的正式 owner 生成场景。

## Hardening 基线

- SQL-native read model 必须有 source version guard，避免读取旧 projection 并标记为 fresh。
- rebuild/backfill 应按 scope 批量执行，避免逐行重建。
- 请求线程不做高成本 live rebuild；miss/stale 返回 refresh 状态并 enqueue。
- 关键 query 需要保留 EXPLAIN/性能观测入口；性能结论进入 `monitoring.md` 或本文，而不是保留一次性 audit。
- Redis payload 必须在 fresh gate 后写入，并设置可解释 TTL。

## System Audit 运维边界

- `GET /api/operations/app-health/page-audit?page=app-health-operations` 是 admin-only 只读证明入口，不是 refresh、repair 或 deploy 操作。
- 一次 System Audit 只打开一个 outer `REPEATABLE READ READ ONLY` PostgreSQL snapshot，在该 snapshot 内执行其余 16 页 proof、App Health inventory 重算，以及 read model/worker/current durable queue 合同检查。不得串行调用 16 个独立页面 HTTP Audit 后聚合为系统绿色。
- 数据库证明、运行时观测和外部证据是三个独立 evidence plane。RabbitMQ transport、HTTP request metrics 等 point-in-time observation 不能写入数据库 snapshot 结论；银行/OA/发票/ETC 外部 control evidence 必须来自经审计登记的独立 complete manifest。缺失保持 `unknown/unproven`；latest revoked/expired/mismatch 为 `fail/unproven`；四域 exact pass 也只能声明截至 evidence observed/source snapshot 与当前 system snapshot 已证明。登记与撤销 runbook 见 `external-control-evidence.md`。
- Audit 发现 drift 后，运维人员先保存 `system_audit_id`、snapshot identity、issue codes 和当前 release/version set，再依赖 upstream → downstream 顺序通过正式 gateway/durable queue 制定受控 refresh 或数据修复。Audit handler 本身永远不 enqueue、不写业务表、不写 read model、不伪造 fresh。
- 绿色结论只属于报告中的 immutable snapshot；任何后续 dashboard refresh、导入、配对、撤销、设置变更或 worker 发布都使旧绿色不能代表当前状态，必须重新运行 System Audit。

## 管理边界

- App 负责：通过 `RuntimeQueueRepository` 写入 `job.outbox_events`、`job.read_model_dirty_scopes`，
  接收 worker heartbeat，并在 `/health` 与 App Health 中暴露 missing/stale/mismatch/backlog。
- file import confirm 必须先写 `job.import_jobs` 再通过同一 repository/gateway 写 `import.process.requested` outbox；`FIN_OPS_IMPORT_PROCESSING_BACKEND` 只允许 `postgres` 或 `rabbitmq`。PostgreSQL polling 是 durable 基线，RabbitMQ 只是 wakeup；API 进程不得 inline confirm，queue/repository 缺失必须 `503` fail closed。
- ETC invoice confirm 遵循同一 durable 基线，但 preview 还必须先登记 `app.etc_import_sessions`、session files 和 verified file objects。独立 worker 从 session 重载 ZIP；Web 进程内存、inline `run_job` 和先改 task 再 enqueue 都不是允许的生产路径。
- systemd 负责：启动、停止、重启 worker 进程，保持进程常驻。
- deploy helper 负责：从 registry 生成 required worker 矩阵，安装 env，执行 `--check`，重启
  systemd unit，并在发布阶段等待 worker readiness 收敛。release deploy 解包并校验 release layout 后，
  会先通过 `/usr/local/sbin/finops-deploy-control self-update <release-name>` 安装 release 内的
  `deploy/oa/bin/finops-deploy-control.sh`，再执行完整 helper contract、`check-release` 和 `activate`，
  避免新增 versioned timer/helper 时被旧远端 deploy-control 卡住。首次接入或旧 helper 不支持
  `self-update` 时仍需要一次 root bootstrap。`/usr/local/sbin/finops-ensure-runtime-workers`
  仍是预安装的 root helper；release deploy 只校验该 helper 的合同并通过 `finops-deploy-control activate`
  间接调用它，不在发布链路中覆盖该 runtime worker helper。
- 当前 release 的 worker registry 同时是生产实例白名单。`activate` 在重启服务前枚举全部已加载
  `fin-ops-worker@*.service`，对已启用、运行或失败但不在 registry 中的实例执行 stop/disable；不删除实例 env，
  因而可通过恢复含该 registration 的 release 受控回滚。禁止把 WIP 性能 worker 或手工 systemd 实例留在
  registry 外长期运行，也禁止通过给未知实例补空参数来绕过 registration contract。
- PostgreSQL durable queue worker 的 idle poll 基线是 `0.05s`；单一 `workbench` worker 使用 `0.01s`，同时处理月份 shard 与 `all` fan-out command。普通 relation 写入只要求具体月份和 relation/downstream read model 收敛；`month=all` 页面直接组合 active 月分片。`all` command 只列出月份并经统一 gateway 投递，不构建或发布全局 generation。新增 read model / 写后 fan-out worker 不能把
  `--poll-interval-seconds 2`、`0.25`、`0.1` 或 `5` 作为默认值；`workbench-matching` 是独立脏 scope 批处理例外，
  可保留显式 5s poll。发布 helper 会把已有 env 中精确命中的历史 `--poll-interval-seconds 2|0.25|0.1|0.05`
  迁移到当前 release env 示例声明的 poll 值。该迁移不会重写 RabbitMQ 灰度或自定义事件。
- OA 待付款使用 required registration `oa-pending-payment`，只 claim `oa_pending_payment.read_model.refresh`；`invoice-usage-collection` 只保留 `input_invoice_usage` / `output_invoice_collection`。release helper 必须幂等删除既有 shared worker env 中精确命中的 OA handler/event 参数，不能让旧 env 覆盖新 registry 边界。OA projector不得访问Mongo/MySQL或复用shared invoice projector。普通业务变化只enqueue精确月份；显式`all`作为低优先级fan-out，用于首次回填、repair或backfill。
- OA release统一切换时不允许两个worker同时claim OA event。先由registry激活新`oa-pending-payment`实例并确认shared invoice registration已不含OA handler，再执行`oa.sync:all`建立completed/admission/payment-status snapshot和watermark；该同步必须使用单次 dual-view source batch，任一 form 失败整轮不提交并记录 failed run。核对 `scanned_projection_count`、`scanned_completed_count`、`scanned_in_progress_count` 后，低优先级enqueue `oa_pending_payment:all`。全部月份dirty/outbox drain并Audit通过前，页面保持refreshing且不展示旧rows。
- OA页面写回MySQL成功后由API进程通过窄PG snapshot writer同事务更新status、月份watermark和outbox；PG失败返回可重试错误。运维不得直接SQL补read model或把MySQL当前值当作页面fresh证明；可重试命令或重新运行OA sync。
- 周期性 `oa.sync` 必须是 change-driven：completed OA、status、admission 与上一 snapshot 一致时只记录 run/watermark，不更新 projection/status/admission 的业务时间戳，也不 fan-out Workbench/OA/成本等页面 refresh。admission/payment-status-only 变化只刷新 OA 待付款；只有 completed canonical 真实新增、修改或删除才允许 shared owner fan-out。snapshot repository 不得直接 enqueue Workbench/shared consumers。若无对应业务变化却持续出现跨页面 dirty/outbox 或 `app.oa_applications.updated_at` 漂移，按同步 owner 回归处理，禁止通过扩大 worker 数量掩盖写放大。
- PostgreSQL durable queue worker 的空轮询 heartbeat 必须节流。`idle` 只证明 worker 存活和当前无可 claim event，
  不能每个 0.05s poll 都写 `job.runtime_worker_heartbeats`；`processing`、`deferred`、`failed`、`stopping`、`stopped`
  必须即时写入，保证 App Health 和故障定位不丢关键状态。
- 同一 event type 确有当前吞吐隔离需求时，只允许使用 worker registry / worker env 暴露的 claim scope include/exclude。
  Workbench 不拆 lane：单一 `workbench` registration claim 月份 shard 与 `all` fan-out command。scope policy 仍是
  read model contract 的事实源，queue 层只做 claim，不承载业务 scope 校验。
- `job.outbox_events` active queue claim hot path 必须保留 `outbox_events_claim_event_type_priority_idx`。
  该索引按 `event_type/status/priority rank/available_at/created_at/id` 支撑 worker lane claim，减少 grouped read model smoke
  扫描无关 event type 的 pickup 尾延迟。它只优化 PostgreSQL I/O，不改变 priority、dedupe、dirty scope、RabbitMQ 或 readiness 语义。
- read model refresh 的 enqueue-to-done SLO 以 `job.outbox_events.available_at -> processed_at` 为准。
  事务内 writer 必须用 `clock_timestamp()` 写实际入队可处理时间；`created_at` 不再作为长事务内 worker drain 的判断起点。
  HTTP 写请求本身的耗时继续由 `workbench_action_timing` / route timing 观测，不能和 worker drain 混算。
- 用户只看到业务状态：queued、running、refreshing、stale、failed。用户不直接 start/stop worker。
- read model query service 负责：通过统一 freshness/status gate 判定是否可读 SQL projection；
  missing、dirty、schema mismatch、source version mismatch 都必须返回 refreshing 并入队。
- read model refresh worker 负责：消费 durable queue event，重建 projection，完成 dirty scope。
  worker 不构造页面 payload，也不读取 HTTP cookie/header。

## 单一事实源

生产运维命令默认先读取当前 active release：

```bash
release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"
```

Worker manifest 的唯一事实源是：

```bash
PYTHONPATH="$release_src/backend/src" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_worker_manifest --json
```

常用查询：

```bash
# required worker instance 列表
python -m fin_ops_platform.tools.runtime_worker_manifest --required-instances

# 全部允许运行的 worker instance 列表
python -m fin_ops_platform.tools.runtime_worker_manifest --instances

# 某个 worker 的 env 模板名
python -m fin_ops_platform.tools.runtime_worker_manifest --env-example workbench

# 某个 worker 的生产 smoke check 命令
python -m fin_ops_platform.tools.runtime_worker_manifest --worker-check-command workbench
```

不要在部署脚本、文档或 runbook 中手写另一份 required worker 列表。新增 read model refresh
event 或 worker instance 时，必须先更新 registry，再让 deploy/preflight/monitoring 从 registry
推导。

本地 parity 门禁必须把这些事实源绑在一起：

- `APP_STATUS_READ_MODEL_REGISTRY` 中的每个 read model 必须有对应 required worker registration、refresh event、RabbitMQ dispatch event 和 SLO smoke 计划。
- `tests/test_postgres_migrations.py` 的 read model storage contract 必须覆盖每个 App Status read model；新增 SQL projection 表时不能只写 migration 而不更新本地 schema 基线。
- `read_model_slo_smoke --critical-only` 必须规划所有 critical App Status read model；dry-run 只证明 scope discovery，`--apply` 才证明真实 enqueue-to-fresh worker drain。
- `fin-ops.rabbitmq-worker.env` 只放共享 RabbitMQ 凭据和 consumer fallback 参数，不设置 `FIN_OPS_QUEUE_BACKEND`；RabbitMQ 灰度切换只能发生在单 worker instance env。`RABBITMQ_CONSUMER_POSTGRES_DRAIN_INTERVAL_SECONDS` 当前基线为 `0.05`，避免 RabbitMQ envelope 丢失或 dispatcher 延迟时让 1s read model SLO 卡在 fallback drain。
- Redis 生产 env 模板必须和 `RuntimeRedisSettings.from_env()` 保持一致；Redis 只能缓存 fresh gate 后 payload，不能成为 worker/readiness 状态事实源。

## 固定写操作 smoke 输入

生产 write-operation E2E smoke 不再逐次询问 scenario 或 approval ticket。标准输入由
`fin_ops_platform.tools.write_operation_scenario_discovery` 生成和报告：

- `FIN_OPS_WRITE_E2E_SCENARIO=/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json`
- `FIN_OPS_WRITE_E2E_APPROVAL_TICKET=FINOPS-WRITE-SMOKE-STANDING-20260702`
- 每个 operation 最多写入 1 个受控 scenario，避免同一月份连续撤回造成 Workbench/read model 串行刷新长尾。
- discovery 只读 PostgreSQL 事实并输出候选；真正 apply 仍必须提供真实 OA/Admin auth，但不再需要临时业务 ticket。
- Workbench relation 的 test-owned checkpoint 必须显式执行三步 I/O：先按目标月份读取
  `/api/workbench?month=...` 并捕获 `read_model_version`，再让 preview 与 mutation 同时携带该精确版本；
  confirm 后的 withdraw 必须重新读取版本，禁止复用上一个 generation、隐藏重试或省略写前置条件。
- `finops-deploy-control write-operation-e2e-smoke ... --apply-stdin` 从 stdin 第一行读取 Admin Token、
  第二行读取 standing approval ticket；任一为空都在业务 mutation 前失败，避免把 root-owned env 漂移误判为已授权。
- 同步写超过门禁仍判定为 SLO failure；如果 HTTP 结果已经证明 mutation committed，恢复步骤必须先按该响应的
  精确 `outbox_event_ids` 等待 durable fan-out 收敛，再读取隔离页基线和执行撤回。`202 refreshing`
  不是稳定恢复基线，不能据此跳过撤回或把生产关系留在 active 状态。
- 首批 receipt 完成后，consumer gate 对 `202` / `read_model_not_fresh` / dependency `503` 在总 timeout
  内继续轮询，因为这些状态可由合法链式 fan-out 产生；业务字段断言失败和单次 fresh 响应超过页面 SLO
  不可重试，仍立即失败，防止 eventual consistency 轮询掩盖错误内容或性能退化。
- no-OA withdraw 候选必须同时满足 `app.no_oa_bank_batches.status='submitted'`、`relation.status='active'`
  和 `relation.relation_mode='no_oa_bank_batch'`，不能把 bank-flow rule batch 关系误送到 no-OA endpoint。

| 页面 | apply policy | 生产 smoke operation | approval ticket |
| --- | --- | --- | --- |
| `turnover-ledger` | standing apply | `turnover_manual_closure_or_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `reconciliation-workbench` | standing apply | `workbench_relation_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `workbench-relations` | standing apply | `workbench_relation_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `no-oa-bank-batches` | standing apply | `no_oa_bank_batch_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `bank-flow-rule-batches` | fan-out evidence | `no_oa_bank_batch_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `bank-details` | fan-out evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `bank-account-balance` | fan-out evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `pending-invoices` | fan-out evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `input-invoice-usage` | fan-out evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `output-invoice-collections` | fan-out evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `invoice-lifecycle` | fan-out evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `oa-pending-payments` | fan-out evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `tax-offset` | fan-out evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `cost-statistics` | fan-out evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `search` | fan-out evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `batch-accounting` | fan-out evidence | `workbench_relation_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `imports-bank-transactions` | no standing production apply | staging 或单次审批导入 scenario | 不使用常驻 ticket |
| `imports-invoices` | no standing production apply | staging 或单次审批导入 scenario | 不使用常驻 ticket |
| `imports-etc-invoices` | no standing production apply | staging 或单次审批导入 scenario | 不使用常驻 ticket |
| `settings` | no standing production apply | staging 或单次审批设置变更 scenario | 不使用常驻 ticket |
| `data-safety-reset` | no standing production apply | staging 或单次审批 reset/restore scenario | 不使用常驻 ticket |

## Read Model 查询合同

页面读取 SQL read model 时，必须先经过统一 freshness/status 边界：

1. route 只解析 HTTP 参数并调用 query service。
2. query service 调 `ReadModelQueryGateway` 或同等统一 freshness resolver，并必须声明 `expected_source_versions` 或 `expected_schema_version`。
3. fresh 时才允许读取 SQL payload，并且 Redis 只可缓存 fresh gate 之后的 payload；fresh gate 必须同时带 scope、schema/source metadata proof。
4. missing、dirty、schema mismatch、schema proof missing、source version missing/mismatch 时返回 `read_model_status=refreshing`，
   同时通过 `ReadModelRefreshGateway` 入队。
5. query service 缺少 expected freshness contract 属于代码配置错误，应 fail fast，不能默认空 versions 后继续返回 fresh。
6. unavailable 时由 route 映射 HTTP 状态，不能把不可用 projection 包装成 fresh。

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
- `RuntimeQueueRepository.enqueue_read_model_refresh(...)`：gateway 和单 scope 事务内 writer 委托的 durable queue 写入入口。
- `RuntimeQueueRepository.enqueue_read_model_refreshes_in_transaction(...)`：同一业务事务内已有多个规范 target 时使用的批量入口；它只减少 SQL 往返，仍写同一 `job.read_model_dirty_scopes` / `job.outbox_events`，不得改变 source_version、dedupe、priority、trace_id、readiness 或 RabbitMQ 事实源语义。
- 事务内 writer：写业务数据时需要同事务标记 dirty/outbox 时使用。

业务 service 不直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`。refresh service
完成 projection 后调用 queue repository 完成 dirty scope；失败或 dead-letter 后由运维 inspect/requeue。

Phase 19 受控生产重建使用：

```bash
sudo -n /usr/local/sbin/finops-deploy-control read-model-refresh <release-name> \
  --scope tax_offset=all --scope turnover_ledger=all --dry-run
```

该入口只通过 scope policy、`ReadModelRefreshGateway` 和 durable queue，不直接更新 `read_model.*`、
`app_status_readiness` 或 dirty scope 状态。已由 exact-scope fresh/done 覆盖的 dead letter 只能通过
`runtime-queue-resolve-covered` dry-run 后执行归档；未覆盖 failure 继续阻断 Audit。

当 canonical source versions 未变化、但已证明旧 projection 算法留下错误数据时，受控重建可显式增加
`--force-refresh`。该标志只把 `force_refresh=true` 写入通过 scope policy 校验后的 durable event metadata，
由已登记 projection handler 重算目标 scope；它不直接写 read model、不修改 readiness，也不能替代重建后
的 queue drain、freshness 和只读 Audit 复验。执行前必须先 dry-run 同一组 scopes，且只选择已证明受影响的 scope。
`force_refresh=true` 的 durable request 不得与已有普通 pending/processing refresh coalesce；`all` fan-out 时该 metadata
必须继续传递给每个实际 shard，避免受控重建被静默降级成普通 unchanged-scope refresh。

如果 downstream refresh handler 抛出 `*_read_model_not_fresh` / `read_model_not_fresh`，runtime worker
会调用 `RuntimeQueueRepository.defer_event(...)`，把该 outbox event 短延迟放回 `pending`，生产模板默认 0.25 秒后
重新 claim。这只用于依赖顺序竞态，不写 fresh readiness、不缓存 payload，也不进入 failed/dead-letter。
`cost-statistics` downstream projection 在抛出该异常前只能做一次无队列副作用的 bank-detail dependency snapshot read，并显式检查返回的 freshness。该快照在一个 `REPEATABLE READ READ ONLY` transaction 内同时读取目标月全部 rows、正式关系引用的跨月流水 ID 和全部涉及 scope 的 signatures；旧的 source-version、transaction-id、month-row 三次独立读取不得恢复。不得让
read facade 在该 projection 内部因 `require_fresh=True` 自动 enqueue。同一读取同时承担 status check 和 enqueue 会产生
TOCTOU：dependency event 可在状态读取后、enqueue active-check 前完成/ack，随后过时的 non-fresh 结果又创建同 scope
event。依赖 enqueue 必须由 runtime worker 的异常边界单点负责；API/query miss 的正常 refresh enqueue 合同不受此限制。

### Runtime queue history retention

`job.outbox_events` 和 `job.read_model_dirty_scopes` 是 read model refresh 的 durable queue
事实源，但它们的完成态历史不能无限保留。当前边界如下：

- 代码 owner：`RuntimeQueueRepository.preview_runtime_queue_history_retention(...)` 和
  `RuntimeQueueRepository.prune_runtime_queue_history(...)`。
- 运维入口：`python -m fin_ops_platform.tools.runtime_queue_ops prune-history`，必须显式
  `--dry-run` 或 `--execute`。
- 生产自动化：`finops-prune-runtime-queue-history.timer` 每天执行版本化 helper
  `/usr/local/sbin/finops-prune-runtime-queue-history`。
- 权限：helper 读取 `/etc/fin-ops/fin-ops.postgres-migrator.env`，把
  `FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL` 映射为 `FIN_OPS_POSTGRES_DATABASE_URL` 后运行；
  API/worker role 不获得 delete 权限。
- 默认策略：`keep_days=30`、`keep_recent_per_type=512`、`limit=20000`。

删除安全边界：

- 只删除 `status='done'` 的历史行。
- 不删除 pending、processing、failed、dead-lettered。
- outbox done 行如果同一 tenant/event/scope 仍有 failed/dead-lettered，则保留，避免丢失
  dead-letter repair 的后续成功证明。
- dirty scope done 行如果同一 scope 仍有 pending/processing/failed dirty scope 或非 done outbox，
  则保留，避免误删当前刷新诊断上下文。
- dirty scope done 行还会按 `(tenant_id, scope_type, scope_key)` 永远保留最新一行，避免下一次
  同 scope 入队时 source_version 从旧值回退。
- retention 返回按 event/scope type 聚合的 JSON 统计；生产执行前后必须记录 dry-run/execute
  输出和 `/health/ready`。

手工执行示例：

```bash
set -a
source /etc/fin-ops/fin-ops.common.env
source /etc/fin-ops/fin-ops.postgres-migrator.env
set +a
export FIN_OPS_POSTGRES_DATABASE_URL="$FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL"

PYTHONPATH=/opt/fin-ops/releases/<release>/src/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops prune-history \
  --dry-run --keep-days 30 --keep-recent-per-type 512 --limit 20000
```

### Read model scope contract 检查

发布前后或 App Status 出现无法解释的 cost statistics failed/refreshing scope 时，先运行只读检查：

```bash
sudo -n /usr/local/sbin/finops-deploy-control read-model-scope-contract <release-name> --json
```

脚本会检查 `job.read_model_dirty_scopes`、`job.outbox_events` 与 `read_model.app_status_readiness`
中不符合当前 registry 的 `cost_statistics` scope，同时扫描未完成或 publish 异常的
read model outbox event 是否已有 later done 或 fresh readiness 覆盖。发现 violation、历史已覆盖 outbox
或 current uncovered failure 时默认返回非 0，JSON 的 `repair_manifest` 会区分：

- `legacy`：如 `2026-03`、裸 `all`，可归一化为规范 `active/all` scope。
- `invalid`：如未知 project scope，当前 registry 无法解释，不猜测 replacement。
- `covered_historical_outbox_failures`：同一 tenant/event/scope 后续已有 `done` 或 `fresh` readiness，可进入人工 resolve/归档候选；字段名沿用历史命名，但 App Status current-effective 口径也会过滤旧 pending/backlog。
- `current_uncovered_outbox_failures`：没有后续成功或 fresh 证明，仍然是当前真实 blocker，必须调查 worker、query、数据或重投原因。

dry-run JSON 必须随发布/修复记录归档，至少保留 `repair_manifest.items[]` 的 `scope_type`、`scope_key`、
`event_type`、`status`、`last_error`、`updated_at`、`covered_by`、`proposed_action` 和 `rollback_hint`。

确认报告后执行受控修复：

```bash
sudo -n /usr/local/sbin/finops-deploy-control read-model-scope-contract <release-name> \
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

### Legacy import fact dirty scope 清理

历史导入路径可能写入 `reason='import_facts_changed'` 的 dirty scope，但对应 `import.fact.changed`
outbox event 已经 `done`，且没有新的 `pending/processing` 事件可被 worker claim。此时 App Status
会继续看到 pending dirty scope，用户表现为导入已可见但全局状态长时间“同步中”。

先运行只读 dry-run：

```bash
scripts/check-read-model-scope-contracts.py --repair orphaned-import-facts --json
```

报告只列出没有 active `import.fact.changed` outbox 可处理的 legacy dirty scope，并给出 `items[].row`
用于回滚。确认这些 scope 已被当前真实 read model refresh 取代，且没有正在运行的导入窗口后，才执行：

```bash
scripts/check-read-model-scope-contracts.py \
  --repair orphaned-import-facts \
  --apply \
  --reason production_orphaned_import_fact_cleanup \
  --json
```

该 repair 只删除 orphaned `job.read_model_dirty_scopes` 行并写审计；不会删除 outbox event、不会写
`read_model.app_status_readiness=fresh`，也不会补投 replacement refresh。清理后必须重新检查
App Status、`job.read_model_dirty_scopes` 非 done 行和 write-operation SLO audit。

### Invalid read model scope 清理

检查 policy 明确判定无效的 read model dirty/outbox runtime 行，例如旧工具误投的
`pending_invoice:all`：

```bash
scripts/check-read-model-scope-contracts.py --repair invalid-read-model-scopes --json
```

确认 manifest 后才允许 apply：

```bash
scripts/check-read-model-scope-contracts.py \
  --repair invalid-read-model-scopes \
  --apply \
  --reason production_invalid_read_model_scope_cleanup \
  --json
```

该 repair 只删除 registry/policy 无法接受的 dirty/outbox/readiness runtime 行，不补投 replacement，
不删除合法但 stale 的 dirty scope。合法 stale scope 应由 worker dependency refresh 自动补投，或通过
对应 read model 的正常 refresh 入口恢复。

### Workbench generation retention

Workbench 使用 active generation 原子发布模型，`read_model.workbench_generations.status='active'`
是页面读路径的边界。发布新的月份或 `all` active generation 后，repository 会对本次发布涉及的
scope 执行 bounded retention：保留每个 scope 最近 1 个非 active generation，并清理其余已被替代的
旧 generation，每次最多 500 个。retention 只删除 `read_model.workbench_*` generation 投影行，
不删除 `app.*`、`job.*` 或其他业务事实；删除条件始终包含 `status <> 'active'`。

retention 是发布后的维护动作，不得让清理失败回滚已经发布成功的 fresh generation。生产环境还应
保留 `finops-prune-workbench-generations.timer` 作为兜底防线，低峰期运行同一保留策略并记录。
该 helper 和 systemd timer 由 `deploy/oa/bin/finops-deploy-control.sh` 在 release activate 时从
`deploy/oa/bin/finops-prune-workbench-generations.sh` 与 `deploy/oa/systemd/finops-prune-workbench-generations.*.example`
安装，生产不得维护漂移的手写 wrapper。默认策略必须与 repository/CLI 保持一致：
`FINOPS_WORKBENCH_PRUNE_KEEP_RECENT=1`、`FINOPS_WORKBENCH_PRUNE_KEEP_DAYS=0`、
`FINOPS_WORKBENCH_PRUNE_LIMIT=500`。

```bash
systemctl list-timers finops-prune-workbench-generations.timer
journalctl -u finops-prune-workbench-generations.service -n 100 --no-pager
tail -n 100 /var/log/fin-ops/workbench-generation-prune-$(date +%Y%m%d).log
```

如果 Workbench read model 表再次膨胀，先确认 retention timer、`workbench_generations` 状态分布、
`pg_wal` 大小和 `/health/ready`。不得直接 `VACUUM FULL` 大表，除非根分区或临时表空间已满足重写
空间需求；read model 可重建但业务事实表不可清空。

当根分区已经接近或达到满盘，按以下顺序处理：先降低 systemd journal 占用，随后只 dry-run
非 active generation 候选并执行一个 bounded batch，接着对 `read_model.workbench_generations`、
`workbench_groups`、`workbench_group_rows`、`workbench_rows`、`workbench_summary`、`workbench_generation_stats`
执行普通 `VACUUM (ANALYZE)`。不要连续盲删大量 read model generation，因为删除会产生 WAL，可能在
满盘状态下进一步压缩可用空间。若清理后 Workbench 仍处于 `refreshing`，必须继续检查 active generation
consistency failure、dirty scope 和 worker defer 原因；不能把磁盘空间恢复误判为 read model 已 fresh。

如果当天大量 superseded generation 已经阻塞 refresh，可执行一次显式清理。该命令仍只删非 active
generation，仍保留每个 scope 最近 1 个非 active generation；`--keep-days 0` 是默认策略：

```bash
set -a
. /etc/fin-ops/fin-ops.common.env
. /etc/fin-ops/fin-ops.secrets.env
set +a
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python \
  -m fin_ops_platform.tools.prune_workbench_generations \
  --execute \
  --keep-recent-generations-per-scope 1 \
  --keep-days 0 \
  --limit 5000
```

emergency 清理后必须重新执行普通 `VACUUM (ANALYZE)`、确认 active generation builder/schema 已更新、
检查 consistency failure 清零、dirty scope 完成和 worker defer 不再重复，最后再跑 Workbench API
耗时 smoke。

### Workbench matching source-version recovery

`workbench-matching` worker 是 matching 规则版本发布后的常驻一致性边界。每轮 claim dirty scope 前，
worker 会通过 `WorkbenchReconciliationDirtyQueue` / repository 检查
`job.workbench_matching_dirty_scopes.status='completed'` 的 scope run；如果 row 的 `source_versions`
不包含当前 matching source versions（例如 `workbench_matching_rules_version`），repository 使用
`for update skip locked` 把该 scope 原子转回 `dirty`，再由同一 worker 正常 claim、读取 canonical facts、
执行纯确定性规划，并把唯一安全结果通过 relation UoW 直接写成 active 正式关系后 complete。该 worker
不持久化候选/decision；ambiguous、unsafe 或 resource-limited 结果只记录计数，事实继续保持未配对。
不要手工改 `job.workbench_matching_dirty_scopes` 状态来补指定月份；生产恢复应走发布后的 worker、
read model refresh 和只读审计验证。

### 2026-07-14 正式关系二态迁移

该迁移必须拆成两个不可合并的生产发布。Release A 只发布 paired/unpaired 新运行时并移除全部旧
candidate/decision 运行时访问，不携带 Workbench 旧状态 drop migration，旧表在稳定窗口内仅作为应用回滚保护保留。
Release A 上线后执行 `workbench-rehydrate`：所有事实月份重建新的 Workbench generation，等待
`workbench` 与 `workbench_relation` scope fresh，再运行页面 Audit。只有 canonical counts/checksum、
active relation/history hash、520/未配对集合、queue/freshness/Audit 和旧表运行时零访问证据全部通过，
Release B 才可用届时下一个可用 migration version 发布旧状态 drop；不得复用已被 OA 使用的 0104，
也不得提前创建空 migration 预留版本。该 migration 只 forward-drop 旧 candidate/decision 派生表和旧 app-setting，不修改 OA、银行流水、发票、正式 relation 或 history；
Release B 后不允许回滚到读取旧表的应用版本。不能通过原地更新旧 generation、恢复旧表或隐藏不一致行完成迁移。

Workbench `all` active generation 从 month shard 聚合时必须传播单一且完整的
`workbench_matching_rules_version`。如果 all scope 缺失该版本证明，先通过正式 Workbench refresh 重建
month/all active generation，并检查 `workbench-matching` worker heartbeat 与 dirty scope 收敛。

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
release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"
cd "$release_src"
set -a
source /etc/fin-ops/fin-ops.worker.workbench.env
set +a
PYTHONPATH="$release_src/backend/src" \
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
后续 `job.outbox_events` read model 非 `done`、`job.read_model_dirty_scopes` 非 `done` 和
`read_model.app_status_readiness` 非 `fresh` 均收敛为 0。该验证只证明发布/重启不再依赖 300 秒
lock timeout；单个重型 read model rebuild 的执行时间仍需通过 worker 增量化、索引/分区和缓存阶段优化。

## RabbitMQ Real Consumer 运维

RabbitMQ 是 read model refresh 的 transport/wakeup，不是状态事实源。切换前后都必须以
PostgreSQL durable queue 和 readiness 为准：

- `job.outbox_events`
- `job.read_model_dirty_scopes`
- `read_model.app_status_readiness`

生产启用 required RabbitMQ real consumers 的顺序：

1. 发布包含 RabbitMQ preflight、systemd env hook 和 consumer clean interrupt 的 release。
2. 确认 RabbitMQ topology env 只加载给 bootstrap，不加载给 API 或 worker。
3. 执行 required-only preflight：

   ```bash
   release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"
cd "$release_src"
   set -a
   source /etc/fin-ops/fin-ops.api.env
   source /etc/fin-ops/fin-ops.rabbitmq-monitoring.env
   set +a
   PYTHONPATH="$release_src/backend/src" \
     /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.run_rabbitmq_staging_preflight \
       --json \
       --output /tmp/finops-rabbitmq-staging-preflight.json
   ```

   默认只检查 registry 中 `required=true` 且 `rabbitmq_eligible=true` 的 worker。只有本次明确启用
   optional worker 时才加 `--include-optional-workers`。

4. 如果 `/health/ready.runtime_infrastructure.rabbitmq_metric_error` 是 queue/DLQ missing，先使用
   `/etc/fin-ops/fin-ops.rabbitmq-topology.env` 执行 topology apply，再重新检查 Management metrics。
5. 创建或更新 root-only `/etc/fin-ops/fin-ops.rabbitmq-worker.env`，只写共享 `RABBITMQ_URL`
   和 `RABBITMQ_CONSUMER_POSTGRES_DRAIN_INTERVAL_SECONDS=0.05`。该文件权限必须是
   `0600 root root`，且不得设置 `FIN_OPS_QUEUE_BACKEND`。
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
- `job.read_model_dirty_scopes` 非 `done` 与 `read_model.app_status_readiness` 非 `fresh` 不持续增长。

如果 RabbitMQ DLQ 中 envelope 没有 PostgreSQL outbox 对应行，它是 transport orphan，不是 read model
事实 blocker。处理顺序是先导出审计摘要，再 purge 该 DLQ；禁止反向根据 broker-only envelope 写入
PostgreSQL done/fresh。

生产 Stage 9 已验证 required worker cutover：`main-99a98feb-stage9-202606130000` 切换后
`rabbitmq_consumer_count=15`、`rabbitmq_queue_depth=0`、`rabbitmq_dlq_count=0`、
`rabbitmq_metric_error=null`，同时 PostgreSQL queue/dirty/readiness 全部保持收敛。

回滚步骤：

1. 从切换前备份目录恢复 `/etc/fin-ops/fin-ops.worker.<instance>.env`，或把目标实例改回
   `FIN_OPS_QUEUE_BACKEND=postgres`。
2. 重启对应 worker unit。
3. 检查 `/health/ready.runtime_infrastructure` 的 required worker missing/stale/mismatch 为 0。
4. 检查 PostgreSQL durable queue 和 readiness 是否收敛。
5. RabbitMQ 残留消息只按 transport envelope 处理；不要把清空 RabbitMQ 当成 read model 修复。

## App Status Readiness Convergence

`read_model.app_status_readiness` 是全局状态 icon 允许变绿的 read model 证明层。上线该表或新增 read model 后，不能用批量 `insert fresh` 伪造状态；必须先用真实 read model 表、active generation、schema/source version 和 row count 做 convergence。

发布或迁移后的固定顺序：

1. 部署包含 `ReadModelReadinessReporter` 和 backfill tool 的版本。
2. 执行 dry-run：

   ```bash
   release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"
cd "$release_src"
   set -a
   source /etc/fin-ops/fin-ops.api.env
   set +a
   PYTHONPATH="$release_src/backend/src" \
     /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.app_status_readiness_backfill --dry-run
   ```

3. 如果 dry-run 输出 `schema_mismatch`、`source_mismatch`、`failed` 或 `missing`，先修复对应 projection/refresh/rebuild 原因；不要把这些状态改写成 `fresh`。
4. dry-run 判定合理后再 apply：

   ```bash
   PYTHONPATH="$release_src/backend/src" \
     /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.app_status_readiness_backfill --apply
   ```

5. 只读核对 `read_model.app_status_readiness`、`job.read_model_dirty_scopes`、`job.outbox_events`、`job.runtime_worker_heartbeats` 和 `/api/app-health.app_status`。如果还有 dirty scope、outbox backlog、worker stale/missing 或 dependency issue，global icon 仍应保持 yellow/red。

空业务结果可以是 `fresh`，但必须有真实生成事实；没有 readiness 记录的 read model 必须显示 `missing`，不能因为当前没有 dirty scope 而显示 ready。

### Cost Statistics Scope Readiness

`cost_statistics.read_model.refresh` 只由 `cost-statistics` worker 消费；`cost-tax` 兼容 worker 只保留 `tax_offset.read_model.refresh`。成本统计是跨银行流水、发票、OA 关系、项目归因和费用分类的派生 read model，因此 App Status 必须展示 scope 级 readiness，而不是只显示一个聚合后的 `cost_statistics=failed`。

高频 read model 的专用 consumers 是当前 P2/P3 一秒级 closure 的基础；历史 5s SLO 记录只是旧基线，不是当前验收上限。当前 direct refresh / 首屏 API 以 p95 <= 1000ms 为门禁，写操作链路还要求 operation-to-fresh p99 <= 3000ms：

- `workbench`：消费全部 `workbench.read_model.refresh`；月份 scope 发布 active generation，`all` 仅投递月份 shards，不发布全局 generation。
- `search` / `search-secondary` / `search-tertiary`：只消费 `search.read_model.refresh`，并发处理关系变更中的 bank 月、invoice 月以及快速 confirm/withdraw 连续写入产生的同 scope search 事件。
- `pending-invoice`：只消费 `pending_invoice.read_model.refresh`。
- `cost-statistics`：只消费 `cost_statistics.read_model.refresh`。
- `tax-offset`：只消费 `tax_offset.read_model.refresh`。
- `invoice-lifecycle-secondary`：作为第二条 `invoice_lifecycle.read_model.refresh` consumer，和 `invoice-lifecycle` 并发 drain 多月份 scope。

这些 worker 不改变 PostgreSQL durable queue / readiness 事实源；它们只是同一 outbox event type 的并发消费者或 scope-filtered lane。旧 `search-pending` 不应作为唯一性能 lane 依赖；`cost-tax` 不再消费 `cost_statistics.read_model.refresh`，避免旧成本统计链路与专用 lane 竞争长 SQL。

成本统计 scope 分为：

- 父 scope：`active:all`、`all:all`。
- 月份 shard：`active:YYYY-MM`、`all:YYYY-MM`。

处理规则：

- refresh `active:YYYY-MM` 或 `all:YYYY-MM` 时，worker 从对应工作台月份 read model 构建成本统计 shard。event 必须带非负整数 `source_version`；repository 复用现有 partial unique index，只有在单事务内锁定的唯一 `pending` / `processing` dirty row 版本精确相等时才发布，handler 再以同一版本条件完成。只有发布与完成均成功才重新入队同 project scope 的父 scope；任一竞态失败都保持 `refreshing`，不写 Redis、不完成新 dirty、不 fan-out。
- refresh `active:all` 或 `all:all` 时，worker 先检查对应月份 shard readiness。缺失、stale 或 failed 的 shard 通过 `ReadModelRefreshGateway` 入队，父 scope 记录 `refreshing`，不完成 dirty scope，不伪造 `fresh`。
- 所有所需月份 shard fresh 后，worker 从 `read_model.cost_statistics_rows` 与 `read_model.cost_statistics_bank_flow_rows` 的月份 rows 聚合生成父 scope；parent metadata 不保存 `time_rows` / `bank_flow_time_rows`。parent snapshot 与过期月份 scope 的 metadata/两类 rows 删除必须在同一次 source-version 条件事务中发布，之后才用同一版本完成父 dirty scope。两张行表都只承载月份 shard 明细，不承载 `active:all` / `all:all` parent rows；禁止回读 child JSON arrays。
- 成本 projection 发布成功或拒绝时都不得写/删 Redis；旧 `cost_statistics:explorer:{scope}` 无版本 writer 已删除。Redis 仅由 API query owner 在 PostgreSQL fresh gate 后写 versioned cache，不属于 worker/readiness 事实链路。
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

运维侧 heartbeat 可能看到 `deferred`：表示 worker 已识别依赖 read model 尚未 fresh，并将事件短延迟回
`pending`。用户侧仍应表现为 `refreshing`，不能把 deferred 解释为已同步。

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
PYTHONPATH="$release_src/backend/src" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops inspect --event-id <uuid>

PYTHONPATH="$release_src/backend/src" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops requeue \
    --event-id <uuid> \
    --reason operator_repair
```

RabbitMQ worker 下如果 PostgreSQL `processing` event 已超过 lock timeout 且没有对应 envelope 被消费，先处理已被更新同
dedupe event 覆盖的旧 `processing`，再释放仍需真实重跑的 stale `processing`。两步都必须先 dry-run；
superseded resolution 只清理旧重复事件，release 只会重新 publish/处理，不会伪造 readiness：

```bash
PYTHONPATH="$release_src/backend/src" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops resolve-superseded-processing \
    --dry-run \
    --stale-after-seconds 300 \
    --event-type bank_detail.read_model.refresh \
    --limit 100 \
    --reason rabbitmq_stale_processing_superseded

PYTHONPATH="$release_src/backend/src" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops resolve-superseded-processing \
    --execute \
    --stale-after-seconds 300 \
    --event-type bank_detail.read_model.refresh \
    --limit 100 \
    --reason rabbitmq_stale_processing_superseded
```

随后释放仍需重跑的 stale processing：

```bash
PYTHONPATH="$release_src/backend/src" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops release-stale-processing \
    --dry-run \
    --stale-after-seconds 300 \
    --event-type bank_detail.read_model.refresh \
    --limit 100 \
    --reason rabbitmq_stale_processing_repair

PYTHONPATH="$release_src/backend/src" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops release-stale-processing \
    --execute \
    --stale-after-seconds 300 \
    --event-type bank_detail.read_model.refresh \
    --limit 100 \
    --reason rabbitmq_stale_processing_repair
```

如果 dead-letter 来自历史 invalid-scope cost statistics 事件，优先使用 `scripts/check-read-model-scope-contracts.py`
检查和清理同类 legacy/invalid scope，避免逐个重放必然再次失败的旧事件。对于其他 read model，且当前版本
已经通过真实 readiness convergence 证明同一 scope 已被覆盖，可以使用受控 resolve：

```bash
PYTHONPATH="$release_src/backend/src" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops resolve-dead-letter \
    --event-id <uuid> \
    --reason readiness_converged_obsolete_invalid_scope
```

批量归档前必须先 dry-run：

```bash
PYTHONPATH="$release_src/backend/src" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters \
    --dry-run \
    --limit 100 \
    --reason readiness_converged_obsolete_dead_letter
```

dry-run 中 `eligible_count` 必须等于准备归档的候选数，且每条 event 的 `proof.covered_by` 至少包含
`fresh_readiness` 或 `later_done`。确认后才能执行：

```bash
PYTHONPATH="$release_src/backend/src" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.runtime_queue_ops resolve-covered-dead-letters \
    --execute \
    --limit 100 \
    --reason readiness_converged_obsolete_dead_letter
```

`resolve-dead-letter` 和 `resolve-covered-dead-letters` 只适用于注册的 read model refresh event。命令会先检查：

- 事件当前必须仍是 `dead_lettered`。
- 同一 `tenant_id + read_model_key + scope_type + scope_key` 在 `read_model.app_status_readiness` 中已经有 `fresh` 证明，或同一 outbox scope 在该 dead-letter 后已有 `done` 事件。
- 同一 `tenant_id + scope_type + scope_key` 没有 `pending`、`processing` 或 `failed` dirty scope。

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

2026-06-29 起，`read_model.workbench_relation_rows` 使用 `(tenant_id, scope_key, row_id)` 作为 scope 内唯一键。发布包含该迁移后，必须重建目标
`workbench_relation` month shards，让跨月 relation 的每个成员 row 索引补齐到受影响 scope；不能只依赖迁移本身修复旧读模型行。

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

## Ensure refresh 与真实写入 dirty 的边界

`dependency_not_fresh`、`api_*`、`pending_invoice_sql_projection`、`bank_detail_relation_tags_read`、
`workbench_relation_write_precondition`、`downstream_bank_tag_read` 属于 ensure/wakeup 类刷新请求。成本统计读取
`bank_detail` source versions、transaction tags 或 month rows 时必须统一复用 `downstream_bank_tag_read`，不能另造绕过
active coalescing 的 reason。它们只能确保目标
read model 有 refresh 在跑；当同一 `tenant_id + scope_type + scope_key` 已经 `pending` 或 `processing` 时，
`ReadModelRefreshGateway` 必须 coalesce，不应 bump `source_version`，否则 downstream projection 会追逐移动目标。
上述 coalesce 仅适用于普通 ensure/wakeup；显式 `force_refresh=true` 必须保留独立 durable event 语义。

真实写入原因，例如 `workbench_relation_changed`、`confirm_link`、`withdraw_link`、导入/设置/标签变更，仍然必须写
durable dirty scope 并在 active scope 上提高 `source_version`。这是防止旧 worker 把新事实误发布为 fresh 的一致性边界。
