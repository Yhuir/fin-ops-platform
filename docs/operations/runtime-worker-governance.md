# Worker + Read Model 统一治理

本页描述生产和开发环境如何统一管理 `fin-ops-platform` runtime worker 与 SQL read model。
治理闭环不引入 Celery/RQ/Redis Queue 等新任务框架：PostgreSQL durable queue 是任务和
read model 刷新状态事实源，systemd 管 worker 进程，App 只负责写入任务、记录 heartbeat、
暴露健康状态和给出运维提示。

本文同时维护 read model production audit、SQL-native hardening、App Health 性能和 worker 运维治理的长期结论。
阶段报告和一次性执行记录不再单独保留。

## 可逆关系 checkpoint 证据边界

- mutation 仍只走 Workbench action API → relation command → UoW；runner 不写 relation、outbox、dirty、readiness 或 read model。
- mutation 与 worker 证据通过 durable idempotency committed record 的精确 event ID 集关联；`started_at` 只是下界，不能让同 profile 并发事件串入。合法 optional scope 可记录为 skipped/pass，未知 scope 或未匹配 event ID fail closed。
- bank+invoice、bank+turnover closure、bank+OA+invoice 的可执行 profile pair、mutation contract 与 affected/non-consumer 页面由部署包内 `write_operation_e2e_smoke.REVERSIBLE_RELATION_*_CONTRACTS` 负责；`docs/dev/write-operation-impact-matrix.json` 是测试机械约束的运维/架构镜像。普通 relation mutation receipt 不再包含页面 read-model target，且提交事务不得新增 relation-origin dirty/outbox。已迁移页面通过自己的 API 直接读取 canonical facts 与 active relations，不补投页面 refresh；保留的共享 read model 只按 manifest 中的显式 owner 合同独立收敛。bank+turnover 只走正式 turnover closure confirm/withdraw。
- discovery 不再把普通生产 turnover/Workbench/no-OA 事实转换成可执行 relation mutation；只保留 read-only context。现有 bank-flow submit 仍由自己的正式 owner 生成场景。

## Hardening 基线

- 普通用户写入默认只提交 canonical facts/source version/audit/idempotency 与必要领域任务，返回信息性 affected scopes；不得直接产生页面 read-model dirty/outbox，也不得返回页面 operation-barrier targets。
- 直接读取页面的 route mount、focus 或 hidden→visible 只执行 normal canonical GET，不比较 read-model version，也不 enqueue。关联台 `workbench` 与三个共享 read model 通过各自 query owner 比较 expected/actual versions；精确 scope non-fresh 时才经 `ReadModelRefreshGateway` 入队。
- `workbench_relation` 的 expected proof 必须覆盖 exact scope 的 active relation count 与稳定 typed membership digest；局部 relation delta 必须先批量解析 canonical UUID/legacy aliases。只比较 `max(updated_at)` 或复用旧 scope proof 会漏掉旧关系撤回，禁止作为 fresh 证明。
- `all` / full-history 只允许显式 authoritative integration、data reset、repair/backfill/reapply 或人工 maintenance 使用；必须在 App Health 标记为 `full_history_batch`，不能伪装成普通 current-scope 工作。
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
  `deploy/oa/bin/finops-deploy-control.sh`，再执行完整 helper contract、`check-release` 和
  `release-gate-activate`，
  避免新增 versioned timer/helper 时被旧远端 deploy-control 卡住。首次接入或旧 helper 不支持
  `self-update` 时仍需要一次 root bootstrap。`/usr/local/sbin/finops-ensure-runtime-workers`
  仍是预安装的 root helper；release deploy 只校验该 helper 的合同并通过
  `finops-deploy-control release-gate-activate` 的内部受控激活阶段间接调用它，不在发布链路中覆盖该
  runtime worker helper。
