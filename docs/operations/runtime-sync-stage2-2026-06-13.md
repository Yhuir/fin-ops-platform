# Runtime 同步 Stage 2 - Direct-scope smoke 结果

本阶段目标是把 Stage 1 新增的受控 `read_model_slo_smoke` 放到生产 release 中 dry-run/apply，
验证每个 App Status read model 的 direct-scope `enqueue_at -> fresh` 真实耗时。未执行 DDL、
migration、业务 repair、服务 activation 或 worker 配置变更。

## 发布方式

- 本地提交：`9003ea4c`。
- 上传 release：`/opt/fin-ops/releases/main-9003ea4c-stage2-smoke-202606131120/src`。
- 部署命令使用 `--no-activate`，只上传并执行 release check。
- 生产 active release 仍是 `main-c9cd87e8-20260613103951`。
- 未重启 API、worker、RabbitMQ、PostgreSQL 或 systemd unit。

## Dry-run

生产 dry-run 输出：

```text
/tmp/finops-read-model-slo-smoke-dry-run-202606131124.json
```

dry-run 结果：

- `status=dry_run`。
- `planned_scope_count=14`。
- `missing_read_model_keys=[]`。

计划覆盖的 read model / scope：

| read model | scope | source |
| --- | --- | --- |
| `workbench` | `2025-12` | active generation |
| `workbench_relation` | `2026-01` | readiness |
| `bank_detail` | `2026-01` | readiness |
| `bank_account_balance` | `all` | readiness |
| `pending_invoice` | `income:all:2026-01` | readiness |
| `search` | `2025-12` | readiness |
| `invoice_lifecycle` | `2026-05` | readiness |
| `input_invoice_usage` | `2025-12` | readiness |
| `output_invoice_collection` | `2026-01` | readiness |
| `oa_pending_payment` | `2026-01` | readiness |
| `cost_statistics` | `all:2025-12` | readiness |
| `tax_offset` | `2025-12` | readiness |
| `no_oa_bank_batch` | `2026-01` | readiness |
| `turnover_ledger` | `all` | readiness |

## 全量 apply 阻断

首次全量 apply 使用 180 秒外部 timeout，进程退出码为 `124`，工具未写出 JSON 报告。阻断点是
`bank_account_balance`：

- `bank_account_balance` 在 App Status registry 中是 `critical=false`。
- 生产缺少 `/etc/fin-ops/fin-ops.worker.bank-account-balance.env`。
- registry check 显示该 worker `required=false`，因此 `/health/ready` 不会因为它缺失而失败。
- smoke 已真实入队 `bank_account_balance.read_model.refresh`，但没有常驻 worker 消费，导致 dirty/outbox
  出现 1 条 pending。

修复方式是运行一次同一 release 的真实 worker 处理该事件，不手工改状态、不删除 event、不伪造 readiness。
处理后生产恢复：

| 指标 | 结果 |
| --- | --- |
| `/health/ready.status` | `ready` |
| dirty scopes | `done` only |
| active queue backlog | 0 |
| required worker missing/stale/mismatch | 0 / 0 / 0 |
| RabbitMQ depth/unacked/DLQ | 0 / 0 / 0 |

结论：如果产品目标是“全 app 每个页面/read model 都在 5 秒内真实同步”，不能继续让
`bank_account_balance` 处于非 required 且无常驻 worker 的状态。下一阶段必须二选一：

- 将它纳入页面 SLO，补 systemd/env/registry required 语义和 smoke 验收。
- 证明它不是任何页面首屏/操作闭环所需 read model，并在产品与运维文档中保留 `critical=false` 原因。

## Critical-only apply

为避免可选 worker 阻断对当前页面关键链路的判断，随后按 registry `critical=true` 跑 critical-only scope。
生产输出：

```text
/tmp/finops-read-model-slo-smoke-critical-apply-202606131140.json
```

结果：13 个 critical read model 中 10 个通过，3 个未达到 5 秒目标。

| read model | scope | enqueue-to-fresh | handler | 判定 |
| --- | --- | ---: | ---: | --- |
| `workbench` | `2025-12` | 14.436s | 919ms | 不达标 |
| `workbench_relation` | `2026-01` | 1.838s | 275ms | 达标 |
| `bank_detail` | `2026-01` | 2.281s | 371ms | 达标 |
| `pending_invoice` | `income:all:2026-01` | 2.073s | 29ms | 达标 |
| `search` | `2025-12` | 1.066s | 515ms | 达标 |
| `invoice_lifecycle` | `2026-05` | 3.331s | 320ms | 达标 |
| `input_invoice_usage` | `2025-12` | 4.645s | 147ms | 达标但余量小 |
| `output_invoice_collection` | `2026-01` | 4.586s | 125ms | 达标但余量小 |
| `oa_pending_payment` | `2026-01` | 4.698s | 268ms | 达标但余量小 |
| `cost_statistics` | `all:2025-12` | 4.640s | 243ms | 达标但余量小 |
| `tax_offset` | `2025-12` | 4.547s | 176ms | 达标但余量小 |
| `no_oa_bank_batch` | `2026-01` | 5.304s | 952ms | 不达标 |
| `turnover_ledger` | `all` | 5.345s | 1.488s | 不达标 |

