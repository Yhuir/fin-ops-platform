# Runtime 同步 SLO 基线 - 2026-06-13

本报告用于把“全 app 每个页面 5 秒内真实同步”的目标落成可验证闭环。它不是实现记录，不修改生产链路，不保存原始执行指令。

## 采集口径

- 代码事实源：`APP_STATUS_READ_MODEL_REGISTRY`、`RUNTIME_WORKER_REGISTRY`、`ReadModelScopePolicyRegistry`、`docs/modules/*`、`docs/operations/postgresql-runtime.md`、`docs/operations/monitoring.md`。
- 运行事实源：本轮已采集的生产 `/health/ready` snapshot、`docs/operations/runtime-sync-baseline-2026-06-12.md`、`docs/operations/runtime-sync-repair-2026-06-12.md`。
- 当前 release：`main-c9cd87e8-20260613103951`。
- 当前生产状态：`/health/ready.status=ready`；dirty scope、pending outbox、stale worker、missing worker、stale dirty scope 均为 0。
- 限制：当前本地没有可用免密 SSH，且未安装 `sshpass`，因此本报告没有重新执行 SQL 级 `sync_slo_baseline`。下一阶段必须在生产机或可认证运维会话中重新运行 collector，保存 JSON 原始证据。

## 目标 SLO

全 app 目标必须按每个 read model/page 统一验收，不能只看 Workbench：

| 指标 | 目标 | 说明 |
| --- | ---: | --- |
| 页面首包 p95 | `< 1s` | 首屏 API 或页面主数据请求，不包含用户主动展开重详情。 |
| 每个 read model enqueue-to-fresh p95 | `<= 5s` | 使用 current window，不用 7 天历史样本证明当前达标。 |
| 每个 read model handler duration p95 | `<= 5s` | 超过时进入 SQL/projection 专项。 |
| 失败率 | `0 current-effective failure` | 历史已覆盖 failure 可归档；当前 blocker 必须暴露并修复。 |
| active backlog | 正常态为 `0` | `job.outbox_events`、`job.read_model_dirty_scopes` 不得长期 pending/processing/failed。 |
| worker readiness | missing/stale/mismatch 均为 `0` | 以 registry 和 systemd/heartbeat/current-effective 共同判断。 |

说明：工程上不能承诺数据库、网络、broker 永远零故障；可承诺的是不假同步、不吞失败、可自动恢复/重试、当前有效 blocker 不长期存在，并用 SLO/告警证明。

## 当前结论

当前 App Status 已经没有失败 blocker，但“全 app 5 秒内 fresh”未达标。主要问题不是所有页面生成 payload 慢，而是多个 read model 的 enqueue-to-fresh 延迟远超 5 秒。

本轮 `/health/ready` current window 中，多个 handler duration 较短但 enqueue-to-fresh 很高，说明优先瓶颈是 worker wakeup、调度、共享 worker 串行处理、积压窗口或 consumer/publish 链路，而不是单个 SQL payload 生成。

| read model | worker | current p95 duration | current p95 enqueue-to-fresh | 判定 |
| --- | --- | ---: | ---: | --- |
| `pending_invoice` | `search-pending` | 152ms | 70.698s | 不达标，队列/调度主导。 |
| `oa_pending_payment` | `invoice-usage-collection` | 280ms | 70.402s | 不达标，队列/调度主导。 |
| `no_oa_bank_batch` | `no-oa-bank-batch` | 1.647s | 67.858s | 不达标，队列/调度主导。 |
| `output_invoice_collection` | `invoice-usage-collection` | 153ms | 63.900s | 不达标，队列/调度主导。 |
| `input_invoice_usage` | `invoice-usage-collection` | 7.117s | 52.534s | 不达标，handler 也超过 5s。 |
| `bank_detail` | `bank-detail` | 1.407s | 50.782s | 不达标，队列/调度主导。 |
| `search` | `search-pending` | 6.648s | 12.566s | 不达标，handler 和调度都要看。 |
| `cost_statistics` | `cost-tax` | 2.358s | 10.950s | 不达标，调度主导。 |
| `workbench_relation` | `workbench-relation` | 1.104s | 5.889s | 接近但仍不达标。 |
| `tax_offset` | `cost-tax` | 1.086s | 5.815s | 接近但仍不达标。 |