- 当前 release 的 worker registry 同时是生产实例白名单。发布门禁在切换前后枚举全部已加载和已安装
  `fin-ops-worker@*.service`，对已启用、运行或失败但不在 registry 中的实例执行 stop/disable；不删除实例 env，
  因而可通过恢复含该 registration 的 release 受控回滚。禁止把 WIP 性能 worker 或手工 systemd 实例留在
  registry 外长期运行，也禁止通过给未知实例补空参数来绕过 registration contract。
- PostgreSQL durable queue worker 的 idle poll 基线是 `0.05s`。read-model worker 只允许
  `workbench-relation`、`search`、`search-secondary`、`search-tertiary` 和 `no-oa-bank-batch`；
  registry 未登记的页面 projection worker 必须由 release helper stop/disable。`workbench-matching` 是独立领域
  批处理，不是 read model，使用 `0.25s` poll 支撑 relation enrichment 的 3 秒写后可读 SLO。
- OA 待付款、进项使用和销项收款页面没有 read-model worker。OA 页面写回外部系统成功后，API 进程通过窄
  PostgreSQL canonical writer 更新状态与 watermark；失败返回可重试错误。运维不得恢复页面 refresh event、
  手工补 projection 或把外部系统当前值伪装成已提交 PostgreSQL 事实。
- 周期性 `oa.sync` 必须是 change-driven canonical commit：相同 completed OA、status、admission snapshot 不更新业务时间戳；真实变化也只提交 canonical facts/source watermark。snapshot repository 与 sync service 不得 fan-out 页面 refresh。直接读取页面在下一次 GET 自然看到已提交事实；Search 等保留 read model 只由自身 query owner 按 source mismatch 收敛精确 scope。若 sync 后持续出现跨页面 dirty/outbox 或无变化时 `app.oa_applications.updated_at` 漂移，按同步 owner 回归处理，禁止通过扩大 worker 数量掩盖写放大。
- PostgreSQL durable queue worker 的空轮询 heartbeat 必须节流。`idle` 只证明 worker 存活和当前无可 claim event，
  不能每个 0.05s poll 都写 `job.runtime_worker_heartbeats`；`processing`、`deferred`、`failed`、`stopping`、`stopped`
  必须即时写入，保证 App Health 和故障定位不丢关键状态。
- 同一 event type 确有当前吞吐隔离需求时，只允许使用 worker registry / worker env 暴露的 claim scope include/exclude。
  当前只有 Search 使用 primary/secondary/tertiary lane；scope policy 仍是 read model contract 的事实源，
  queue 层只做 claim，不承载业务 scope 校验。
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

## 独立受控业务写 smoke 输入（不属于自动 Release Gate）

显式 operator write-operation E2E smoke 使用标准 scenario 和 approval ticket。标准 scenario 是运维维护的
`test_owned`、bounded、可逆关系测试对象；只读
`fin_ops_platform.tools.write_operation_scenario_discovery` 只提供候选审核上下文，不能把普通生产业务关系
写成可执行输入：

- `FIN_OPS_WRITE_E2E_SCENARIO=/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json`
- `FIN_OPS_WRITE_E2E_APPROVAL_TICKET=FINOPS-WRITE-SMOKE-STANDING-20260702`
- 每个 operation 最多写入 1 个受控 scenario，避免同一月份连续撤回造成 Workbench/read model 串行刷新长尾。
- scenario 必须使用登记的可逆 relation shape，包含 checkpoints 与 inverse/recovery，并证明最终关系 inactive；旧式 discovery 输出、真实待处理业务对象或缺少 recovery 的 scenario 必须 fail closed。
- `runtime_sync_closure_gate` 不读取该合同，也不执行 mutation；自动 release gate 只运行隔离
  PostgreSQL 可逆写探针和只读 canonical audit。
