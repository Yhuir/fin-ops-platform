# Read Model 退役合同

扫描日期：2026-08-15。

## 当前结论

App 当前运行时 read model 集合为空。所有页面 API 都从 PostgreSQL canonical facts 和
`app.workbench_pair_relations` 的 active 正式关系直接读取；不存在 manifest、freshness gateway、
refresh worker、dirty scope、projection repository、Redis page payload 或前端 refresh polling。

`workbench-matching` 是正式关系计算的领域任务，不是页面读取投影。OA integration mirror/cache 是外部
系统适配层，不是 App read model。`job.outbox_events`、attempt、heartbeat 和 background job 仍是通用
任务基础设施，也不属于 read model。

## 页面读取 I/O

| 边界 | 合同 |
| --- | --- |
| 输入 | 已鉴权 tenant、筛选、排序、分页/keyset cursor 和页面 scope |
| 数据源 | canonical PostgreSQL tables、active canonical relations；OA 原库只经只读 adapter |
| 一致性 | 组合 rows、summary、facets、statistics 的页面查询使用一个短生命周期 `REPEATABLE READ READ ONLY` snapshot |
| 输出 | 页面专属 DTO；不得包含 `read_model_status`、scope/version、`refresh_enqueued`、generation 或 operation barrier target |
| 写后读取 | 写事务完成后最多一次 normal canonical GET；不等待后台投影，不跨页面 fan-out |
| 失败 | repository/schema/contract 缺失时 fail fast；禁止回退旧 projection、进程内 snapshot 或 shadow read |

## 性能合同

- 查询必须 set-based、分页有界、批量 hydration，禁止逐行数据库或外部 I/O。
- 热路径索引由 canonical repository 和 migration 所有；优化以生产 p95/p99 与 query count 证据为准。
- 默认生产验收目标是核心 GET p95 不高于 1000ms、p99 不高于 2000ms；具体页面可以声明更严目标。
- GET 不 enqueue、不轮询、不读 RabbitMQ/Redis，因此耗时只由 HTTP、canonical SQL 和必要适配层组成。
- ETag/304 可用于无变化响应，但不能缓存或掩盖 stale canonical facts。

## 物理退役

Migration `0149_remove_read_model_runtime.sql` 在确认遗留 schema 仅包含已知对象后：

1. 终止历史 `%.read_model.refresh` 非终态事件；
2. 删除历史 projection override 与 tax scope 字段；
3. 删除 `job.read_model_dirty_scopes`；
4. 删除整个 `read_model` schema。

这是 forward-only schema retirement。部署后不得自动切回仍依赖这些对象的旧 release；失败时保持维护状态并
用当前 release 向前修复。发布会精确 stop/disable 未登记 worker，并删除已知旧 Workbench timer/helper/env；
不会删除主数据库或其它业务表。

## 禁止恢复的旧链

- `ReadModel*` gateway/manifest/readiness/scope/freshness service。
- `*.read_model.refresh` producer、handler、queue route、worker/env、repair/backfill/SLO tool。
- `read_model.*` SQL reader/writer、generation、projection table、Redis payload cache。
- App Status/Health 与前端 DTO 中的 read-model summary/scope/freshness 字段。
- operation freshness barrier、兼容 fallback、双读、shadow projection。

允许保留的文字引用仅限历史 migration/checksum 和明确的负向审计。`retired_projection_event_audit` 必须把任何
新产生的 `%.read_model.refresh` 事件视为失败。

## 验收闭环

- `tests/test_read_model_runtime_removal.py` 验证删除面、四个 worker、API/frontend/deploy/migration合同。
- 页面 API、service、repository、frontend interaction 和跨页业务回归全部通过。
- 全仓 active source/deploy scan 不存在旧入口；生产 migration 后 schema/worker/event 负向审计通过。
- 生产 canonical page audit、HTTP p95/p99、health-ready、queue/worker 和可逆写链 smoke 共同形成发布证据。