critical-only smoke 后复核：

| 指标 | 结果 |
| --- | --- |
| `/health/ready.status` | `ready` |
| dirty scopes | `done` only |
| active queue backlog | 0 |
| required worker missing/stale/mismatch | 0 / 0 / 0 |
| RabbitMQ depth/unacked/DLQ | 0 / 0 / 0 |

补充 baseline 输出：

```text
/tmp/finops-stage2-sync-slo-baseline-after-critical-202606131145.json
```

## 判定

Stage 2 不能宣布“全 app 5 秒内全部真实同步”完成。

未完成原因：

- `bank_account_balance` 有 readiness 和 refresh event，但没有常驻 worker；全量 smoke 会被真实 pending event
  阻断。这是配置/产品关键性定义缺口，不是工具误报。
- `workbench` direct-scope 仍为 14.436 秒，超过 5 秒目标。handler 本身约 919ms，主要问题不是单次
  projection SQL，而是调度、queue wait、链式 aggregate 或 worker 串行余量。
- `no_oa_bank_batch` 和 `turnover_ledger` 都在 5.3 秒左右，handler 分别约 952ms 和 1.488s，说明
  调度余量很小，轻微排队就会越线。
- 多个通过项在 4.5 到 4.7 秒之间，没有生产安全余量。

当前证据不支持引入 Kafka：

- RabbitMQ queue depth、unacked 和 DLQ 在 smoke 后均为 0。
- PostgreSQL durable outbox/dirty/readiness 已能收敛，当前瓶颈不是 broker 吞吐。
- RabbitMQ consumer 已作为 wakeup/transport 存在，替换成 Kafka 不会解决可选 worker 缺失、每轮 drain
  数量小、共享 worker 串行、Workbench aggregate 链路和 near-threshold handler 的问题。

## 下一阶段执行入口

Stage 3 目标是先把所有 critical read model 的 direct-scope SLO 稳定压到 5 秒以内，并决定
`bank_account_balance` 的全 app 语义。不得以缓存或前端状态伪装 fresh。

执行顺序：

1. 保持 `main` 小提交、小验证、可回滚；先确认 Stage 2 文档和 smoke 工具变更已提交。
2. 检查 worker runtime 配置：每个 read model 的 systemd unit/env、RabbitMQ transport、consumer count、
   `FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION`、poll interval、prefetch 和 shared worker 事件类型。
3. 处理 `bank_account_balance`：补 required worker 闭环，或写明并测试它不属于页面/操作闭环。若纳入 SLO，
   必须新增 env/systemd/manifest/test/docs，并跑全量 smoke。
4. 对 `workbench` 采集更细 profile：区分 event 创建到 RabbitMQ 投递、RabbitMQ delivery 到 claim、
   claim 到 handler start、handler duration、active generation publish、aggregate/all-scope enqueue 的耗时。
5. 对 `no_oa_bank_batch`、`turnover_ledger` 先验证 worker 调度参数和专属 worker 余量；只有 handler
   仍超过目标时再进入 SQL/索引优化。
6. 重新跑 critical-only apply。目标不是单次偶然通过，而是连续多轮每个 critical read model 都 `<5s`，
   且 p95 有余量。
7. 全量 apply 验收必须覆盖所有 App Status read model；如果仍排除 `critical=false`，报告必须解释产品原因。
8. 再进入登录态 HTTP SLO：页面 shell 和每个页面首屏 API p95 `<1s`，操作链路写入后对应页面
   enqueue-to-fresh p95 `<5s`。
9. 只有当 SQL profile 证明 handler 是主瓶颈时，才执行 targeted index/partition 变更；先用
   `EXPLAIN (ANALYZE, BUFFERS)`、`pg_stat_statements` 和回滚 SQL 定义验收。

第三方组件取舍：

- 保留 RabbitMQ 作为 wakeup/transport；先优化 consumer/worker 参数和 registry 覆盖。
- Redis fresh-cache 只能缓存 fresh gate 后 payload，不参与 readiness 判定。
- PgBouncer 当前不是第一优先级；Stage 1 连接数为 26/100，未见连接瓶颈。若提高 worker 并发后
  `connection_acquire_ms` 或连接数持续升高，再接入 PgBouncer。
- Prometheus/Grafana 继续作为长期观测；它补充但不替代 App Status/health/ready 的事实状态。
- Kafka 暂不引入；除非出现 RabbitMQ broker 层不可接受的 publish/consume 延迟、持久 backlog、DLQ
  或跨服务事件流需求，否则只会增加运维复杂度。

## 验证

本阶段本地验证应覆盖：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_read_model_slo_smoke.py tests/test_read_model_refresh_gateway.py tests/test_runtime_queue.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_sync_slo_baseline.py -q
python3 -m py_compile backend/src/fin_ops_platform/tools/read_model_slo_smoke.py
bash scripts/verify.sh docs
git diff --check
```

生产验证已完成：

- 上传 release check 通过。
- dry-run 输出完整且覆盖 14 个 read model。
- 全量 apply 暴露 optional worker 缺口，并通过真实 worker 恢复收敛。
- critical-only apply 输出完整，生产最终 `/health/ready`、dirty/outbox、RabbitMQ 均收敛。