- gate 失败证据必须保留 RabbitMQ 总量和逐事件队列的 `messages`、`unacked`、`consumers`、DLQ 明细，禁止只记录总积压后依赖 root 权限二次排查。
- runner 每次执行为所有 mutation 生成独立 idempotency key；静态 root-owned scenario 不保存可跨 checkpoint 复用的 mutation key。
- discovery 只读 PostgreSQL 事实并输出审核上下文；真正 apply 仍必须提供真实 OA/Admin auth，但不再需要临时业务 ticket。
- 标准文件禁止通过 shell 重定向或普通复制直接覆盖。候选文件必须先保存为
  `/tmp/finops-write-e2e-<run-id>.json`，再由
  `finops-deploy-control write-operation-e2e-scenario-install <release-name> <temporary-scenario-path>`
  使用候选 release 的严格校验器验证并原子安装；helper 拒绝链接、不安全权限、非 finops-deploy
  所有者、超限文件和不完整 scenario，并保留 root-owned `.previous` 作为恢复点。
- Workbench relation 的 test-owned checkpoint 必须显式执行三步 I/O：先按目标月份读取
  `/api/workbench?month=...` 并捕获 `read_model_version`，再让 preview 与 mutation 同时携带该精确版本；
  confirm 后的 withdraw 必须重新读取版本，禁止复用上一个 generation、隐藏重试或省略写前置条件。
- 成本统计 consumer 只使用当前 explorer 合同：query 为 `scope/view/project_scope/page_size`，业务行根为
  `rows`。旧 `month` query 与 `time_rows` / `bank_flow_time_rows` / `project_rows` /
  `expense_type_rows` response root 已退出生产合同，不得继续用于 write smoke 或作为兼容 fallback。
- 可逆关系 consumer assertion 只接受 typed `equals`、`contains` 与 `excludes`。`excludes` 递归检查指定
  业务根中不再包含明确的 test-owned row/case identity，用于撤回后目标行按正式页面规则退出列表的场景；
  它仍必须绑定 scenario 的 fixture row 或已捕获 case，不能用空数组或宽泛状态断言绕过 identity gate。
- `finops-deploy-control write-operation-e2e-smoke ... --apply-stdin [preview-samples]` 从 stdin 第一行读取
  Admin Token、第二行读取 standing approval ticket；任一为空都在业务 mutation 前失败，避免把 root-owned env
  漂移误判为已授权。可选 preview sample count 只接受 `1..20`，默认 1；它只重复 canonical relation preview，
  不增加正式 mutation 次数。scenario 可直接使用固定 root-owned `0600`
  `/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json`；其它输入仍只接受
  `finops-deploy` 持有且不可 group/world write 的 `/tmp/finops-write-e2e-*.json`。
- 明确 test-owned、幂等且 runner 自动执行 inverse/recovery 的 relation smoke 不要求每次创建全库备份；其安全
  边界是独立 idempotency key、exact receipt、失败 recovery、最终 inactive 状态和 System Audit。只有场景无法靠
  业务 inverse 完整恢复、或审批明确要求灾难恢复点时，才使用 `write-operation-restore-point`。已创建恢复点只能
  通过 `write-operation-restore-point-delete <run-id> <expected-sha256>` 精确校验固定文件集、manifest 和 dump
  checksum 后删除；禁止宽泛路径删除。
- 同步写超过门禁仍判定为 SLO failure；如果 HTTP 结果已经证明 mutation committed，runner 必须先证明
  `outbox_event_ids` 为空且没有出现登记的旧 fan-out signature，再读取目标消费页并执行撤回。隔离/causal 写前基线遇到
  `202 refreshing`、`read_model_not_fresh` 或 dependency `503` 时，必须在同一个有界 timeout 内轮询到 fresh；
  这些瞬态状态不能据此跳过撤回或把生产关系留在 active 状态。
- 首批 receipt 完成后，consumer gate 对 `202` / `read_model_not_fresh` / dependency `503` 在总 timeout
  内继续轮询，因为这些状态属于合法的 access-time convergence；业务字段断言失败和单次 fresh 响应超过页面 SLO
  不可重试，仍立即失败，防止 eventual consistency 轮询掩盖错误内容或性能退化。
