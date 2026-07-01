# 2026-07-01 关联台读取 Load 慢 GSD 全量分析

## 范围

本文件先记录分析阶段，随后追加主控 `/goal` 执行状态。目标是从模块化架构、清晰边界、清晰 I/O、worker 边界和生产性能合同角度，判断关联台读取 Load 慢的真实原因、优化空间、旧链路污染风险和后续执行方案。

截图证据显示 App Health 中 `关联台` 正在同步，运行摘要为 `Read model 1 刷新中 / 0 过期 / 0 缺失`，Queue 为 `0 pending / 1 processing`，数据域中 `关联台`、`all`、`2026-06` 显示同步。这说明当前用户感知的慢至少包含 read model 正在刷新/等待 fresh 的因素，不能只按单个 SQL 慢查询处理。

## 当前首屏读链路

### Frontend Bootstrap

入口：`web/src/pages/ReconciliationWorkbenchPage.tsx` 调用 `fetchWorkbenchInitialPage(...)`。

输入 I/O：

- 输入：当前视图 month，默认 `all`；paired/open 两个 zone 的 query；AbortSignal；progress callback。
- 输出：summary、invoice inventory、OA 状态、paired 首屏 groups、open 首屏 groups、两个 zone 的 page/freshness 信息。

现状：

- 首屏已从旧 `/api/workbench?month=all` 全量读取迁移为 `GET /api/workbench/summary` 加两个 `GET /api/workbench/groups` 分页请求，方向正确。
- 仍存在一个串行点：先等 summary 返回，再并行请求 paired/open groups。
- `WORKBENCH_GROUP_PAGE_SIZE` 为 200，paired/open 首屏各请求 200 个 summary group。数据大时，即使 DB 快，传输、JSON parse 和 React render 仍可能成为 Load 感知瓶颈。
- 旧 `fetchWorkbenchWithProgress(...)` 和 `/api/workbench` full payload 仍存在。当前首屏测试证明主入口不再调用它，但旧链路没有完全删除。

结论：Frontend 模块边界基本清楚，但还不是性能闭环。首屏 I/O 合同仍偏宽，且旧 full endpoint 仍是污染风险。

### HTTP Read API

入口：`WorkbenchReadApiRoutes.summary/groups/refresh_status`。

输入 I/O：

- 输入：month、zone、page、page_size、status、source_kind、search、sort、detail_level、column_filters、time_filters。
- 输出：HTTP status、payload、`read_model_status`、scope、generation/source version 信息。

现状：

- `routes_workbench.py` 已经拥有 summary/groups 的 HTTP 参数校验和映射，边界方向正确。
- `server.py` 仍保留 `/api/workbench/summary`、`/api/workbench/groups` 的路由分发和 wrapper，同时 `_workbench_query_facade()` 在 `server.py` 组装过多依赖。
- `GET /api/workbench` full endpoint 仍走 legacy SQL read provider，是历史兼容链路。

结论：读 API 边界中等清楚，但还没有从 `server.py` 完全抽离；旧 full endpoint 未移除，不能称为完全闭环。

### Query Facade

入口：`WorkbenchQueryFacade.summary(...)`、`WorkbenchQueryFacade.groups(...)`。

输入 I/O：

- 输入：repository、Redis helper、refresh enqueue port、scope normalize、stale reason detector、status metric、refresh status provider、cache key provider。
- 输出：`WorkbenchQueryResult(status_code, payload)`，并在 miss/stale/refreshing 时 enqueue refresh。

现状：

- fresh gate 明确：refreshing/stale/unavailable 不缓存为 fresh。
- groups 读路径会先查 refresh status，再尝试 Redis version/cache，再落到 repository page query。
- 因为每个 zone 请求都要做 freshness/cache/version 判断，首屏 paired/open 两次请求会重复一部分 gate 成本。
- cold cache 时一定落到 repository SQL；如果 worker warmup 未启用，刷新后第一个用户会承担首屏 SQL 成本。

