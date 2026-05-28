# AppHealth 与关联台性能治理

## 目标

AppHealth 的轻量健康状态只回答系统是否可用、read model 是否 fresh、worker 是否延迟、队列是否积压。数据盘点、接口 p95/p99、历史 read model 刷新耗时属于运维诊断，不应阻塞 `/api/app-health`。

关联台页面读取必须以 active generation 为版本边界。generation 发布前不暴露 building 数据，发布后 Redis cache key 包含 generation id，因此旧页面缓存会自然失效。

## 指标口径

- 当前健康：由 dirty scopes、active generation consistency、worker lag、队列和 DLQ 决定。
- 最近性能：read model duration 使用最近 15 分钟和 1 小时窗口。
- 历史诊断：全历史 p95/p99 只用于容量和回归分析，不决定当前页面红绿。
- 无样本：显示 unknown，不用 `0 ms` 表示。

全历史 p95 不能作为当前健康状态。一次 full rehydrate 或部署重建可能持续 10-30 秒，这应该记录为历史诊断，而不是让 AppHealth 在 read model 已 fresh 后继续显示异常。

## 关联台热路径

`/api/workbench/groups` 默认页面使用：

1. active generation id
2. `read_model.workbench_generation_stats` 预聚合计数
3. 当前页 `read_model.workbench_groups` 数据
4. 轻量 dirty-scope 状态

带搜索、列筛选、时间筛选、source kind 或 status 的请求仍可走精确 SQL 聚合路径。默认首屏和常用 tab 不应每次 join `workbench_group_rows` 做全量 count。

## Redis

`FIN_OPS_WORKBENCH_GROUPS_REDIS_TTL_SECONDS` 默认 600 秒，范围 60-900 秒。cache key 包含：

- Workbench read model schema version
- active generation id
- scope
- zone
- page/page_size
- filters/search/sort/detail_level

因为 generation id 在 key 中，TTL 可以比之前更长。Redis 不可用时允许走 DB path，但不能返回旧 generation 数据。

## Retention

历史 generation 需要定期清理，避免 `workbench_rows`、`workbench_groups`、`workbench_group_rows` 无限膨胀。保留原则：

- active generation 永不删除。
- 每个 scope 保留最近 N 个非 active generation。
- 保留最近若干天的非 active generation。
- 删除顺序：stats、group_rows、groups、rows、summary、snapshots、generations。
- 清理任务必须先 dry-run。

## PostgreSQL 慢查询

生产需要启用 `pg_stat_statements` 才能做真实慢 SQL 排名：

```sql
alter system set shared_preload_libraries = 'pg_stat_statements';
-- 重启 PostgreSQL 后：
create extension if not exists pg_stat_statements;
select * from pg_stat_statements limit 1;
```

如果 `pg_stat_statements` 未启用，运维面板只能显示 unavailable，不应影响 `/api/app-health`。

## 验证

发布后检查：

- `/health` ready。
- `/api/app-health` p95 低于 150ms。
- `/api/operations/app-health-dashboard` 可加载，但不影响轻量健康状态。
- `/api/workbench/groups?zone=paired&page=1&page_size=50&detail_level=summary` p95 低于 300ms。
- worker lag 小于阈值。
- RabbitMQ queue/DLQ 为 0。
- `read_model.workbench_generation_consistency` 无 active inconsistent。
- Redis workbench groups hit rate 上升。
