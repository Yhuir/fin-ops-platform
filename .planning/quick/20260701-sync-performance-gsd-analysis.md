# 2026-07-01 页面同步慢 GSD 全量分析

## 问题

用户反馈各页面同步慢，截图显示 App Health 中多个数据域处于“同步中”，包括关联台、成本统计、OA 待付款核对等。目标是从模块化架构视角定位真实原因，并判断是否有耗时缩短空间。

## 线上证据

- Release：`main-e6de7bcb-20260701141033`，git commit `e6de7bcb8eb8f702cd400296be6a05fdb6e37082`。
- `/health/ready` 显示服务 ready、schema version 83、worker 服务均 active。
- 队列不是大面积堆积，主要是少数 scope 长时间卡住：
  - `queue_backlog`: pending 4, processing 1。
  - `dirty_scopes`: pending 12。
  - stale dirty scope 样本包括 `cost_statistics active:2026-03`、`cost_statistics all:2026-03`、`workbench all`、`cost_statistics active:all`、`cost_statistics all:all`。
- scope contract 检查存在当前未覆盖 dead-letter：
  - `cost_statistics.read_model.refresh`
  - scope `all:2026-03`
  - error `canceling statement due to statement timeout`
  - status `dead_lettered`
- 进程状态：
  - `cost-statistics` worker 运行约 15 分钟，命令行为 `--statement-timeout-seconds 90 --task-timeout-seconds 300 --max-events-per-iteration 8`，RSS 约 500MB。
  - `cost-tax` worker 同时消费 `cost_statistics` 与 `tax_offset`，RSS 超过 4GB。
  - `workbench` worker CPU 约 40%，仍在处理 `workbench.read_model.refresh`。
- 线上 API 性能样本：
  - `GET /api/cost-statistics/explorer`: p50 5322ms, p95 8031ms, DB p50 1316ms, DB p95 3656ms。
  - `GET /api/batch-accounting`: p50 1296ms, p95 4315ms, DB p50 879ms, DB query count p50 101。
  - `GET /api/workbench/groups`: p50 776ms, p95 3579ms, DB p50 451ms, DB p95 2043ms。
  - `GET /api/app-health`: p50 456ms, p95 919ms, DB query count p50 30。

## 模块边界判断

### Read Model 模块

输入：

- `job.outbox_events`
- `job.read_model_dirty_scopes`
- `read_model.app_status_readiness`
- 各业务事实表和上游 read model。

输出：

- 各页面读取的 `read_model.*` 投影表。
- freshness/status 给 App Health 和 API fresh gate 使用。

边界现状：

- PostgreSQL durable queue 是事实源，符合架构。
- Redis 只是 fresh gate 后的短 TTL 缓存，符合架构。
- 问题不是没有边界，而是部分投影单次构建成本过高，且父 scope 与 shard scope 的收敛会互相放大。

### Cost Statistics 模块

输入：

- `cost_statistics.read_model.refresh(scope_key)`
- `read_model.workbench_groups(scope_key=YYYY-MM)`
- `read_model.cost_statistics_rows` 月份 shard
- app settings 中项目状态、标签规则版本、OA projection/parser version。

输出：

- `read_model.cost_statistics_read_models`
- `read_model.cost_statistics_rows`
- cost explorer Redis cache
- readiness fresh/stale/refreshing 状态。

边界现状：

- 月份 shard 与父 scope 已拆分，设计方向正确。
- 当前 month shard `all:2026-03` 仍会从 `read_model.workbench_groups` 拉整月 `payload/raw_payload` 到 Python 解析，这个 I/O 太重。
- 父 scope `active:all/all:all` 会在 shard 完成后被重复入队；gateway 对 `cost_statistics_shard_converged` / `cost_statistics_all_shard` 没有 active coalesce，导致收敛链路被放大。
- `cost-tax` 兼容 worker 同时消费 `cost_statistics` 和 `tax_offset`，与专用 `cost-statistics` worker 并发处理同一高成本 event type，内存压力明显。

### Workbench 模块

输入：

- 业务事实、关系变更、导入事实。

输出：

- `read_model.workbench_groups`
- active generation
- downstream `cost_statistics`、`search`、`workbench_relation` 等 scope。

边界现状：