结论：Query Facade 是当前读链路里最清晰的模块之一；优化重点不是推翻 facade，而是收窄它的首屏合同、减少重复 gate、提升 cold-cache 策略。

### Repository / SQL Read Model

入口：`PostgresReadModelRepository.get_workbench_summary(...)`、`get_workbench_groups_page(...)`。

输入 I/O：

- 输入：scope_key、zone、pagination、filter/sort/search、detail_level。
- 输出：summary payload 或 group page payload，携带 active generation、source_versions、read_model_status。

现状风险：

- summary 正常应读 `read_model.workbench_summary`；若 summary payload 缺少 `summary`，会 fallback 到 `read_model.workbench_groups + workbench_group_rows` 聚合计数，再额外读 invoice inventory。这是热路径兜底，生产级应转移到 worker repair 或直接 fail-fast/stale，而不是请求内重算。
- groups page 已有限制 page_size，上限 200，避免无界读取。
- open zone 当前有 ETC linked summary exclusion 规则。该规则会让部分物化统计不可直接复用，容易触发运行时 count / join count。这是首屏 open 区域 cold-cache 的高风险慢点。
- 之前生产 SLO 文档显示 Workbench groups 曾有 p95 约 2.4s，但后续 gzip-aware/稳定采样可降到 274ms 或更低。这说明“稳定 fresh API”不一定慢，慢更可能来自 cold cache、refreshing 状态、响应体传输或特定 filter/zone。

结论：SQL read model 有正确的 active generation 架构，但 repository 文件聚合职责过宽，且热路径仍有 fallback 聚合。性能闭环缺口集中在 summary fallback、open zone 统计和 cold-cache page query。

## Worker 模块化判断

### Workbench Read Model Worker

入口：`workbench.read_model.refresh`，处理器 `WorkbenchReadModelRefreshService.handle_runtime_event(...)`。

输入 I/O：

- 输入：RuntimeQueueEvent，要求 `event_type=workbench.read_model.refresh`、`scope_type=workbench`、`scope_key`。
- 输出：active generation publish、dirty scope complete、必要时 enqueue all aggregate refresh、可选 post-refresh cache warmup。

现状：

- event I/O 清楚，scope 校验明确。
- `all` scope 不是直接粗暴全量重建，而是先 fan-out shard，再 aggregate-only 等 parent shard fresh，这个边界正确。
- post-refresh cache warmer 是可选依赖，默认通过 env 控制；历史上同步 warmup 放在 ack 前热路径会导致 worker ack 超时，所以默认关闭是有原因的。

结论：Workbench read model worker 基本模块化，边界清晰。性能优化要保留其 event/scope contract，不能绕过 durable queue 或 active generation。

### Workbench Relation Worker

入口：`workbench_relation.read_model.refresh`。

输入 I/O：

- 输入：relation dirty scopes。
- 输出：relation/search read model、写操作后的 operation freshness barrier。

现状：

- 和主 workbench read model 分离，符合“写后 relation barrier 不等待全局 workbench all”的设计。
- 这条链路对写操作释放速度很关键，但不是首屏 Load 慢的直接主因。

结论：边界基本清楚，应继续作为写后快速一致性的独立模块保留。

### Workbench Matching Worker

入口：`WorkbenchMatchingWorkerFactory.build_dirty_scope_worker(...)`。

输入 I/O：

- 输入：matching dirty scope、SQL row provider、settings/source version。
- 输出：candidate decisions、relation commands、dirty scope completion。

现状风险：

- 工厂仍通过 `PostgresStateStore` 加载 `WorkbenchPairRelationService.from_snapshot(...)`。
- relation read port 包装的是 pair relation snapshot。
- relation command service 通过 `CallbackWorkbenchRelationRepository(load_snapshot/save_snapshot)` 写回 snapshot，并设置 `require_fresh_relations=False`。
- 这说明 matching worker 没有完全收敛到 PostgreSQL relation repository / command service 的新边界。

