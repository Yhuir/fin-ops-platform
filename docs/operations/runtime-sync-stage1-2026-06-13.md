# Runtime 同步 Stage 1 - SLO 采集与 smoke 工具

本阶段目标是执行全 app 同步闭环的第一步：用生产事实重新采集 SLO 基线，并补齐可受控触发 synthetic refresh 的工具。未执行 migration、DDL、服务重启、repair、requeue 或业务逻辑优化。

## 生产采集

- 采集时间：2026-06-13 11:00 CST。
- 当前 release：`main-c9cd87e8-20260613103951`。
- systemd effective working directory：`/opt/fin-ops/releases/main-c9cd87e8-20260613103951/src`。
- 原始采集文件：生产机 `/tmp/finops-stage1-20260613110042/`。
- 采集命令：
  - `curl http://127.0.0.1:18001/health`
  - `curl http://127.0.0.1:18001/health/ready`
  - `PYTHONPATH=<release>/backend/src python -m fin_ops_platform.tools.sync_slo_baseline --json`
  - `python -m fin_ops_platform.tools.runtime_worker_manifest --json`
  - `rabbitmqctl -p /finops list_queues ...`
  - `systemctl list-units 'fin-ops-worker@*.service'`

注意：文档里的 `/opt/fin-ops/current` 在当前生产机不存在，systemd drop-in 已覆盖到 release 目录。后续 runbook 需要统一使用 systemd effective path 或补回 current symlink，避免排障命令误导。

## 当前健康状态

| 指标 | 当前值 | 判定 |
| --- | ---: | --- |
| `/health/ready.status` | `ready` | 达标 |
| required worker missing/stale/mismatch | 0 / 0 / 0 | 达标 |
| `job.read_model_dirty_scopes` active backlog | 0 | 达标 |
| read model outbox active backlog | 0 | 达标 |
| failed jobs | 0 | 达标 |
| stale dirty scope count | 0 | 达标 |
| RabbitMQ depth/unacked/DLQ | 0 / 0 / 0 | 达标 |
| RabbitMQ consumer count | 15 | 达标 |
| PostgreSQL connections | 26 / 100 | 未见连接数瓶颈 |

这只能说明当前无 backlog/blocker，不能证明“写入后 5 秒内 fresh”达标。

## Current-window SLO

采集时最近 15 分钟没有 refresh 样本，因此不能用 recent_15m 证明当前体验。最近 1 小时仍包含 10:42-10:43 的 refresh 样本，结论是不达标：

| read model | sample | duration p95 | enqueue-to-fresh p95 | 判定 |
| --- | ---: | ---: | ---: | --- |
| `pending_invoice` | 40 | 152ms | 70.698s | 不达标，调度/排队主导 |
| `oa_pending_payment` | 2 | 280ms | 70.402s | 不达标，调度/排队主导 |
| `no_oa_bank_batch` | 2 | 1.647s | 67.858s | 不达标，调度/排队主导 |
| `output_invoice_collection` | 2 | 153ms | 63.901s | 不达标，调度/排队主导 |
| `input_invoice_usage` | 7 | 7.117s | 52.534s | 不达标，handler 也超过 5s |
| `bank_detail` | 6 | 1.407s | 50.782s | 不达标，调度/排队主导 |
| `search` | 2 | 6.648s | 12.566s | 不达标，handler 也超过 5s |
| `cost_statistics` | 6 | 2.358s | 10.950s | 不达标，调度/排队主导 |
| `workbench_relation` | 3 | 1.104s | 5.889s | 接近但仍不达标 |
| `tax_offset` | 2 | 1.086s | 5.815s | 接近但仍不达标 |

缺少 recent current 样本或 current 样本不足的 read model 仍不能判定达标：

- `workbench`
- `invoice_lifecycle`
- `turnover_ledger`
- `bank_account_balance`

## API 首包线索

`/health.api_performance` 是进程内 rolling window，样本数小的 endpoint 只能作为线索，不能作为最终验收。

当前最慢 endpoint：

| endpoint | sample | p95 | DB p95 | SQL count p95 | 说明 |
| --- | ---: | ---: | ---: | ---: | --- |
| `GET /api/pending-invoices/filter-options` | 1 | 6.086s | 1.189s | 740 | 明显 N+1/构造风险，需要专项确认。 |
| `POST /api/workbench/actions/confirm-link` | 1 | 1.561s | 1.421s | 92 | 写路径首包超 1s，样本不足但需关注。 |
| `GET /api/pending-invoices/rows` | 1 | 1.480s | 220ms | 116 | 首包超 1s，样本不足但需关注。 |
| `GET /health/ready` | 2 | 684ms | 539ms | 18 | 可接受但监控查询成本偏高。 |
| `GET /api/app-health` | 12 | 577ms | 130ms | 31 | 可接受。 |
| `GET /api/workbench/groups` | 8 | 553ms | 332ms | 18 | 当前达标。 |

下一阶段必须用 `http_slo_probe` 做登录态 p95 采样；本阶段没有管理员 token/cookie，因此未完成登录态页面首包验收。

## PostgreSQL 观测

`sync_slo_baseline` 已成功采集 `pg_stat_statements`，说明 extension 当前可用。

最大表仍集中在 Workbench projection：