- 同一 checkpoint 声明的多个 consumer 代表同时打开或同时恢复可见的页面，runner 每轮必须有界并发探测，
  并按 scenario 顺序输出结果；禁止串行 HTTP 探测把前一个页面的请求/重建时间累计到后一个页面。失败结果必须保留
  已解析的 `path`，使首次不可重试 SLO failure 与后续 fresh 结果使用同一 identity，不能出现报告总状态 fail、
  展示行却全部 pass 的证据漂移。
- no-OA withdraw 候选必须同时满足 `app.no_oa_bank_batches.status='submitted'`、`relation.status='active'`
  和 `relation.relation_mode='no_oa_bank_batch'`，不能把 bank-flow rule batch 关系误送到 no-OA endpoint。

| 页面 | apply policy | 生产 smoke operation | approval ticket |
| --- | --- | --- | --- |
| `turnover-ledger` | standing apply | `turnover_manual_closure_or_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `reconciliation-workbench` | standing apply | `workbench_relation_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `workbench-relations` | standing apply | `workbench_relation_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `no-oa-bank-batches` | standing apply | `no_oa_bank_batch_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `bank-flow-rule-batches` | access convergence evidence | `no_oa_bank_batch_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `bank-details` | access convergence evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `bank-account-balance` | access convergence evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `pending-invoices` | access convergence evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `input-invoice-usage` | access convergence evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `output-invoice-collections` | access convergence evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `invoice-lifecycle` | access convergence evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `oa-pending-payments` | access convergence evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `tax-offset` | access convergence evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `cost-statistics` | access convergence evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `search` | access convergence evidence | turnover / Workbench / no-OA withdraw | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
| `batch-accounting` | access convergence evidence | `workbench_relation_withdraw` | `FINOPS-WRITE-SMOKE-STANDING-20260702` |
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
  --scope tax_offset=all --dry-run
```

该入口只通过 scope policy、`ReadModelRefreshGateway` 和 durable queue，不直接更新 `read_model.*`、
`app_status_readiness` 或 dirty scope 状态。已由 exact-scope fresh/done 覆盖的 dead letter 只能通过
`runtime-queue-resolve-covered` dry-run 后执行归档；未覆盖 failure 继续阻断 Audit。
外部往来已在 2026-07-26 迁为 direct canonical read，不再接受 `turnover_ledger` refresh scope，也没有对应
worker、dirty scope 或 outbox event。

当 canonical source versions 未变化、但已证明旧 projection 算法留下错误数据时，受控重建可显式增加
`--force-refresh`。该标志只把 `force_refresh=true` 写入通过 scope policy 校验后的 durable event metadata，
由已登记 projection handler 重算目标 scope；它不直接写 read model、不修改 readiness，也不能替代重建后
的 queue drain、freshness 和只读 Audit 复验。执行前必须先 dry-run 同一组 scopes，且只选择已证明受影响的 scope。
`force_refresh=true` 的 durable request 不得与已有普通 pending/processing refresh coalesce；`all` fan-out 时该 metadata
必须继续传递给每个实际 shard，避免受控重建被静默降级成普通 unchanged-scope refresh。

如果 downstream refresh handler 抛出 `*_read_model_not_fresh` / `read_model_not_fresh`，runtime worker
会调用 `RuntimeQueueRepository.defer_event(...)`，把该 outbox event 短延迟放回 `pending`，生产模板默认 0.25 秒后
重新 claim。这只用于依赖顺序竞态，不写 fresh readiness、不缓存 payload，也不进入 failed/dead-letter。
dependency refresh 只有在 source manifest entry 的 `read_dependencies` 显式登记目标时才允许补投；当前四个保留
read model 均未声明跨模型依赖。manifest 外 event 和已退休页面 scope 不得因为旧错误文本重新进入 runtime queue。
成本统计等 direct-canonical 页面没有 downstream projection 或 dependency enqueue；请求由 canonical repository
在单个 `REPEATABLE READ READ ONLY` snapshot 中完成读取，失败直接返回错误供客户端重试。

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