- 工作台仍是多个页面 read model 的上游。
- `workbench all` 同步时会影响下游成本统计父 scope 与页面 App Health 状态。
- 当前 `workbench` worker CPU 高，说明上游刷新也在占资源。

### API Read Path

输入：

- 页面请求、scope、filter、freshness。

输出：

- 页面 payload 和 App Health 状态。

边界现状：

- `cost-statistics/explorer` 的 API read path 仍会在 cache miss 或大 scope 读取时组装全 payload，p50 已超过 5s。
- `batch-accounting` API 单次约 101 个 SQL，属于 N+1 或过宽 read model 缺口，需要独立治理。
- App Health 每次约 30 个 SQL，p95 近 1s；当后台 worker 压力高时，健康浮层也会变慢。

## 真实原因

1. 不是前端慢，也不是 worker 没启动。所有 worker active，问题集中在少数 read model scope 长时间 pending/processing。
2. 直接阻塞点是 `cost_statistics all:2026-03`。它已有当前 dead-letter，错误是 PostgreSQL statement timeout。
3. 同步慢的结构性原因是成本统计 read model 的 I/O 边界仍偏重：
   - 月份 shard 读取整月 workbench group JSON。
   - Python 再解析 OA/bank payload、费用上下文、项目范围。
   - 写入 read model 后还要替换 `cost_statistics_rows`。
4. 父 scope 收敛放大了耗时：
   - 月份 shard 完成后入队 `active:all/all:all`。
   - 父 scope 如果发现 shard 不 fresh，又重新入队 shard。
   - gateway 未合并 `cost_statistics_shard_converged` / `cost_statistics_all_shard` 的 active refresh，容易重复 bump。
5. worker 心跳边界不够细：
   - 心跳只在事件前后更新。
   - 长时间 SQL/Python 投影中，worker 真实在跑，但 App Health 显示 stale/processing，用户感知为一直同步。
6. API read model 有独立性能债：
   - cost explorer p50 5.3s，说明页面读路径本身也慢。
   - batch-accounting p50 101 SQL，说明批量账务页面还存在 read model 聚合不足或 N+1 查询。

## 是否可以提高性能

可以，且优化空间很大。优先级如下：

1. P0：先让生产恢复收敛。
   - 不建议直接反复 requeue `all:2026-03`，否则会再次 timeout 或继续占资源。
   - 应先减少 cost_statistics 重复并发，必要时临时停用兼容 `cost-tax` 对 `cost_statistics` 的消费，只保留专用 `cost-statistics` lane。
   - 对当前 dead-letter 做只读 explain/行数采样后再受控 requeue。
2. P1：修 cost_statistics refresh 边界。
   - 给 `cost_statistics_shard_converged` / `cost_statistics_all_shard` 加 active coalesce。
   - 降低 `cost-statistics` worker `max-events-per-iteration`，避免一次循环长时间不 heartbeat。
   - parent scope 只做轻量聚合，避免任何回退到 workbench 全 JSON。
   - month shard 尽量从结构化 `workbench_rows` 或专用 relation rows 构建，不再读取整组 JSON payload。
3. P1：拆 API read model。
   - cost explorer 首屏读取摘要和分页 rows，不默认返回全量 time/project/expense rows。
   - batch accounting 建立页面专用 read model 或批量查询合同，把 101 SQL 降到固定少量 SQL。
   - App Health 改为读取预聚合 health snapshot 或 bounded summary，目标 p95 < 300ms。
4. P2：worker 可观测性。
   - 长任务中增加阶段心跳，例如 query、parse、publish、parent_wait。
   - App Health 区分 `processing_alive` 与 `stale`，不要把长任务统一显示为异常。
   - 对每个 read model 写 refresh duration、row count、payload size、source scope count。

## 结论

该问题是模块边界内的性能合同不完整，不是单个页面同步按钮问题。当前模块化边界已经存在，但还没有形成性能闭环：read model scope 有边界，worker 有边界，API 有 fresh gate，但高成本投影、重复收敛、长任务心跳和页面读模型没有各自的耗时上限。

建议下一阶段以 `cost_statistics` 为第一阶段改造目标，因为它同时解释截图中的同步中、dead-letter、worker stale 和 cost explorer API 慢。第二阶段治理 `batch-accounting` read model/N+1，第三阶段治理 App Health summary。
