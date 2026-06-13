# Runtime 同步 Stage 3 - Dispatcher 调度与必需 worker 收敛

本阶段目标是修复 Stage 2 暴露的两个非业务瓶颈：

- RabbitMQ dispatcher idle poll 仍为 5 秒，单个 outbox event 在投递前就可能消耗完整同步预算。
- `bank_account_balance` 属于 `/bank-details` 页面事实源，但生产缺少常驻 worker，且此前未纳入 App Status critical/required 闭环。

本阶段没有引入 Kafka、PgBouncer、分区、DDL 或 SQL rewrite。

## 本地变更

- 提交：`d465468f Tighten runtime sync worker scheduling`。
- `RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS` 默认设为 `0.5`，systemd example 和 deploy-control drop-in 都通过 env 控制
  `--poll-interval-seconds`。
- `bank-account-balance` 在 `runtime_worker_registry` 中改为 `required=true`。
- `bank_account_balance` 在 App Status read model registry 中改为默认 critical。
- `fin-ops.worker.bank-account-balance.env.example` 从 optional 语义改为银行明细页面 required worker，PostgreSQL polling 默认
  poll 从 5 秒降到 2 秒；生产本次使用 RabbitMQ env example。

本地验证：

```bash
PYTHONPATH=backend/src python3 -m pytest \
  tests/test_read_model_slo_smoke.py \
  tests/test_runtime_worker_registry.py \
  tests/test_runtime_monitoring.py \
  tests/test_rabbitmq_staging_preflight.py \
  tests/test_deploy_runtime_examples.py \
  tests/test_read_model_refresh_gateway.py \
  tests/test_runtime_queue.py \
  tests/test_rabbitmq_runtime.py -q

bash scripts/verify.sh docs
git diff --check
bash -n deploy/oa/bin/finops-deploy-control.sh deploy/oa/bin/finops-ensure-runtime-workers.sh
```

结果：84 passed，docs/shell/diff check 通过。

## 生产发布

- release：`main-d465468f-stage3-sync-202606131230`。
- 上传方式：`scripts/deploy-oa.sh --skip-build --no-activate`，release check 通过。
- 激活方式：`/usr/local/sbin/finops-deploy-control activate main-d465468f-stage3-sync-202606131230`。
- migration：`0001` 到 `0070` 均为 skipped 或 accepted checksum drift，没有新增 DDL。

激活前只读检查确认：

- `fin-ops-rabbitmq-dispatcher.service` 仍使用 `--poll-interval-seconds 5`。
- `/etc/fin-ops/fin-ops.worker.bank-account-balance.env` 不存在。
- 其它 read model worker 已使用 RabbitMQ worker env；`bank-account-balance` 若用 PostgreSQL env 启动，会让
  RabbitMQ 对应 queue 缺 consumer。

因此在激活前先安装 RabbitMQ 版 worker env：

```text
/etc/fin-ops/fin-ops.worker.bank-account-balance.env
```

内容来自 release 中的：

```text
deploy/oa/env/fin-ops.worker.bank-account-balance-rabbitmq.env.example
```

首次激活后，`bank-account-balance` worker 已被创建并启动，但生产 root-owned `finops-deploy-control` 仍是旧 helper，
dispatcher drop-in 仍写出 `--poll-interval-seconds 5`。随后把 release 内 helper 安装到：

```text
/usr/local/sbin/finops-deploy-control
```

并重新 activate 同一 release。复核实际进程：

| 项 | 结果 |
| --- | --- |
| dispatcher WorkingDirectory | `/opt/fin-ops/releases/main-d465468f-stage3-sync-202606131230/src` |
| dispatcher env | `RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS=0.5` |
| dispatcher process args | `--poll-interval-seconds 0.5` |
| bank-account-balance worker | active |
| bank-account-balance queue backend | RabbitMQ |
| bank-account-balance process args | `--enable-bank-account-balance-read-model-refresh --event-type bank_account_balance.read_model.refresh --max-events-per-iteration 4` |

## 生产健康状态

激活后 `/health/ready`：

| 指标 | 结果 |
| --- | ---: |
| status | `ready` |
| missing/stale/mismatched required worker | 0 / 0 / 0 |
| active outbox backlog | `{}` |
| dirty scopes | `done` only |
| RabbitMQ queue depth/unacked/DLQ | 0 / 0 / 0 |
| RabbitMQ consumer count | 16 |
| RabbitMQ dispatcher lag | `null` |

`bank-account-balance` worker 启用后，consumer count 从 15 增到 16。

## Read model smoke

生产输出目录：

```text
/tmp/finops-stage3-20260613114342
```

