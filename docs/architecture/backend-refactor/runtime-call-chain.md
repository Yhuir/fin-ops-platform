# 运行时调用链与优化规则

## 当前完成度

本文档当前定义运行时调用链的分析方法、模板和优先级。它不是最终的逐模块调用链事实清单。

已完成：

- 已使用 CodeGraph 做过一次全局上下文探索。
- 已阅读 `backend/src/fin_ops_platform/app/`、`backend/src/fin_ops_platform/services/`、PostgreSQL migrations、Read Model、Redis/RabbitMQ 相关代码和架构文档入口。
- 已确认系统存在 HTTP、PostgreSQL transaction、outbox、RabbitMQ、Python worker、Read Model generation、Redis cache、SSE/App Health 等动态链路。
- `PF-P001` 已产出 `architecture-inventory.md`，完成全局 API path ownership、文件族归属、外部依赖矩阵和第一批运行时序候选。
- `PF-P002` 已产出 `platform-runtime-boundary-audit.md`，完成 Platform / Ops / Runtime 的第一批代码事实调用链，包括 auth context、DB transaction、outbox/dirty scope、RabbitMQ/worker、App Health/SSE、DB migration/backfill。

未完成：

- 尚未逐模块产出真实 API path -> handler -> service -> repository -> queue/cache/worker/read model 的完整调用链。
- 尚未对 Workbench、Turnover Ledger、Batch Accounting、Bankdetail、Invoices、Tax/Cost/ETC、Search、Imports、Ops 分别画出 Mermaid sequence diagram。
- 尚未给出每条链路的具体优化结论。

下一步：

- 先审查并确认 `PF-P002`。在 PF-P002 verified 前，不生成业务模块重构 prompt。
- PF-P002 verified 后，建议先生成 `PF-P003 - Platform Runtime Boundary Enforcement / Guard Tests`，补强生产 storage backend、legacy snapshot、auth context、transaction boundary 和 Redis/RabbitMQ 直接依赖的机械门禁。
- 模块级函数时序和最终重构计划必须在后续 Micro-JIT prompt 中逐个模块产出，不能一次性写完所有模块详设。

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
- Workbench page read-model SSE 已移除；页面使用 direct API refetch 或 mutation operation projection。

重点看：

- `routes_workbench.py` 到 `workbench_query_service.py`。
- `workbench_read_model_service.py` 和 `workbench_sql_projection.py`。
- 写操作如何触发 `workbench_matching_dirty_scope_service.py`、outbox 和 worker。
- Redis page cache 是否以 active generation 为版本边界。
- `PF-P001` 必须扫描并显式列出 Workbench 全量 service 文件，尤其是 `workbench_candidate_grouping.py`、`workbench_sql_projection.py`、`workbench_query_service.py`、`workbench_free_matching_engine.py`、`workbench_matching_rules.py`、`live_workbench_service.py`、`workbench_exception_case_service.py`、`workbench_special_pair_rule_service.py`、`workbench_matching_orchestrator.py` 等大文件。

PF-P004 已补充 Workbench `query/read-model` 子域事实链路，完整计划见 `workbench-read-model-query-plan.md`：

- `GET /api/workbench/summary` 由 `_handle_api_workbench_summary` 读取 `PostgresReadModelRepository.get_workbench_summary(scope_key)`；missing 或 source_version stale 时 enqueue `workbench.read_model.refresh`，不在请求线程同步 rebuild。
- `GET /api/workbench/groups` 由 `_handle_api_workbench_groups` 读取 refresh status，fresh 时才允许使用 Redis versioned page cache；cache miss 后读取 `get_workbench_groups_page(...)`，底层 pin active generation 并读结构化 `workbench_groups` / `workbench_group_rows`。
- `GET /api/workbench/groups/detail` 由 `_handle_api_workbench_group_detail` 读取 `get_workbench_group_detail(...)`；当前 stale/missing 语义不如 summary/groups 明确，后续必须先补 characterization tests。
- Workbench 后台状态由 App Health、dirty scope、outbox backlog、worker heartbeat、active/building/failed generation 和 consistency 巡检聚合；公开 `/api/workbench/refresh-status` 与 `/api/workbench/events` 已移除。
- 兼容期 `GET /api/workbench` 仍可能在 SQL read model unavailable 时 fallback legacy builder；这是高风险读路径，后续必须先锁定 response contract 再收口。
- Row detail 当前存在 `LiveWorkbenchService`、cached read model、`WorkbenchQueryService` route 多级 fallback；后续不得直接重写，必须先锁定 fallback 顺序、字段完整度和 override 应用顺序。
- Worker refresh 由 `app/worker.py` 在启用 `--enable-workbench-read-model-refresh` 时注册 `workbench.read_model.refresh` handler，`RuntimeQueueRepository.enqueue_read_model_refresh` 同步维护 dirty scope source_version 和 outbox event，`WorkbenchReadModelRefreshService` 调用 `WorkbenchSqlProjectionBuilder` 写 building generation，验证后切 active generation。
- `all` scope 只能从 active month shards 聚合；`YYYY-MM` scope 负责当月 facts 到 rows/groups/summary 的生成。

