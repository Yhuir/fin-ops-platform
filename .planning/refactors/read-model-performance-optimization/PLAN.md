# Read Model Performance Optimization Plan

## Goal

把 read model 相关生产读侧和刷新观测路径优化到高性能，同时不改变 read model freshness、dirty/outbox、worker 或业务 payload 合同。

## Baseline Evidence

- 2026-06-28 production critical read model SLO：15 个 scope 中 14 个一次通过 5000ms，`search` 单次 `5951.862ms` 后定向重跑 `499.357ms`。
- 当前最大可验证瓶颈不是业务 projection 正确性，而是 read model refresh 指标聚合：线上完整 runtime monitoring 聚合和直接 health 探测出现长时间无返回/SSH 断开。
- `runtime_monitoring.py` 的 full `health_summary()` 对 read model refresh metrics 使用 `done OR failed/dead_lettered` 条件；现有 `0068` 指标索引只覆盖 `status='done'`，失败样本会让 planner 不能稳定使用该部分索引。

## Scope

### Wave 1

- 给 `job.outbox_events` 增加 read model refresh metric attention partial index，覆盖 full health/dashboard 指标查询里的 `done duration` 和 `failed/dead_lettered` bounded samples。
- 更新迁移守卫测试，防止索引合同回退。
- 更新运维监控文档，记录该指标查询必须走 bounded partial index。

### Deferred

- 不在本轮改业务 read model projection 逻辑。
- 不在本轮做生产写入或受控刷新 apply。
- 不在本轮新增压测框架；已有 SLO 工具继续作为生产验证入口。

## Acceptance Criteria

- 新 migration 文件登记到 migration 顺序清单。
- migration guard 断言新增 index 名称、列和 partial predicate。
- `tests.test_postgres_migrations` 通过。
- `tests.test_runtime_monitoring` 继续通过，证明 runtime summary 合同未改变。
- `bash scripts/verify.sh docs` 通过或明确报告阻塞。

## Next Prompt

执行 Wave 1：新增最小索引迁移和测试，验证本地合同；生产 apply/deploy 只有在用户明确要求生产操作时再做。