dry-run：

```text
/tmp/finops-stage3-20260613114342/read-model-slo-smoke-dry-run.json
```

- `planned_scope_count=14`
- `missing_read_model_keys=[]`
- 包含 `bank_account_balance/all`

连续三轮 `--critical-only --apply --target-ms 5000` 均通过。由于 `bank_account_balance` 已是 critical，
本轮 critical-only 覆盖所有 App Status read model。

| 输出 | status | failed | result count | 最慢 read model | 最慢 enqueue-to-fresh |
| --- | --- | ---: | ---: | --- | ---: |
| `read-model-slo-smoke-critical-apply.json` | pass | 0 | 14 | `no_oa_bank_batch` | 1.360s |
| `read-model-slo-smoke-critical-apply-2.json` | pass | 0 | 14 | `no_oa_bank_batch` | 1.370s |
| `read-model-slo-smoke-critical-apply-3.json` | pass | 0 | 14 | `no_oa_bank_batch` | 1.018s |

第一轮详细结果：

| read model | scope | enqueue-to-fresh | handler | 判定 |
| --- | --- | ---: | ---: | --- |
| `workbench` | `2025-12` | 750ms | 561ms | pass |
| `workbench_relation` | `2026-01` | 611ms | 437ms | pass |
| `bank_detail` | `2026-01` | 562ms | 379ms | pass |
| `bank_account_balance` | `all` | 220ms | 38ms | pass |
| `pending_invoice` | `income:all:2026-01` | 247ms | 64ms | pass |
| `search` | `2025-12` | 591ms | 416ms | pass |
| `invoice_lifecycle` | `2026-05` | 475ms | 290ms | pass |
| `input_invoice_usage` | `2025-12` | 363ms | 175ms | pass |
| `output_invoice_collection` | `2026-01` | 362ms | 189ms | pass |
| `oa_pending_payment` | `2026-01` | 426ms | 257ms | pass |
| `cost_statistics` | `all:2025-12` | 563ms | 388ms | pass |
| `tax_offset` | `2025-12` | 360ms | 195ms | pass |
| `no_oa_bank_batch` | `2026-01` | 1.360s | 1.177s | pass |
| `turnover_ledger` | `all` | 837ms | 638ms | pass |

补充 baseline：

```text
/tmp/finops-stage3-20260613114342/sync-slo-baseline-after.json
```

该 baseline 的 `postgres_connections`、`pg_stat_statements`、`dashboard_queues`、`dashboard_read_models`、
`explain_probes` 均可用。

## 判定

本阶段已完成：

- 所有 App Status read model 的 direct-scope synthetic refresh 连续三轮真实通过 5 秒目标。
- `bank_account_balance` 不再是 optional/非 critical 缺口，且生产有常驻 RabbitMQ worker。
- RabbitMQ dispatcher outbox-to-broker 最坏 idle wait 从 5 秒降为 0.5 秒。

仍不能宣布“全 app 完美闭环”：

- 本阶段验证的是 direct-scope synthetic refresh，不等于所有真实写操作链路 p95。
- 登录态 HTTP 页面首包和首屏 API p95 尚未重新采样；Stage 1 仍记录过 `GET /api/pending-invoices/filter-options`
  单样本 6.086s，需要单独处理。
- Workbench parent/all-scope、导入链路和关联/撤回/配对等写操作后的页面 fresh 体验仍需按业务流验证。

## 下一阶段

Stage 4 必须进入登录态页面/API 和写操作链路：

1. 用 `http_slo_probe` 或等价登录态采样覆盖每个页面首屏 API，目标 p95 `<1s`。
2. 覆盖关键写操作：关联配对、撤回、银行导入确认、发票导入确认、设置/规则变更、OA 同步影响链路。
3. 每个写操作必须验证后端真实 outbox/readiness fresh，目标 enqueue-to-fresh p95 `<5s`，不能只看前端文案。
4. 若 pending invoice filter-options 仍慢，按 `/health.api_performance`、`pg_stat_statements` 和
   `EXPLAIN (ANALYZE, BUFFERS)` 处理 N+1/SQL，不引入 Kafka。

回滚：

- 如 dispatcher 0.5 秒 poll 造成数据库压力，可在 `/etc/fin-ops/fin-ops.rabbitmq-dispatcher.env` 临时设置更高
  `RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS` 并重启 dispatcher，但必须重新跑 read model smoke。
- 如 `bank-account-balance` worker 异常，可 `systemctl disable --now fin-ops-worker@bank-account-balance.service`，
  再回滚到上一 release；这会重新打开银行明细余额闭环缺口，不能作为最终状态。
