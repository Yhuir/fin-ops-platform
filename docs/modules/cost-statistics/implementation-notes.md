# 成本统计实施决策

## 2026-07-26：改为直接 canonical read

- 保留现有 API、视图、标签规则和导出业务合同。
- 删除 Cost 专属 read model、投影、worker、scope、source version、runtime service 与生命周期入口。
- 每个请求从一个 PostgreSQL `REPEATABLE READ READ ONLY` 快照读取统一事实源。
- 业务计算集中在无 I/O 的 `CostStatisticsPolicy`；repository 只负责读取，route 只负责 HTTP。
- Audit 改为直接 canonical proof，Cost 不再出现在 App Status read-model/worker 诊断中。
- migration `0126` 终止遗留 Cost runtime 行并删除旧 Cost read-model 表。

这是本模块当前唯一读链。历史的 parent/shard、freshness gate、dependency defer、conditional publish 和 Redis cache 设计已经被本决策取代，不再作为实现依据。