发布 migration `0126` 前后若发现遗留 Cost scope，先运行只读检查：

```bash
sudo -n /usr/local/sbin/finops-deploy-control read-model-scope-contract <release-name> --json
```

脚本会检查 `job.read_model_dirty_scopes`、`job.outbox_events` 与 `read_model.app_status_readiness`
中已不符合当前 registry 的 legacy `cost_statistics` scope，同时扫描未完成或 publish 异常的
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

### 关联台 Workbench generation runtime

关联台页面继续读取 `read_model.workbench_*` active generations；批量账务保持 direct canonical read，
不得借用关联台 projection。`workbench` generation worker、repository、rehydrate CLI、prune helper、
systemd service/timer 与部署安装逻辑均为当前运行时合同。生产可以投递
`workbench.read_model.refresh`，但必须经 scope gateway/durable queue；generation retention 只能删除
非 active 且超过保留窗口的版本。

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

matching source versions 只允许包含会改变正式关系计算结果的输入。`workbench_read_model_schema_version`
属于 Workbench 展示投影边界，不能触发 matching stale scan。若已失败 scope 经确认是无关投影升级触发，
先发布完成该依赖解耦和专用 worker statement-timeout 修复，再使用受控命令精确恢复：

```bash
sudo /usr/local/sbin/finops-deploy-control workbench-matching-retry <release-name> \
  --scope-month YYYY-MM --dry-run
sudo /usr/local/sbin/finops-deploy-control workbench-matching-retry <release-name> \
  --scope-month YYYY-MM --execute --expected-fingerprint <dry-run-fingerprint>
```

该命令只接受 `failed` 状态、单个合法月份和未漂移 fingerprint，并通过既有 matching durable repository
把 exact scope 置回 dirty；实际 claim、relation UoW、complete/fail 仍由注册的 `workbench-matching`
worker 负责。不得用它重排 completed/processing scope，也不得直接 SQL 修改 attempt/status。

### 2026-07-14 正式关系二态迁移（历史记录）

该迁移必须拆成两个不可合并的生产发布。Release A 只发布 paired/unpaired 新运行时并移除全部旧
candidate/decision 运行时访问，不携带 Workbench 旧状态 drop migration，旧表在稳定窗口内仅作为应用回滚保护保留。
Release A 上线后曾执行 Workbench generation rehydrate：所有事实月份重建新的 Workbench generation，等待
`workbench` 与 `workbench_relation` scope fresh，再运行页面 Audit。只有 canonical counts/checksum、
active relation/history hash、520/未配对集合、queue/freshness/Audit 和旧表运行时零访问证据全部通过，
Release B 才可用届时下一个可用 migration version 发布旧状态 drop；不得复用已被 OA 使用的 0104，
也不得提前创建空 migration 预留版本。该 migration 只 forward-drop 旧 candidate/decision 派生表和旧 app-setting，不修改 OA、银行流水、发票、正式 relation 或 history；
Release B 后不允许回滚到读取旧表的应用版本。不能通过原地更新旧 generation、恢复旧表或隐藏不一致行完成迁移。
现行 deploy-control 保留 `workbench-rehydrate`，只用于冷启动、回滚恢复或明确批准的受控重建；
正常页面访问必须通过 freshness gate 精确 enqueue，不得把全量 rehydrate 当作请求 fallback。

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

公开 `activate` 命令已删除。`finops-deploy-control release-gate-activate <release>` 是唯一正常激活入口，
其内部受控激活阶段的 worker 顺序是：

