# 运行时调用链与优化规则

## 为什么必须整理动态调用链

本项目大量关键行为不是简单的 HTTP 调用函数返回，而是：

- HTTP 写请求。
- PostgreSQL transaction。
- audit、dirty scope、outbox。
- RabbitMQ envelope 或 PostgreSQL durable queue。
- Python worker refresh。
- Read Model generation 发布。
- Redis 版本化 cache。
- SSE/App Health 通知前端刷新。

只看静态调用图会漏掉 outbox、worker、read model 和缓存之间的真实时序。因此每个模块重构前必须同时整理静态调用链和动态运行时序。

## 分析工具

### 静态调用链

优先使用 CodeGraph：

- 找 API handler 调用哪些 service。
- 找 usecase/service 调用哪些 repository、queue、cache、adapter。
- 找某个写操作影响哪些 dirty scope 和 read model refresh。
- 评估修改函数的影响半径。

补充使用 `rg`：

- 查 API path 字符串。
- 查 event type、routing key、read model table、Redis key。
- 查测试覆盖和 product spec。

### 动态运行时序

动态时序来自：

- 现有 structured log。
- trace id。
- App Health。
- worker heartbeat。
- outbox backlog。
- RabbitMQ queue/DLQ。
- PostgreSQL read model generation 表。
- Redis hit/miss 指标。
- 测试中 fake repository/fake queue 记录的调用顺序。

## 标准时序模板

### 读请求

```text
HTTP request
  -> auth/session context
  -> route request validation
  -> module query service
  -> Redis versioned cache lookup
  -> PostgreSQL read model query
  -> freshness check
  -> response mapping
  -> structured log / metrics
```

优化检查：

- 是否绕过 read model 同步扫描 facts。
- Redis key 是否包含 generation/source version。
- stale/missing 时是否只 enqueue refresh，不阻塞用户请求。
- 是否存在 N+1 SQL。
- 分页、筛选、排序是否在 SQL/index 层完成。

### 写请求

```text
HTTP request
  -> auth/session context
  -> route validation
  -> module usecase
  -> PostgreSQL transaction begin
      -> write facts
      -> write audit
      -> bump dirty scope / source version
      -> write outbox event
  -> commit
  -> response with refreshing/stale/fresh hint
```

硬约束：

- facts、audit、dirty scope、outbox 必须同事务提交。
- 不允许写 facts 成功但 outbox/dirty scope 丢失。
- 写后读如果 read model 未追上 expected source version，API 返回 refreshing/stale 语义，而不是假装 fresh。

### Worker refresh

```text
outbox/durable queue event
  -> worker claim
  -> load dirty scope and source version
  -> idempotency check
  -> build read model into building generation
  -> validate summary/groups/rows/source_versions
  -> switch building generation to active
  -> mark dirty scope complete
  -> emit health/SSE/cache invalidation signal
```

硬约束：

- worker 按 `(scope_type, scope_key, source_version)` 幂等刷新。
- 旧 source version 不得覆盖新 active generation。
- API 只读 active generation。
- building/failed generation 只用于诊断，不进入用户读路径。

## 需要优先梳理的调用链

### Workbench

- `GET /api/workbench/summary`
- `GET /api/workbench/groups`
- `GET /api/workbench/group-rows`
- pair relation confirm/cancel。
- exception preview/apply/revert。
- `GET /api/workbench/events` SSE。

重点看：

- `routes_workbench.py` 到 `workbench_query_service.py`。
- `workbench_read_model_service.py` 和 `workbench_sql_projection.py`。
- 写操作如何触发 `workbench_matching_dirty_scope_service.py`、outbox 和 worker。
- Redis page cache 是否以 active generation 为版本边界。

### Bankdetail

- 银行流水分页。
- 自动分类规则应用。
- 分类确认/撤销。
- 账户余额 read model。

重点看：

- SQL projection 是否覆盖分页和筛选。
- 标签变更是否只标 dirty scope。
- 是否影响 Workbench read model refresh。

### Invoices / Pending

- 待找发票列表。
- 输入发票使用。
- 输出发票收款。
- OA 附件发票缓存。

重点看：

- pending read model miss/stale 是否同步扫描事实。
- 命令记录、审计、dirty scope 是否同事务。

### Tax / Cost / ETC

- 税金抵扣月度读取。
- 成本统计 explorer。
- ETC 对账导入和匹配。

重点看：

- Redis miss 后是否读 PostgreSQL read model。
- 聚合是否读取一致 active shards。
- 是否存在请求线程内大范围同步重算。

## 优化决策规则

优化顺序必须是：

1. 去掉请求路径的 full snapshot 和同步全量 builder。
2. 修正 SQL 查询、索引、分页和 N+1。
3. 改成 read model / background worker。
4. 增加 Redis 短 TTL、版本化 cache。
5. 通过批处理、并发控制和 worker lag 限流优化。
6. 仍不达标时，才进入 Go Fiber Hot Path Gate。

不得直接因为“性能要求高”就重写为 Go。必须先有指标和调用链证据。

## 输出格式

每个模块必须产出一份调用链记录，至少包含：

- API path。
- handler。
- usecase/service。
- repository/read model。
- external services。
- event/outbox。
- worker。
- Redis keys。
- transaction boundary。
- stale/refreshing 行为。
- 当前瓶颈和优化决定。

建议使用 Mermaid sequence diagram，但文档中的图必须来自代码事实，不得套模板。