| 表 | total | estimated rows | 结论 |
| --- | ---: | ---: | --- |
| `read_model.workbench_group_rows` | 3.70GB | 445k | 最大项，仍是写放大/索引优化重点。 |
| `read_model.workbench_groups` | 2.87GB | 224k | 大表，继续监控。 |
| `read_model.workbench_rows` | 2.29GB | 382k | 大表，继续监控。 |
| `read_model.workbench_snapshots` | 1.53GB | 490 | 大 JSON payload 仍是长期优化空间。 |
| `read_model.search_index_rows` | 118MB | 1.7k | 可接受。 |
| `job.outbox_events` | 74MB | 36k | 可接受。 |

大索引里仍有零扫描或低扫描候选，但不能盲删：

- `workbench_group_rows_generation_scope_identity_zone_idx` 95MB，`idx_scan=0`。
- `workbench_rows_generation_scope_identity_idx` 93MB，`idx_scan=0`。
- `workbench_groups_bank_sort_idx` 47MB，`idx_scan=0`。
- `workbench_rows_counterparty_trgm` 36MB，`idx_scan=0`。
- `workbench_group_rows_searchable_text_trgm` 310MB，`idx_scan=444`，仍有扫描，不能按 0-scan 删除。

`pg_stat_statements` 当前 top SQL 显示：

- OA attachment invoice cache 查询 10 calls、total 88.953s、mean 8.895s，是当前最大单 SQL 线索。
- `app.app_settings` 读取 81k calls、total 64.446s，频率过高但单次低。
- outbox status monitoring 查询 6.6k calls、total 58.344s。
- workbench generation consistency 查询 6.5k calls、total 54.925s。
- Workbench groups/group_rows/rows insert 仍是 projection 写入主要成本。

结论：除了 read model handler，监控查询和 OA attachment/cache 查询也需要纳入后续 SQL profile。分区不是第一刀；先按 top SQL/EXPLAIN 和索引扫描数据做小步优化。

## Smoke 工具

新增工具：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.read_model_slo_smoke --json
```

默认 dry-run，只发现每个 App Status read model 的可用 direct scope，不写 queue。显式 `--apply` 才会通过 `ReadModelRefreshGateway` 入队，等待对应 outbox event `done` 且 `read_model.app_status_readiness` 为 `fresh`，再计算 `created_at -> processed_at` 的真实 enqueue-to-fresh。

示例：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.read_model_slo_smoke \
  --json \
  --apply \
  --target-ms 5000 \
  --timeout-seconds 120 \
  --output /tmp/finops-read-model-slo-smoke-$(date +%Y%m%d%H%M%S).json
```

scope 选择策略：

- 优先选择已有 fresh readiness 或 active generation 中的 direct shard，避免把无效 scope 投进 durable queue。
- `workbench` 使用 active generation。
- `cost_statistics` 会选择 `active:YYYY-MM` / `all:YYYY-MM` 这类直接月份 shard，不默认选择 `active:all` / `all:all` 父 scope。
- 只有 `turnover_ledger`、`bank_account_balance` 等当前只有 `all` 的 read model 会选择 `all`。
- 可用 `--scope READ_MODEL_KEY=SCOPE_KEY` 显式覆盖。

本阶段未在生产执行 `--apply`。原因是新工具尚未随 release 部署；直接在生产粘贴临时代码会降低审计质量。下一阶段应先部署工具或使用受控 release，然后先跑 dry-run，再跑一轮 direct-scope apply。

## 下一阶段执行入口

Stage 2 目标是部署并运行受控 `read_model_slo_smoke`，拿到每个 App Status read model 的 direct-scope
enqueue-to-fresh current 证据。不要优化业务逻辑，除非 smoke 证明具体瓶颈。

执行要求：

1. 确认 `main` 工作树干净，阶段 1 变更已小提交。
2. 发布或以受控 release 方式让生产可运行 `fin_ops_platform.tools.read_model_slo_smoke`。不得粘贴临时代码绕过审计。
3. 在生产运行 dry-run，保存 `/tmp/finops-read-model-slo-smoke-dry-run-<ts>.json`。
4. 审查 dry-run scopes：确认每个 App Status read model 都有 scope；若缺失，先补只读原因，不得猜 scope。
5. 运行 direct-scope apply，保存 `/tmp/finops-read-model-slo-smoke-apply-<ts>.json`。
6. 运行 `/health/ready` 和 `sync_slo_baseline --json` 复核 dirty/outbox/readiness/RabbitMQ 均收敛。
7. 如果 direct-scope smoke 全部 `<=5s`，下一阶段进入 parent/all-scope 和登录态 `http_slo_probe`。
8. 如果 direct-scope smoke 失败，按失败类型分流：
   - enqueue-to-fresh 高但 handler duration 低：优先 worker/RabbitMQ 调度、共享 worker 串行、`FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION=1`、prefetch/consumer 拆分。
   - handler duration 高：优先 SQL/projection profile 和 targeted index/query 优化。
   - event failed/dead-letter：先修真实 blocker，不删除失败伪装 green。
9. 输出 Stage 2 报告，包含 raw JSON 路径、每个 read model 结果、是否达标和验证命令。

## 验证

本阶段本地验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_read_model_slo_smoke.py tests/test_sync_slo_baseline.py -q
python3 -m py_compile backend/src/fin_ops_platform/tools/read_model_slo_smoke.py
```

结果：6 passed，py_compile 通过。