1. 执行 PostgreSQL migration。
2. 写入 API、worker、dispatcher release drop-in。
3. 调用 `/usr/local/sbin/finops-ensure-runtime-workers <release-src>`。
4. 重启 API、worker、dispatcher。
5. 等待 `/health` worker readiness 收敛。
6. 输出状态。

入口先对当前 release 执行 production-equivalent `preflight` checkpoint；候选激活后在 T+0 执行
`full` checkpoint，并分别在 T+60s、T+300s 执行 `stability` checkpoint。所有 profile 都使用
`pg_temp` 临时表完成隔离 insert/read/delete/rollback 探针，并在 runtime 收敛后执行只读页面 canonical
audit；任何 profile 都不得 confirm、withdraw、recovery 或修改真实业务关系。每次检查都必须使用真实 PostgreSQL 和 RabbitMQ，
验证 exact registry/systemd inventory、worker readiness、dirty scope、pending/processing outbox、durable 与
RabbitMQ dead letter、critical read-model enqueue-to-fresh SLO、domain audit 和 API/health/SSE 性能。
最终 evidence 复用只读页面 canonical audit，并以 T+300 runtime 采样证明 queue 持续稳定。
RabbitMQ management 未配置或读取失败时 fail closed。checkpoint 必须按实际
systemd I/O 边界分别加载 `/etc/fin-ops/fin-ops.rabbitmq-topology.env`（topology apply）和
`/etc/fin-ops/fin-ops.rabbitmq-monitoring.env`（runtime health/closure）；文件缺失或不可读不得退回
common env、worker env 或跳过 RabbitMQ。自动门禁不读取业务 write scenario 或 standing approval。

最终证据写入
`/opt/fin-ops/runtime-smoke/release-gates/<release>/evidence.json`，权限为 root `0600`，并绑定
release 与 Git commit。PRE 失败时，部署命令只返回不含 token、环境变量值和业务样本的组件状态与
队列计数摘要，供运维修复真实阻塞项；不得据此绕过门禁。PASS 必须满足：

- `unknown_worker_count = 0`
- `required_worker_not_ready = 0`
- `dirty_scope_count = 0`
- `pending_outbox_count = 0`
- `publishing_outbox_count = 0`
- `dead_letter_delta = 0`
- `page_canonical_audit_status = pass`
- `terminal_publish_reconciliation_stable = true`
- `queue_stable_after_300_seconds = true`

任一 checkpoint、最终证据写入或证据合同校验失败，都必须自动恢复 previous release，并在回滚后执行
`preflight` checkpoint；pre checkpoint 失败时还必须恢复 previous release 的 deploy-control/runtime-worker helper。
pre 与 rollback checkpoint 使用候选 release 的门禁代码检查实际运行 release；worker inventory 仍按实际
运行 release 的 registry 核对。这样首次启用新门禁时不依赖旧 release 中尚不存在的检查逻辑。
页面 audit 则以候选 release 的 `PAGE_AUDIT_REGISTRY` 为预期集合，严格核对当前 runtime 返回的 summary
和逐页 proof。旧 runtime 尚未返回 registry 明细字段时，只有逐页 proof、页数和顺序全部与候选 registry
一致才可通过；三个 registry 字段部分缺失、漏页或额外页面均 fail closed。
不存在“候选已激活但没有有效 gate evidence”的成功状态。

RabbitMQ dispatcher 每次领取待发布事件前，会把业务消费已经完成的
`status=done/publish_status=publishing` 行立即收敛为 `published`，不再等待 publish lock timeout。
`status=done` 是消息已经到达 consumer 并完成处理的 durable 终态证据，继续等待或重复发布都没有意义；
稍后到达的 dispatcher publish confirm 对该终态幂等成功。release gate 同时要求
`publishing_outbox_count=0`，防止终态事件卡在 transport 中间态。
只有 closure gate 内部可以调用同一 repository 方法幂等收敛已经 `done` 的终态；部署 shell 不得在 gate
前后隐式修复。任何 reconciliation 都必须写入 checkpoint evidence，随后至少再取得一个
`publishing_outbox_count=0` 且本轮没有再次 reconciliation 的干净采样才可 PASS。若采样期间重复出现，
视为 dispatcher/状态机持续故障并 fail closed；T+60/T+300 还会再次验证没有复发。该步骤不认领、重放或
重新发布事件，也不绕过 `unpublished/publishing/publish_failed = 0` 强门禁。

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

