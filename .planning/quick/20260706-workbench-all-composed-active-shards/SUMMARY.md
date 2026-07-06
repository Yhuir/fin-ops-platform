# Workbench all composed active shards

日期：2026-07-06

## 目标

- 让普通写路径退出 `workbench:all` 全量 generation，避免 relation 写后由全局 rows/groups/group_rows 重写拖慢强可见性。
- 保持 `month=all` 页面强可见：查询直接组合 active 月度 generation，而不是等待 materialized all。
- 移除旧 freshness 逻辑对 materialized all 的依赖，避免旧 all generation 缺失、为空或 builder 版本落后污染新读路径。

## Grill Me 结论

- 目标如果是 1s 内强可见，`workbench:all` 全量 generation 不能继续在 ordinary write path 上自动触发。
- 正确事实源是 active month shard generation；`workbench-aggregate` 只能保留为显式 rebuild/repair/backfill。
- `all` 查询必须保留旧 all aggregate 的 group identity 语义：可合并 group id 按 case/batch/source 合并，非可合并临时 group 必须带 scope 前缀，避免跨月覆盖。

## Ponytail 决策

- 不新增新的 worker、队列、缓存或依赖。
- 最小代码路径：
  - `WorkbenchReadModelRefreshService` 默认不再在 month shard publish 后 enqueue `workbench:all` aggregate。
  - `PostgresReadModelRepository` 的 `all` summary/groups/rows/cache version 读取 active 月度 generation。
  - materialized all aggregate 旧路径保留为显式维护路径，不参与 ordinary write freshness。

## 验证

- `PYTHONPATH=backend/src:. python3 -m pytest tests/test_workbench_sql_runtime.py -q`
- 190 passed，5 warnings，6 subtests passed。
- `bash scripts/verify.sh lint`
  - All checks passed.
- 生产 release：`workbench-all-composed-final-20260706`
  - `read-model-scope-contract`：`ok=true`、`violation_count=0`、`current_uncovered_outbox_failure_count=0`。
  - 关键接口探测：
    - `workbench_summary_all` 200，fresh，约 156.6ms。
    - `workbench_groups_all_paired` 200，fresh，约 284.3ms。
    - `workbench_groups_all_open` 200，fresh，约 401.2ms。
    - `workbench_groups_all_open_linked_search` 200，fresh，约 329.0ms。
    - `workbench_groups_all_open_column_filter` 200，fresh，约 284.5ms。
  - HTTP SLO：`/tmp/finops-http-slo-workbench-all-composed-final-20260706105050.json`，`status=pass`，37 probes / 111 samples，0 failed，max p95 609.157ms；`workbench_summary_all` p95 151.581ms，`workbench_groups_all_paired` p95 609.157ms。

## 剩余风险

- 仍需部署后用生产写操作验证真实 enqueue-to-visible SLO。
- 本地测试已证明 worker 不再自动投递 all aggregate，但生产上如果存在旧 pending all aggregate，需要通过队列监控确认不会被误当成 ordinary write blocker。