缺少 current sample 的 read model 不能判定达标；下一阶段必须用合成 refresh smoke 或真实业务操作触发样本：

- `workbench`
- `invoice_lifecycle`
- `turnover_ledger`
- `bank_account_balance`

## 页面与 read model 覆盖

| 页面/功能域 | 主要 read model | 当前 SLO 风险 |
| --- | --- | --- |
| 关联台 `/` | `workbench`、`workbench_relation` | Workbench 已做局部优化，但仍需 current synthetic sample 证明全路径 `<5s`。 |
| 批量账销、关系撤回、跨页配对 | `workbench_relation` | 当前 p95 约 5.889s，必须压到 5s 内；写入口继续 fail fast，不得绕过 freshness。 |
| 待找发票 | `pending_invoice`、`search`、`invoice_lifecycle`、`workbench_relation` | 当前 `pending_invoice`/`search` 不达标；invoice lifecycle 缺 current sample。 |
| 进项发票使用 | `input_invoice_usage`、`workbench_relation` | 当前 handler 超 5s，需 SQL/read model payload 专项。 |
| 销项收款 | `output_invoice_collection`、`workbench_relation` | 当前 enqueue-to-fresh 不达标。 |
| OA 待付款核对 | `oa_pending_payment`、`invoice_lifecycle` | 当前 enqueue-to-fresh 不达标。 |
| 银行明细 | `bank_detail`、`bank_account_balance` | 当前 `bank_detail` 不达标，余额模型缺 current sample。 |
| 免 OA 批次 | `no_oa_bank_batch`、`workbench_relation` | 当前 enqueue-to-fresh 不达标。 |
| 税金抵扣 | `tax_offset` | 接近但仍不达标。 |
| 成本统计 | `cost_statistics` | 当前 enqueue-to-fresh 不达标；scope policy 已存在，只能走 gateway normalization。 |
| 往来款管理 | `turnover_ledger`、`workbench`、`workbench_relation`、`cost_statistics`、`search` | 缺 current sample，必须加入合成验收。 |
| 导入页 | `import.process.requested`、下游多个 read model | 导入成功不等于下游页面 fresh，必须跟踪 fan-out 到各 read model 的 p95。 |
| App Health / App Status | runtime metrics | 当前用于事实暴露；后续 Prometheus/Grafana 读取它，不替代它。 |

## 组件取舍

| 组件 | 是否需要 | 结论 |
| --- | --- | --- |
| RabbitMQ real consumers | 需要，且已经有现成架构 | 继续使用现有 topology/dispatcher/consumer，不引入 Kafka 替代。下一阶段重点验证每个 event type 是否真实走 RabbitMQ、prefetch/ack/nack/DLQ 是否正确、共享 worker 是否串行拖慢。 |
| Redis fresh-cache | 需要 | 只缓存 fresh gate 后 payload。页面秒开可读 last fresh snapshot；缓存不能替代 readiness，也不能把 stale 伪装成 fresh。 |
| PgBouncer | 条件需要 | 2-3 人使用不是当前瓶颈；如果提高 worker 并发或连接获取 p95 升高，再作为连接保护层启用。可纳入完整栈，但不应先于 SLO/连接证据。 |
| Prometheus/Grafana 或 OpenTelemetry | 必须 | 不是替换 `/health/ready`、App Health 和 runtime docs，而是把现有指标做时序化、告警化和长期审计。 |
| PostgreSQL 索引优化 | 必须 | 先基于 `pg_stat_statements`、`EXPLAIN`、表/索引扫描数据优化。Workbench 大索引已是明确方向；其他 read model 必须逐个证明。 |
| PostgreSQL 分区 | 有条件需要 | 不应全库盲目分区。先对 workbench、relation、invoice lifecycle、search 等大表按查询路径证明收益和 migration/rollback，再实施。 |
| Kafka/Redpanda | 当前不需要 | 当前瓶颈是 wakeup/worker/projection/观测闭环，不是高吞吐事件流。引入 Kafka 会扩大运维面，并绕开已有 RabbitMQ/read model governance。 |

