# 2026-07-01 成本统计同步性能 GSD 执行方案

## 目标

降低页面同步中卡住的概率，并移除成本统计旧兼容消费链路对新链路的污染。

## 模块边界

- 输入 I/O：`cost_statistics.read_model.refresh(scope_key)` 只能由 `cost-statistics` worker 消费。
- 内部 I/O：成本统计 shard 收敛产生的 `cost_statistics_all_shard`、`cost_statistics_shard_converged` refresh request 必须经 `ReadModelRefreshGateway` 合并 active scope。
- 输出 I/O：dirty scope/outbox/readiness 仍以 PostgreSQL durable queue 为事实源；不伪造 fresh。

## 执行切片

1. Gateway：把成本统计内部收敛原因纳入 active refresh coalesce。
2. Worker：`cost-tax` 只保留 `tax_offset.read_model.refresh`，不再注册/部署 `cost_statistics.read_model.refresh`。
3. Manifest/docs：成本统计 `auxiliary_refresh_worker_instances=()`；税金抵扣继续允许 `cost-tax` 辅助。
4. Tests：覆盖 gateway 合并、registry/manifest/env 合同。

## 验收

- 重复入队同一 active cost_statistics scope 时不再 bump active dirty/outbox。
- `cost-tax` worker command/env 不包含 `cost_statistics.read_model.refresh`。
- 成本统计 manifest 不再声明 `cost-tax` 辅助 worker。