正式生产切换只走受控入口：

```bash
sudo /usr/local/sbin/finops-deploy-control \
  rabbitmq-required-worker-cutover <release-name>
```

该命令直接从 worker registry 推导精确 required eligible 实例与 dispatcher event types，不维护第二份
清单；验证共享与实例环境文件为 root-owned、非符号链接且不可被 group/world 写入；备份所有目标
instance env；原子写入 `FIN_OPS_QUEUE_BACKEND=rabbitmq`；重启精确目标 worker；等待 worker ready、
每个目标 queue 均有 consumer、depth/unacked 自然清空且 DLQ 为 0。任何步骤失败都会恢复备份并重启
原 worker。禁止 purge 队列、跳过 consumer 检查或削弱 release gate；PostgreSQL durable queue 始终保留。
production-equivalent release gate 对缺失 queue metrics 或 consumer 为 0 的 dispatcher event 一律阻断。

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

### Cost Statistics direct canonical read

成本统计没有 runtime worker、read-model manifest、scope、readiness 或 refresh event。页面/API 请求直接在一个 PostgreSQL `REPEATABLE READ READ ONLY` snapshot 中读取 canonical facts；标签规则保存后由下一次 GET 应用。

发布 migration `0126_cost_statistics_direct_canonical_read.sql` 后，遗留 `cost_statistics.read_model.refresh`、dirty/readiness 行被终止/删除，旧 Cost read-model 表被删除。运维不得再 enqueue Cost scope、启动 Cost worker、手工伪造 Cost readiness 或恢复旧 parent/shard repair。生产验证应检查 Cost API/Audit 正确性、请求耗时以及 Cost queue I/O 为零。

### Direct canonical page runtime retirement

`0127_direct_canonical_page_runtime_retirement.sql` 是纯 no-op 退休标记：不终止或删除历史 outbox/dirty/readiness，也不 DROP 旧表，因此上一 release 回滚时仍保有完整 backlog、状态和 projection 证据。`finops-deploy-control release-gate-activate` 的内部受控激活阶段必须先停止/disable 新 registry 未登记的退休页面 instance，再查询 PostgreSQL，确认非当前 manifest 的 read-model outbox 与 dirty scope 均无 `processing`；门禁通过后才停止其余上一版本 worker、运行 migration 并激活。门禁失败时不得运行 migration 或激活新版本，且已登记的 import/matching/保留 read-model worker 继续运行，避免生产 runtime 被留在全停状态。新版本的 registry、RabbitMQ dispatcher 和 App Status 不 claim/展示退休历史。`workbench`、Search、`workbench_relation`、no-OA 与 Workbench matching 继续保留；ETC 仍只使用 import worker，没有自己的页面 read model。

Bank-flow 未提交候选由页面 API 请求内实时推导，没有 canonical draft event、queue、worker、env 或 replay。`app.bank_flow_rule_batches/events` 只保存 submitted、withdrawn、stale 等正式业务状态和审计历史；运维不得投递 draft refresh、启动 bank-flow worker、手工写 draft 或恢复旧 `bank_flow_rule_batch.read_model.refresh`。

发布验证必须确认 runtime registry、systemd env、outbox 与 backfill CLI 均不存在 bank-flow draft handler/event；旧数据库 draft 行不参与新列表、提交或 Audit expected set。物理清理遗留 draft 数据必须另立 dry-run、幂等、仅命中明确 draft/unsubmitted 状态的受控 migration，禁止删除正式历史。