结论：matching worker 不是当前首屏读取慢的第一嫌疑，但它是模块化闭环中的最大旧链路污染点。后续重构必须迁移到 repository-backed relation read/write port，并删除 snapshot callback path。

## 真实原因假设

按当前证据，关联台 Load 慢不是单一原因，而是五类问题叠加：

1. 正在刷新导致的等待：截图明确显示 workbench read model 处于 refreshing/processing。此时 API 可能返回 202/refreshing，前端会显示同步态或等待 fresh。
2. cold-cache 首屏 SQL：Redis warmup 默认关闭，刷新后第一个用户请求 paired/open 首屏会打 repository page query。
3. open zone 统计慢点：ETC linked summary exclusion 使 open page count 不一定能直接复用物化 stats，可能执行 count/join count。
4. 首屏 I/O 偏宽：summary 串行在前，paired/open 各 200 groups，传输和 JSON parse/render 可能放大体感。
5. 旧链路未彻底删除：`/api/workbench` full endpoint、row detail live/legacy fallback、matching worker snapshot relation bridge 都还存在，虽然不一定在当前首屏主路径，但会让未来修复被旧逻辑绕过。

## 模块化闭环评分

| 模块 | 边界/I/O 清晰度 | 闭环状态 | 主要缺口 |
| --- | --- | --- | --- |
| Frontend 首屏 bootstrap | 中高 | 未完全闭环 | summary 串行、page_size=200、旧 full fetch 仍存在 |
| HTTP read routes | 中高 | 未完全闭环 | `server.py` wrapper 和依赖组装仍偏重 |
| Query Facade | 高 | 基本闭环 | paired/open 重复 gate，cold-cache 仍落 SQL |
| SQL read repository | 中 | 未闭环 | summary fallback 聚合、open zone runtime count、文件职责过宽 |
| Workbench read-model worker | 高 | 基本闭环 | warmup 策略需改为异步/低优先级，不能回到 ack 热路径 |
| Workbench relation worker | 高 | 基本闭环 | 需继续保护 operation barrier，不等待 all |
| Workbench matching worker | 中低 | 未闭环 | 仍有 state-store snapshot / callback relation repository |
| Row detail | 中 | 未闭环 | live/cache/SQL/legacy fallback 链路过长 |
| Legacy `/api/workbench` | 低 | 应删除 | 旧全量 payload 链路仍存在 |

## 生产级优化方案，不实现

### Phase 0：只读 profiling 先行

必须先区分“fresh API 慢”和“refreshing 等待慢”：

- 采集 `/api/workbench/summary?month=all`、`/api/workbench/groups?month=all&zone=paired&page=1&page_size=200&detail_level=summary`、`zone=open` 的 gzip-aware p50/p95。
- 同轮记录 `read_model_status`、`read_model_version`、response bytes、server duration、DB duration、cache hit/miss。
- 采集 `job.read_model_dirty_scopes`、`job.outbox_events`、worker heartbeat、latest workbench refresh duration。
- 对 paired/open cold-cache SQL 做 `EXPLAIN (ANALYZE, BUFFERS)`，重点看 open zone count 和 group_rows join。

没有这一步，容易把 refreshing/queue 问题误改成 SQL 问题，或把传输/render 问题误改成 worker 问题。

### Phase 1：收窄读模型热路径 I/O

- summary 请求必须只读 materialized summary；缺 summary 时返回 stale/refreshing 并 enqueue repair，不在 API 请求内重算 group_rows。
- open zone 首屏必须有等价的物化 stats，ETC linked summary exclusion 不能迫使请求内做大范围 count/join count。
- 首屏可以设计一个明确的 bootstrap read contract：一次请求返回 summary + paired/open first page 的最小字段，后端内部共享一次 freshness/version gate，减少三次 API 往返和重复 gate。
- 若保留三接口模式，至少让 summary 与 groups 并行，避免 summary 串行阻塞 paired/open。

