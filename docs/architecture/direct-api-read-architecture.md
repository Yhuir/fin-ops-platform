# Direct API Read Architecture

日期：2026-06-26
状态：目标架构；代码迁移未完成前，既有 read model 文档仍作为 legacy inventory 和删除清单。

## 决策

`fin-ops-platform` 的页面读取目标改为 direct API：页面通过 API 直接读取 PostgreSQL canonical facts、OA SQL projection、导入事实和业务 repository 组装出的 DTO，不再使用 app 页面级 read model。

这项决策废弃以下设计方向：

- 新增或扩展页面 read model。
- 用 `ReadModelQueryGateway` / freshness gate 证明页面 payload 可读。
- 用 `job.read_model_dirty_scopes`、`*.read_model.refresh` worker 或 `read_model.app_status_readiness` 表示页面数据同步状态。
- 用 `/api/operation-barrier/status` 等待 read model 收敛后释放写操作 overlay。
- 把 Redis/RabbitMQ/read_model schema 当作页面数据事实源。

## 目标读路径

```text
React page
  -> feature API client
  -> Flask route
  -> query/application service
  -> narrow repository
  -> PostgreSQL canonical facts / OA projection / import facts
  -> API DTO
```

约束：

- route 只做 HTTP 参数、权限、session 和错误映射。
- service 负责业务查询语义和 DTO 组装。
- repository 负责 SQL、分页、排序、过滤、聚合和索引友好查询。
- 页面展示 loading、empty、error 和业务状态，不展示 read model freshness 状态。
- API 不返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys`、`refresh_enqueued` 或 operation barrier target。

## 目标写路径

```text
mutation API
  -> command service / UoW
  -> canonical facts + audit
  -> response: status, affected ids/months, version, optional updated DTO
  -> frontend refetch direct GET
```

写成功代表 canonical write 已提交。页面重新 GET 即可看到当前提交后的事实；不再等待 read model worker。

如果仍有外部同步或导入任务未完成，API 应通过真实 background job 状态表达，而不是通过 read model freshness 表达。

## 后台任务边界

保留后台 worker 的条件：

- 外部系统同步，例如 OA 同步。
- 文件、导入、OCR 或大批量处理。
- 受控数据修复、迁移、审计和清理。

不保留的 worker 职责：

- 页面 read model refresh。
- 页面 projection rebuild。
- read model readiness reporting。
- read model SLO smoke 或 repair。

## App Health 目标

App Health 只展示：

- session/auth 可用性。
- PostgreSQL、OA、对象存储、Redis 等依赖可用性。
- 真实后台任务状态。
- worker heartbeat 和 worker mismatch。
- active alerts 和 deployment/runtime guard。

App Health 不再展示页面 read model readiness，不因为页面投影 missing/stale 变黄或变红。

## 性能原则

- 默认使用 direct SQL 查询、分页、过滤下推和必要索引。
- 重查询必须有 `EXPLAIN` 或测试数据下的 p95 证据。
- 不为猜测的性能问题重建 read model。
- 如果某条 direct API 已经被真实数据证明无法达标，优先优化 SQL、索引、分页和查询范围；缓存只能作为最后一步，并且只是 response cache，不是 freshness proof。

## Legacy inventory

以下文档在迁移完成前保留，但不再代表新增设计方向：

- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/modules/read-models/`
- `docs/operations/runtime-worker-governance.md` 中的 read model worker 治理章节
- `.planning/refactors/modular-io-boundaries/` 中围绕 read model 增量投影的旧计划

新的实施计划见 `.planning/refactors/remove-read-models/`。