### Turnover Ledger

- `GET /api/turnover-ledger`
- `GET /api/turnover-ledger?view=grouped`
- `GET /api/turnover-ledger/relations/{relation_id}`
- `GET|PUT /api/turnover-ledger/relations/{relation_id}/extra`
- `POST /api/turnover-ledger/relations/confirm`
- `POST /api/turnover-ledger/relations/{relation_id}/withdraw`
- `POST /api/turnover-ledger/bank-row-tags/batch`
- `GET /api/turnover-ledger/export-preview`
- `GET /api/turnover-ledger/export`

重点看：

- `server.py` 中 `_handle_api_turnover_ledger*` 到 `TurnoverLedgerApiRoutes`、`TurnoverLedgerService`、`TurnoverRelationService`。
- 读路径是否保持 direct `TurnoverLedgerService` payload，不恢复 PostgreSQL `read_model.turnover_ledger_rows`、stale gate 或同步重建。
- confirm/withdraw 是否同事务写 relation、audit、dirty scope 和 derived lifecycle event。
- `turnover_relation_changed` 如何影响 Workbench candidate grouping 和 source version。
- `turnover_ledger_extras` 是否仍存在 legacy full snapshot fallback。

PF-P046 已补充当前运行时序：

```text
GET /api/turnover-ledger?view=grouped
  -> Application._handle_api_turnover_ledger
  -> TurnoverLedgerApiRoutes.list_ledger
  -> TurnoverLedgerQueryService.list_ledger
  -> TurnoverLedgerService.list_grouped_ledger / list_ledger
  -> route facade returns direct grouped payload
```

```text
POST /api/turnover-ledger/relations/confirm
  -> Application._handle_api_turnover_ledger_confirm
  -> _turnover_mutation_session
  -> TurnoverRelationService.rebuild_from_bank_rows
  -> TurnoverLedgerApiRoutes.confirm_relation
  -> TurnoverRelationService.confirm_relation
  -> _after_turnover_relation_mutation
  -> _persist_turnover_relations_best_effort
  -> _invalidate_workbench_after_bank_transaction_categories
  -> direct page reload / downstream lifecycle events
```

PF-P046 风险判断：

- Query service 已移除 SQL read model freshness gate；页面 GET 只走 direct builder。
- Runtime queue 已提供 dirty scope + outbox 同事务 primitive；Turnover 写 handler 尚未把 relation facts/audit 和 dirty/outbox 纳入一个显式 UoW。
- `/api/turnover-ledger/bank-row-tags/batch` 由 Turnover API 写 Bankdetail category facts，必须在后续 tests 中锁定 ownership 和 side effects。

### Batch Accounting

- `GET /api/batch-accounting`
- `POST /api/batch-accounting/submit`
- `POST /api/batch-accounting/{relation_id}/withdraw`

重点看：

- `server.py` 中 `_handle_api_batch_accounting*` 到 `BatchAccountingService`。
- `load_batch_accounting_workbench_payload` 与 Workbench SQL read model 的读取边界。
- submit/withdraw 是否同事务写 relation、audit、dirty scope 和 `batch_accounting_relation_changed`。
- `repair_legacy_case_id_collisions` 保留为 service-level repair capability；app/server 级 `_repair_batch_accounting_relation_case_ids` wrapper 已删除，读请求热路径不得触发 repair。
- Workbench 如何识别 `special_metadata.source == "batch_accounting"` 并投影到候选分组。

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
6. 仍不达标时，回到架构评审重新评估数据模型、read model 粒度、缓存策略和业务口径。

不得直接因为“性能要求高”就引入新语言后端。本轮计划只做 Python 系统内重构和优化。

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