## 页面秒开与写操作边界

页面可以秒开 fresh snapshot，并在后台追赶增量；但写操作不能等同于“全 app 后台完全 loaded”。

规则如下：

1. 只读页面可以显示最近一次通过 freshness gate 的 payload；如果目标 scope 正在刷新，UI 可显示正在更新，但不能把旧 payload 标为 fresh。
2. 关联、配对、撤回、规则保存、导入确认等写操作不需要等待全 app 所有 read model 完成。
3. 写操作必须检查本操作依赖的目标 read model/source version/权限/审计前置条件；例如依赖 `workbench_relation` 的操作在 relation read model non-fresh 时返回 409，不做半写入。
4. 写事务成功后，facts、audit、dirty scope、outbox 必须在同一边界提交或可回滚；后续 read model refresh 用真实 worker 完成。
5. 前端只能基于后端返回的 `read_model_status`、`source_versions` 和 job/refresh 状态提示用户，不自行“补绿”。

## 闭环缺口

当前还缺以下证据，不能宣称全 app 达标：

- 每个 read model 的 current-window synthetic refresh 样本。
- 每个关键页面登录态首包 p95。
- `sync_slo_baseline --json` 新版生产 JSON，包括连接数、表大小、索引使用、EXPLAIN 和 `pg_stat_statements` 状态。
- `pg_stat_statements` shared preload 是否真正启用；只创建 extension 不够。
- RabbitMQ consumer per event type 的 depth、unacked、DLQ、ack/nack、publisher confirm p95。
- worker 共享实例内的 per-event 串行等待时间，尤其 `invoice-usage-collection` 和 `search-pending`。
- Redis fresh-cache 的 key/version/fresh gate 证明。
- 旧模块删除 impact analysis、调用点迁移和回归测试。
- DDL、RabbitMQ 切换、Prometheus/Grafana、Redis cache、PgBouncer 的 rollback/DR runbook。

## 下一阶段执行入口

下一阶段不是先做 Kafka 或盲目分区，而是先把 SLO 采集和当前调度瓶颈闭环：

1. 在生产机运行 `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.sync_slo_baseline --json`，保存 JSON。
2. 建立每个 read model 的 synthetic refresh smoke，触发后等待 fresh，记录 enqueue-to-fresh、handler duration、failure、dirty/outbox 收敛。
3. 对每个 RabbitMQ eligible worker 验证真实 consumer 路径、consumer count、prefetch、DLQ、publisher confirm 和 PostgreSQL durable 状态一致。
4. 拆分或并发化共享 worker 中拖慢的 event type；先测 `invoice-usage-collection`、`search-pending`、`cost-tax`。
5. 对 `input_invoice_usage` 和 `search` 做 SQL/projection profile，因为它们 current handler p95 已超过 5s。
6. 接入 Prometheus/Grafana 或 OpenTelemetry，至少覆盖 read model current-window p95、failure rate、pending age、worker lag、RabbitMQ depth/DLQ、API p95、DB p95。
7. 只有当连接获取 p95 或 worker 并发需要证明 PgBouncer 有收益时，才灰度 PgBouncer。
8. 只有当 `pg_stat_statements`、EXPLAIN 和表体积证明收益时，才做索引/分区 DDL。

验收时必须连续观察至少一个真实业务窗口和一轮 synthetic all-read-model refresh；所有 current-effective blocker 为 0，所有 read model current p95 enqueue-to-fresh `<= 5s`，页面首包 p95 `< 1s`。