### Phase 2：缓存和 warmup 重新定界

- 保持 Redis 只能缓存 fresh payload。
- 不恢复同步 warmup 到 worker ack 热路径。
- 引入低优先级 warmup event 或 worker publish 后异步 lane，刷新完成后预热 `all/open/paired/page=1/page_size=200/detail_level=summary`。
- cache version 绑定 active generation id，旧 generation cache 必须自然失效。

### Phase 3：worker 旧链路删除

- matching worker 改为使用 PostgreSQL relation repository backed `relation_read_port` 和 `WorkbenchRelationCommandService`。
- 删除 `CallbackWorkbenchRelationRepository` 在 matching worker 的生产 wiring。
- 删除 `require_fresh_relations=False` 的绕过点，改为明确的 relation read model freshness precondition 或 command UoW contract。
- 保留 workbench_relation operation barrier，不把写操作重新绑回主 workbench all fresh。

### Phase 4：旧读链路删除

- 全量盘点 `/api/workbench` full endpoint、`fetchWorkbenchWithProgress`、`WorkbenchLegacyApiSqlReadProvider` 调用方。
- 所有前端、测试、工具迁移到 summary/groups/bootstrap 后，删除旧 full endpoint 或改成明确的兼容测试入口。
- Row detail 改为 SQL active generation/freshness gate 优先；live/legacy fallback 只能在明确迁移窗口存在，最终删除。

### Phase 5：测试和验收

七类测试中，本次后续实现至少需要覆盖：

- Business core：relation/matching worker 迁移后的候选、确认、撤回、异常决策不变。
- Service layer：query facade cache/fresh gate、worker refresh/warmup、matching relation command。
- API contract：summary/groups/bootstrap fresh/stale/refreshing/invalid filter/permission。
- Read model/cache/worker：summary 不请求内 fallback 重算；open zone stats 不 runtime 大 count；warmup 不进入 ack 热路径。
- Frontend interaction：首屏加载、refreshing/stale/error、重复 reload 去重、page/filter/sort。
- E2E：导入/OA/关系变更 -> dirty scope -> worker -> active generation -> page fresh。
- Regression：旧 `/api/workbench` 删除或迁移后，现有关联台展示、row detail、权限、导出、设置写入口不回归。

生产 smoke 目标：

- fresh cache-hit 首屏 API p95 < 300ms。
- fresh cold-cache 首屏 API p95 < 800ms。
- page bootstrap response gzip 后尽量 < 500KB；若超过，必须继续裁剪 summary group payload。
- workbench dirty scope enqueue-to-fresh p95 < 5s，all aggregate 不阻塞 operation barrier。
- queue drain 无 pending/processing 卡住；App Health 不把旧 failed 覆盖当前 active repair。

## 是否合理，有没有遗漏

需求合理，但要补齐以下遗漏，避免做成只堆代码的优化：

1. 必须先定义“Load 慢”的 SLO：首屏 API、浏览器可交互、read model enqueue-to-fresh、还是写后返回 fresh。
2. 必须区分 fresh 读慢、refreshing 等待慢、网络传输慢和浏览器 render 慢。
3. 必须把 cache hit/miss 分开测，否则平均值没有架构意义。
4. 必须把 open/paired 分开测，open zone 有独立 SQL 风险。
5. 必须纳入 worker matching 旧链路删除，即使它不是首屏 Load 的直接瓶颈。
6. 必须纳入旧 `/api/workbench` 和 row detail legacy fallback 的删除计划，否则旧代码仍可能污染新链路。
7. 必须保留 operation-level `workbench_relation` barrier，不能为了“全局一致”让写操作等待 `workbench:all`。

## 结论

关联台已经具备 read model、query facade、route、worker 的模块化雏形，但还不是生产级闭环。当前最可能的真实 Load 慢原因是 read model 正在刷新叠加 cold-cache 首屏 SQL；稳定 fresh API 曾经能跑到较短耗时，说明优化空间存在且应先用生产只读 profiling 精确切分。

下一轮如果执行，应先做 Phase 0 生产只读 profiling，再按证据选择 Phase 1/2/3 的最小生产级改造；不能直接补一堆前端 loading 或后端 fallback。

## 主控 `/goal` 执行状态

### 本轮已执行

- Phase 0 生产只读 profiling：确认首屏 groups summary page 响应体约 2.2MB，最大膨胀来源是 group `searchable_text`；同时发现生产根分区满盘，Workbench generation/TOAST 膨胀与 `No space left on device` 是 read model 刷新无法收敛的真实阻塞之一。
- Phase 1 读路径热 I/O 收窄：`get_workbench_summary(...)` 改为只读 `read_model.workbench_summary`，缺 materialized summary 返回未完成，不再在 API 请求内 join `workbench_group_rows` 或读取 `app.invoices` 修复；groups `detail_level=summary` 裁剪 search/debug/source/object identity/decision evidence 等重字段。
- Phase 2 旧刷新竞争降低：导入页没有 operation barrier target 时改走 `fetchWorkbenchInitialPage(...)`，不再调用旧 full workbench progress fetch 作为 runtime fallback。
- Phase 2 运维止血：生产执行 journal 限额、一个 bounded 非 active generation 删除批次和普通 `VACUUM (ANALYZE)`；repository/tool retention 默认收紧到 `keep_recent=1`、`keep_days=1`、`limit=500`，删除条件仍只允许 `status <> 'active'`。
- Phase 3 active relation consistency：生产只读样本证明 `active_relation_open_membership` 来自跨月 active relation 被 `month_scope=当前月` 过滤漏读；已将月度 Workbench projection 改为按 active relation `row_ids && 当前月行集合` 读取，并 bump `WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION=2026-07-01-cross-month-active-relation-v1`。

### 当前未闭环项

- 本地代码尚未部署到远程生产，因此生产 p95 和浏览器首屏 smoke 仍未证明。
- 生产 `workbench:all` / `2026-06` 的 `active_relation_open_membership` 代码根因已修复但尚未部署和 worker 重建验证。
- 旧 `/api/workbench` full payload、row detail legacy fallback、matching worker snapshot bridge 仍未删除，只能视为下一轮迁移目标。

### 下一条主控 prompt

```text
/goal 继续闭环关联台 Load 性能和模块化 Phase 3。

目标：
1. 修复生产和代码中的 Workbench active generation consistency failure：active_relation_open_membership，确保 active relation 拥有的 rows 不再被发布到错误 open group，或只出现在允许的 canonical case open group。
2. 保持模块边界：relation fact 只能通过 workbench_relation/command 边界读取，read model projection 只发布 active generation，不允许请求线程或旧 legacy endpoint 修补事实。
3. 修复后部署到 139.155.5.132，并跑生产 smoke：read_model enqueue-to-fresh、/api/workbench/summary p95、paired/open groups page p95、App Health 收敛、队列 drain、根分区空间。
4. 若 smoke 通过，再生成下一条 prompt 处理旧 /api/workbench full payload、row detail legacy fallback、matching worker snapshot bridge 的删除迁移。

约束：
- 先做 GSD 全量分析，读取 docs/architecture/module-boundaries 与 reconciliation-workbench/workbench-relations/runtime-workers boundary-io。
- 不允许手工把 readiness/dirty/outbox 改 fresh；不允许继续盲删大量 read_model generation；所有生产修复先 dry-run 或只读定位。
- 旧代码不能污染新链路；若发现旧路径仍在 runtime 主链路，必须迁移调用点并删除旧逻辑或明确 quarantine。
- 自行测试：至少运行 Workbench SQL runtime 相关测试、relation/projection consistency 测试、前端 Workbench API/interaction 相关测试、git diff --check；部署后跑生产 smoke 并记录耗时。
```
