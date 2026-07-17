---
phase: 04-reconciliation-workbench-improvements
plan: 04
type: execute
status: implementation-verified-deployment-deferred
deployment_status: deferred_by_user
wave: 1
depends_on: []
autonomous: true
requirements:
  - PAGE-04
  - PAGE-05
  - PAGE-06
  - PAR-01
  - PAR-02
  - PAR-03
must_haves:
  truths:
    - 关联台继续复用现有 active month generation，不新增 Query Projection、投影表、投影 worker 或第二套事实源。
    - month=all 只组合 active month generation，并在分页前完成唯一 canonical owner 仲裁；不物化 all generation。
    - 首屏 summary、paired、unpaired 来自同一 PostgreSQL 只读快照和同一 generation-set token。
    - 刷新期间可展示上一版 stable active generation，但必须明确标记 refreshing、禁止写操作，并在新 generation 激活后自动替换。
    - 刷新/过期 generation 禁写同时由前端和 Workbench action API 服务端 precondition 强制，不能只靠按钮状态。
    - 关联台旧 full-payload、旧 row-detail fallback、伪 all-aggregate lane 和 cache warmer 全部从运行链、部署、测试和文档中删除。
    - 变更只优化 Workbench API、Workbench active-generation 查询和 Workbench Redis namespace；为删除旧 full-payload 所需的跨模块改动只允许解除错误依赖，不改变其他页面 read model、DTO、scope 或业务行为。
    - 本次自动执行只完成代码、测试、文档、受控环境性能证据和发布交接；禁止部署、生产 canary、生产性能验证以及任何会把其他 thread 改动带入 release 的 Git 操作。
  artifacts:
    - path: backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
      provides: active-generation 初始页与分页查询的唯一 SQL owner
    - path: backend/src/fin_ops_platform/services/workbench_query_facade.py
      provides: freshness、版本固定、缓存和错误分类边界
    - path: backend/src/fin_ops_platform/app/routes_workbench.py
      provides: Workbench HTTP DTO 与状态码映射
    - path: backend/src/fin_ops_platform/app/server.py
      provides: 删除 legacy provider/assembler 与所有 generic full-payload 依赖组装
    - path: web/src/features/workbench/api.ts
      provides: 单请求首屏和 generation-set token 传播
    - path: web/src/pages/ReconciliationWorkbenchPage.tsx
      provides: refreshing 展示、写入门禁和版本冲突恢复
    - path: web/src/components/imports/ImportWorkflowPage.tsx
      provides: 移除对 Workbench 首屏读取的跨页面刷新探测，只依赖既有 operation barrier targets
  key_links:
    - from: Workbench route
      to: WorkbenchQueryFacade
      via: 一个首屏查询方法；route 不读 SQL、不拼装业务 payload
    - from: WorkbenchQueryFacade
      to: PostgresReadModelRepository
      via: REPEATABLE READ READ ONLY transaction
    - from: Redis page payload
      to: active month generation set
      via: generation-set token + query schema version
    - from: pagination/group detail/row detail
      to: initial response
      via: expected_read_model_version，版本变化返回 409
---

# 关联台高性能链路复审与实施计划

日期：2026-07-16

状态：设计与实施闭环已完成；部署及生产性能验收按用户要求延期

范围：关联台 `/` 页面、`/api/workbench*`、Workbench active generation 查询、Workbench 专属缓存与 worker lane 清理；以及删除旧 full-payload 所必需的窄幅依赖解耦。其他页面业务合同和 read model 不变。

## 0. 本次执行边界与两个闭环

当前 worktree 同时存在其他 thread 的修复。本次主控目标只负责**实施闭环**：完成代码、七类适用测试、长期文档、旧链零引用证明、受控环境 correctness/EXPLAIN/性能回归证据，以及可直接用于统一发布的交接清单。主控必须在每轮编辑和验证前检查 `git status --short`，只修改本计划确认的文件；不得覆盖、删除、暂存或提交其他 thread/用户的改动。目标文件已有不属于本任务的修改时，必须保留并做兼容编辑；无法安全合并时才报告具体阻塞。

本次明确禁止：`deploy-oa.sh`、生产 canary、生产写操作、生产性能 smoke、生产 admin token、queue drain/worker stop、`git add`、`git commit`、`git push`、merge/rebase 和创建 release。受控性能验证可以使用本地或隔离的生产等价数据集，但不能把该结果表述为生产 SLO 已通过。

以后所有 thread 完成并汇总为单一 release candidate 后，再执行**发布闭环**：核对外部 consumer、复跑合并后全量验证、备份、旧 aggregate lane drain、统一部署、canary、生产 SLO/隔离性验证和回滚演练。延后发布是用户明确的协调决策，不是本次实施 goal 的 blocker；本次 goal 可以在实施闭环全部满足后标记完成，但必须输出 `deployment_status: deferred_by_user` 和尚未执行的发布闭环清单。最终功能只有在发布闭环也通过后，才能标记为 production-verified。

### 0.1 最终实施后复审

2026-07-16 的 Prompt 22 全量回归发现的最后遗漏不在生产设计，而在测试合同：部分本地集成测试和浏览器 mock 仍把旧 full-payload/分区首屏当作事实源，写后仍强制断言 `GET /api/workbench/groups`，且 combined initial mock 没有返回分页与 generation 元数据。处理方式是把测试迁到当前 active-generation/combined-initial 合同；没有恢复旧 route、fallback 或第二 payload owner。

最终复审结论仍是：本计划合理且没有需要新增运行时层的遗漏。生产模型保持一个既有 generation 事实源、一个 repository SQL owner、一个 query facade、一个 combined initial API、一个可丢弃 Workbench cache 和一个现有 Workbench worker lane。没有新增 projection、表、索引、worker、事件、依赖、通用 adapter/factory 或跨页面 read model。

实施闭环证据：默认 `month=all` combined initial 固定 7 条数据库语句；受控 60 次样本 p50/p95/p99 为 58.581/70.962/109.974ms，payload 341,319 bytes；Workbench SQL/query/routes 191 passed；前端测试与生产构建通过；全站 E2E 179/179；lint、docs、diff 校验通过；旧运行链在 `backend/src`、`web/src`、`deploy`、`scripts` 中机械零引用；临时性能数据库已删除。全仓后端 4073 个用例只剩 3 个可精确归属其他并行 thread 的失败，Workbench/本 goal 失败为零。

这些证据只能标记为 `implementation-verified`。生产 external consumer access log、合并后全量绿灯、备份、旧 all-lane drain、统一部署、canary、真实基数/并发性能与其他页面 p95 隔离性、监控和回滚仍属于延期的发布闭环，不能提前标记 `production-verified`。

## 1. 复审结论

现有方向合理，但必须按本计划收敛后才是完整闭环：**复用已有 active month generation，重写 Workbench 查询热路径，首屏合并为一次 API 请求，删除仍可能进入运行链的旧代码；不引入新的 projection。**

这不是“保留旧链路再加一层加速”，也不是“新建一套高性能架构”。最终只有一条页面读取链：

```text
ReconciliationWorkbenchPage
  -> Workbench HTTP route
  -> WorkbenchQueryFacade
  -> PostgresReadModelRepository
  -> active month generations
```

Redis 只是该链路在 fresh/stable gate 之后的可丢弃缓存，不是事实源；worker 只继续生产现有 month generation。

### 1.1 复审后确认保留的设计

- 复用现有 generation 原子发布与月分片，不新增 Query Projection。
- `month=all` 组合 active month shards，不新增物化 `all` generation。
- 首屏用一个 API、一个 query facade 方法和一个数据库只读快照返回 summary + 两区各 200 groups。
- 首屏请求继续支持 paired/unpaired 各自已有的搜索、排序和筛选条件；route 复用现有 query 规范化规则，不新增通用查询 DSL。
- 默认首屏可以缓存；任意搜索、筛选、深分页默认不缓存。
- 刷新时展示上一版 stable generation，明确显示 `refreshing`，禁用写操作；新 generation 激活后自动刷新。
- 复用 repository 已有 active-month generation-set version 固定首屏、翻页、group detail 和 row detail 的同一版本，不新增第二套 token 算法。
- 删除旧 full-payload、旧 row-detail fallback、伪 aggregate lane、cache warmer 及其部署/测试/文档残留。

### 1.2 复审后删除的过度设计

本轮明确不做：

- 新 projection、新表、新 generation 类型、新 worker、新事件、新 dirty scope。
- generation schema 改造、全量 rehydrate 或 canonical facts 搬迁。
- 持久化 `logical_group_id`、generated column 或无证据索引。
- 为 summary、paired、unpaired 分别新增 bootstrap 路由；只复用一个 `GET /api/workbench` 首屏入口。
- cache warmer、任意查询结果缓存、永久 feature flag、single-flight。
- keyset pagination、前端虚拟列表、新前端依赖。
- read replica、专属连接池、通用 repository/factory/adapter 抽象。
- 重写 matching worker；当前 matching 已使用 repository + UoW 边界，不属于本次慢查询根因。

这些能力只有在本计划的量化门槛失败且证据指向它们时，才可作为单独变更重新评审，不能预埋。

### 1.3 第三轮 Grill Me 闭环复审

| 追问 | 结论 |
| --- | --- |
| 目标是否可量化 | 第 8 节定义最终生产 SLO；本次保留同用例的受控 before/after 证据，禁止把本地结果冒充生产结论。 |
| 输入/输出和事实源是否唯一 | 输入是现有 Workbench query/freshness/generation set；输出是 initial/groups/detail 既有业务 DTO 的收敛合同；事实源仍只有 active month generation。 |
| 是否影响其他页面 | 只解除其他模块对 full Workbench payload 的错误依赖；其他页面 read model、DTO、scope、事实源和 command 行为都有回归门。 |
| 刷新/版本/写入是否闭环 | 同 snapshot/token、所有后续读取 expected version、前后端 non-fresh 禁写、SSE 激活后原子替换均有测试责任。 |
| 旧链是否可能继续污染 | 第 6 节覆盖入口、调用方、service、repository、worker、cache、deploy/env、测试和当前事实文档，并要求机械零引用。 |
| 是否有无必要的新层 | 没有新 projection/table/worker/event/adapter/dependency；最终 runtime owner 数量不增加，删除量大于新增量。 |
| 测试与失败恢复是否完整 | 七类测试、Redis/timeout/version/refreshing/权限/其他页面回归均有门；生产回滚以完整 release bundle 为单位，不保留 runtime fallback。 |
| 多 thread 与发布是否安全 | 本次只做实施闭环，禁止 Git 打包、部署和生产性能操作；统一 release candidate 后再完成 consumer、drain、canary、SLO 和回滚闭环。 |

结论：修正“当前实施完成”和“统一发布完成”的边界后，没有剩余的已知设计遗漏。该拆分不增加运行时复杂度，只防止主控越权部署或错误宣称 production-passed。

## 2. 报错原因与性能根因

截图中的错误是 Workbench SQL read model 查询超过 statement timeout。当前错误映射把它描述成“刷新后重试”，但 timeout 并不等于 generation 正在刷新；当 active generation 本身正常时，刷新不是正确补救动作。

已确认的主要慢点是 `month=all` 查询路径，而不是 generation 生产：

1. `all` 没有物化 generation。repository 明确禁止保存 `scope_key=all`；所谓 all refresh 只读取当前状态，没有生成页面数据。
2. all-scope SQL 每次组合全部 active month generations，再计算逻辑 group id、窗口排序、min/max 和 `string_agg(searchable_text)`，最后才分页。
3. 选出 group 后仍会加载过多 member payload，首屏预览承担了详情读取成本。
4. 前端首屏先串行等待 summary，再并行请求 paired/unpaired；多个请求不在同一数据库快照，增加延迟，也可能混入不同 generation 版本。
5. page-facing refresh status 查询混入 worker heartbeat、outbox backlog、consistency failure 等运维诊断，首屏为不需要的证据付费。
6. 缓存 warmer 默认关闭且形成额外运行边界；即使开启，也不能修复 cold path，而且会增加刷新后的同步负担。

历史生产证据显示：summary 约 160–209ms，单月 paired/unpaired 约 433–693ms，而 all-scope paired/unpaired 约 7–11s，并出现约 10s 的 timeout。优化重点因此必须是 all-scope cold query，而不是提高 timeout 或增加重试。

## 3. 必须保护的边界与 I/O

| 模块 | 允许输入 | 允许输出 | 禁止行为 |
| --- | --- | --- | --- |
| Workbench route | HTTP 参数、session/权限、facade 返回值 | HTTP DTO、明确状态码 | SQL、缓存操作、业务分组、旧 fallback |
| `WorkbenchQueryFacade` | 规范化 query、expected version、repository、Workbench cache | freshness/context、页面 DTO、领域化 query error | 直接 SQL、构造 Flask response、写 read model |
| Workbench read repository | transaction、规范化 query、active generation metadata | summary、group page、detail | HTTP、Redis、权限、刷新 enqueue |
| Existing generation worker | durable Workbench month scope | 完整 month generation 原子激活、既有下游 fan-out | 新投影、all 数据物化、同步 cache warming |
| Workbench Redis cache | fresh/stable gate 后的默认首屏 payload | 可丢弃的 versioned payload | 事实源、freshness 决策、跨页面 key |
| Workbench frontend | API DTO、SSE/domain refresh signal | 页面状态、用户命令 | 本地关系推断、伪造 fresh、跨版本拼页 |

隔离约束：

- 不修改其他页面的 read model manifest、projection schema、scope policy、repository query 或 Redis namespace。
- 关系写入仍只产生当前受影响 month scopes；保留 month generation 发布后的 `cost_statistics` 既有 fan-out。
- 不改变 OA、银行、发票 canonical facts，也不改变 `workbench_relation` shared read model。
- 所有缓存 key 必须在 Workbench namespace 内，并带 generation-set token 与 Workbench query schema version。

现有代码有一个必须先拆除的跨页面耦合：`ImportWorkflowPage.refreshWorkbenchStatus(...)` 在后端没有返回 operation barrier targets 时会调用 `fetchWorkbenchInitialPage(...)`，为了一次“刷新探测”加载完整关联台首屏。该调用既浪费 I/O，也会让关联台 API 改动影响导入页。最小修复是：有 targets 时继续调用既有 `waitForOperationFreshness(...)`；没有 targets 表示该导入响应没有声明等待目标，直接完成导入反馈，不读取 Workbench 页面。若业务确实要求等待 Workbench，责任在后端返回明确 targets，不能靠 GET 页面数据猜测完成状态。

## 4. 目标查询链路

### 4.1 首屏合同

复用 `GET /api/workbench?month=all` 作为唯一首屏入口，返回当前 DTO 语义下的：

- page-facing read model status；
- generation-set token / read model version；
- 当前已有 OA status；
- summary；
- 当前已有 invoice inventory；
- paired 首 200 groups 与分页信息；
- unpaired 首 200 groups 与分页信息。

首屏请求同时接收 paired/unpaired 各自当前的 `WorkbenchGroupsPageQuery`。传输层只允许两个稳定 JSON object 参数 `paired_query`、`unpaired_query`，字段白名单与 `/groups` 已有 `search/search_mode/search_by_pane/status/source_kind/sort/column_filters/time_filters` 完全相同；route 复用现有 JSON normalize 与字段校验，未知字段或非法值返回 400。page 固定为 1、page size 固定为 200、detail level 固定为 summary，不能由客户端放大。

前端不再执行“summary 后 paired/unpaired”三请求编排。`/groups` 继续用于后续分页；筛选条件变化或 generation 切换时仍调用同一个首屏入口，从而在一个快照中同时得到 summary 和两区第一页。group detail 与 row detail 继续保持窄接口。

旧 `/api/workbench` full-payload 合同不能在新链路旁长期保留。仓库内 client inventory 与迁移在本次实施闭环完成；生产 access log 的外部 consumer 核查属于统一发布前置门：

- 无外部 consumer：原路由直接替换为新首屏合同。
- 有外部 consumer：先迁移明确 consumer，再替换；不得保留隐藏 fallback 或双实现。
- `/api/workbench/summary` 在确认无外部 consumer 后删除，因为首屏已包含 summary。

生产 access log 至少核查 35 天（日志保留不足时取全部窗口），以覆盖一个月结周期。这项核查是发布前置门，不是引入兼容层的理由；如果发布时发现外部 consumer，先迁移明确 owner，再部署已经删除旧合同的新 release。本次不得为等待该门禁保留隐藏 fallback 或双实现。

仓库内已知 consumer 不等待生产日志结论，必须随合同迁移：`scripts/check-local-runtime.sh`、`operations_dashboard.py`、`validate_workbench_generation_convergence.py`、`http_slo_probe.py`、前端 api mock/组件测试，以及仍用旧 full `/api/workbench` 读取结果的业务测试。`/groups` 仍是合法分页/定向探测接口，不因首屏合并而删除。

### 4.2 数据库 cold path

cache miss 使用已有 `PostgresConnection.transaction()` 开启：

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '2s';
```

2 秒只是一条 Workbench transaction-local 资源保护线，不是性能目标，也不修改其他页面连接设置；正常 cold p99 仍必须 ≤800ms，发布验收中 timeout 必须为零。超时直接走明确 `query_timeout` 503，不自动重试、不 enqueue refresh，避免一次请求重复放大数据库负载。

同一 transaction 内执行少量、职责单一、可独立解释的查询；不拼成一个巨型 SQL：

1. 读取 active month generation set 与轻量 page freshness context。
2. 基于统一 canonical-owner 集合计算 exact summary/counts。
3. 查询 paired page group metadata。
4. 查询 unpaired page group metadata。
5. 一次批量读取这 400 个 group 的有限 preview rows。

目标是约 5 个简单 indexed statements；最终 statement 数由 `EXPLAIN (ANALYZE, BUFFERS)` 和测试证明，而不是为了凑数字牺牲清晰度。

### 4.3 canonical-owner 语义只能有一份

all-scope 必须先从每个 active month generation 中选出唯一 canonical owner，再进行 summary、zone 计数、搜索、排序和分页。summary 与两区 page 必须复用同一 repository 内部语义构造，不得各写一套近似 SQL。

原因：跨月 relation 的完整成员会补入多个 month generation。当前简单累加月 summary 可能重复计算跨月 relation/member；如果 summary 与 page 使用不同 owner 规则，即使查询更快也不可信。

验收不变量：

- paired = active relation owners；
- unpaired = canonical facts - active relation owners；
- 两区不相交，union 完整；
- cross-month relation 只计一次，但 group detail 仍返回完整成员；
- summary counts 与相同过滤条件下 page exact counts 一致；
- 未知/重复 owner fail fast，不以任意月份静默胜出。

### 4.4 首屏只取预览，不承担详情成本

- group page 只返回现有 group metadata、summary row 与 UI 首屏确实展示的有限 preview rows。
- 完整 collapsed/member rows 继续由 group detail / row detail 按需读取。
- 不改变已发布 generation 的 payload schema；优化发生在读取与 DTO 物化阶段。
- 不为首屏重新生成 generation，不把 JSON 拆到新表。

## 5. freshness、缓存与版本一致性

### 5.1 page-facing context 与运维诊断分离

复用现有方法边界，把 `get_workbench_groups_freshness_status(...)` 收敛为页面所需的轻量查询：

- active generation-set token；
- dirty/failed/refreshing 状态；
- generated_at / source version 必要字段。

`get_workbench_refresh_status(...)` 继续服务 App Health/System Audit，保留 heartbeat、outbox backlog、consistency failures 等重诊断。页面首屏与 SSE 不再查询完整运维证据。

### 5.2 generation-set token

不新增 token builder。`PostgresReadModelRepository._workbench_active_month_generation_version(executor)` 已经按 active month generation、source versions 和稳定排序生成 `workbench:all:active-generation-set:*` version，并且可接收 transaction executor；它是 all-scope version 的唯一 owner。Workbench query/cache schema 继续使用现有 `WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION` / cache schema version，不另拼一份语义版本。

现有 version 必须贯穿：

- initial response；
- cache key 与 cache payload；
- `/groups` 搜索/筛选/分页；
- group detail；
- row detail。

后续请求携带 `expected_read_model_version`。服务端发现 active set 已变化时返回 409；前端清除旧列表/选择态，重新加载首屏。禁止把旧页与新 generation 拼在同一 UI。

首屏/后台 reload 本身会直接返回最新 version，不一定先经历 409。`applyWorkbenchInitialPageResult(...)` 应比较当前与新 version：version 变化时，在应用新数据的同一状态转换中清空 selection source、已选 group/row、详情 drawer 数据和旧 pagination；version 未变化时才允许保留当前选择。禁止新列表配旧 selection。

当前 group detail 已具备该能力；本次补齐 groups page、load-more、search/filter 和 row detail。

### 5.3 最小缓存策略

只缓存低基数的默认首屏：标准排序、无搜索、无额外筛选、paired/unpaired 各 200 groups。

cache key 包含：tenant、month、generation-set token、query schema version 和固定默认首屏参数。读取时 facade 先取得轻量 page context，再命中同版本 payload。Redis 异常或 miss 直接走数据库 cold path，不改变结果与状态。

现有 `workbench_groups_page_cache.py` 已拥有稳定 JSON 规范化、version hash、TTL 和 schema version。保留这些函数，只删除 warmer/env；由于现有 key builder 只描述单个 zone，允许增加一个纯函数构造 combined initial-page key，不增加 cache class、registry 或 invalidation service。非默认 paired/unpaired query 不缓存，因此该 key 不需要承载任意筛选组合。

不缓存任意搜索/筛选/深分页，不保留异步/同步 warmer，不新增 cache invalidation event：month generation 原子激活会自然改变 token，旧 key 自动失效并由 TTL 回收。

### 5.4 刷新时的可信行为

- dirty/processing 且旧 active generation 可用：返回旧 active payload + `refreshing`，页面展示明确 banner，所有 relation mutation 按钮禁用。
- 新 month generation 原子激活：generation-set token 变化；SSE/domain refresh signal 触发首屏重载。
- failed/unavailable 或无 stable active generation：不伪装 fresh，页面进入明确错误/不可用状态并禁写。
- query timeout：返回分类明确的 `query_timeout` 503；不得声称已 enqueue refresh，也不得把“刷新”描述成必然修复。

“刷新期间禁写”必须双层执行：前端禁用所有会修改 relation/override/exception 的 Workbench 控件；对应 Workbench action 请求必须携带 `expected_read_model_version`，并在进入 write facade 前复用 `WorkbenchQueryFacade` 的轻量 page context 做服务端 precondition。缺版本返回 400，token 不一致返回现有 `workbench_read_model_version_conflict` 409，refreshing/stale 返回 `workbench_read_model_not_fresh` 409，failed/unavailable 返回 503。该 gate 只放在 Workbench action API，不下沉到共享 `WorkbenchRelationCommandService`，避免影响其他页面；command service 原有 canonical relation/version transaction checks 继续负责最终并发正确性。

## 6. 必须删除的旧代码与污染路径

删除不是可选清理项。实施时先做 whole-repo symbol/text scan，按“入口 → 调用方 → service → repository → worker → deploy → test → docs”逐项清零。

### 6.1 旧 full-payload 链

删除：

- `services/workbench_legacy_api_sql_read_provider.py`；
- `services/workbench_api_payload_assembler.py`；
- `services/workbench_raw_payload_assembler.py` 以及只服务 on-demand legacy page build 的 server wiring；
- `server.py` 中对应 import、构造、字段和 `_build_api_workbench_payload` wiring；
- `_get_or_build_workbench_read_model`、`_get_persisted_workbench_read_model`、`_can_use_legacy_workbench_read_model_without_source_versions`、`_build_raw_workbench_payload`、`_workbench_raw_payload_assembler`；
- repository 的 `get_workbench_view`、`_load_active_workbench_snapshot_view`、`_load_all_workbench_view`、`_load_all_workbench_rows_page_view`、`_load_workbench_rows_page` 等仅服务旧合同的方法；
- `read_model_manifest.py` 对 `get_workbench_view` 的旧 repository contract；
- 仅验证 legacy provider/assembler/get-view 实现的测试；
- 只用于“隔离但保留旧链”的 architecture guard，改为“旧符号不得存在”的删除 guard。

前端旧的 `fetchWorkbenchWithProgress` 已经不存在，不把已删除代码重复列为工作量。当前 `fetchWorkbenchInitialPage` 保留函数边界，但内部改成一个 HTTP 请求。

`_build_api_workbench_payload` 不是只被旧 HTTP 使用。当前 whole-repo 调用方必须先按下表解耦，之后才能删除 assembler；禁止直接删依赖导致其他页面降级，也禁止为了保留它而新增兼容 facade。

| 当前调用方 | 最小迁移 | 隔离验收 |
| --- | --- | --- |
| `GET /api/workbench` | 改由 `WorkbenchQueryFacade.initial_page(...)` 返回 active-generation 首屏 | 不再触发 legacy provider/assembler/live fallback |
| `CostStatisticsService` server 构造 | 当前生产代码只有构造、没有运行时读取调用；先以 symbol guard 锁定，再删除无效构造/import。若全仓 non-test 引用仍为零，删除该 legacy service 与只测试它的用例；现有 `CostStatisticsQueryService`、SQL read model 和 month publish fan-out 不动 | 成本统计 API/worker/read model DTO、scope、数据和性能不变 |
| `SearchService.grouped_workbench_loader` | 在现有 Workbench repository 增加一个窄查询方法，只返回搜索索引现已消费的 active-generation row/zone/project context；直接注入 callable，不新增 port class/read model/cache。保留 SearchService 当前 cache/clear 行为 | 搜索结果、排序、status/project filter 与缓存失效 characterization 完全相同 |
| ignored rows 非 SQL fallback | `list_workbench_ignored_rows` 已是生产 SQL owner；支持的运行时要求该 repository 方法存在并 fail fast，删除回退 `_get_or_build_workbench_read_model` 的分支 | ignored rows API/Search 输入 shape 不变，不触发 raw/full page build |
| `BatchAccountingService` generic fallback | 生产 SQL 路径已拥有 `load_batch_accounting_workbench_payload`、submit/submitted 窄 loaders；把它们设为该路径的必需依赖并 fail fast，删除 generic full-payload fallback | 批量账务 list/submit/withdraw DTO 和 relation command 行为不变 |
| `WorkbenchWriteFacade.ignore_row` | 改用已注入的单 row canonical/live resolver 和现有 stale conflict 校验，不为一个 row 构建整页 payload | ignore-row 的权限、版本冲突、audit、affected scopes 不变 |
| settings reset 的 `_build_api_workbench_payload("all")` | 该 read 不能充当 rebuild。确认既有 derived-data lifecycle 已投递 Workbench targets 后删除；如 targets 缺失，只补入现有 lifecycle target envelope并等待既有 barrier/job，不新增 refresh 路径 | reset 完成语义由 durable target 收敛证明，不靠页面 GET 成功猜测 |
| 运维脚本与探针 | summary/首屏探针改用新首屏合同；需要分页 SLO 的探针继续用 `/groups` | local runtime、convergence、operations dashboard、HTTP SLO 仍有等价或更强证据 |

业务行为测试不能因旧 route 删除而整批删除。`test_workbench_v2_api.py` 等使用旧 full payload 进行业务断言的用例，应迁移到 initial/groups/detail 或 command result；只有测试已删除实现细节的 provider/assembler/get-view 用例才删除。迁移后覆盖数不得下降。

`WorkbenchReadModelService` 不能因名称相似被整类删除：当前 Bank Batch、No-OA Batch、settings reset 和多个 source-version provider 仍使用其 snapshot/version 能力。为保护其他模块，本计划只删除它在 Workbench 页面 on-demand raw/full read path 中的职责，并增加 guard 证明 route/facade/repository 不再依赖它；把共享 snapshot-version 用户迁走属于另一项跨模块重构，不在本次预埋。

### 6.2 row detail 多级 fallback 链

当前 row detail 仍可能依次尝试 ETC/live service/cache/query facade/opaque OA/legacy route。目标链必须收敛为：

```text
row detail route -> WorkbenchQueryFacade -> active generation repository
```

删除 route/server 中 ETC/live/cached/legacy/opaque fallback 与依赖注入。ETC summary/detail 已属于 generation rows，公开详情不得再特殊拼装。

当前 `_resolve_rows_for_amount_check(...)` 和 `_confirm_link_selected_oa_source_ids(...)` 会调用 `_get_api_workbench_row_detail_payload(...)` 补齐写命令输入，这使 command 反向依赖 HTTP read fallback。迁移时直接复用已存在的 canonical row resolver / `_resolve_live_rows_direct` 和 relation fact repository，按 row ids 批量解析金额与 OA source ids；不新建 resolver class，不从页面 DTO 提取命令事实。公开 row detail 删除后，这两个 helper 也不得保留调用。

### 6.3 伪 `workbench-aggregate` lane

代码事实表明 `all` 不可物化，现有 all refresh 只读取状态。因此删除：

- runtime registry 的 `workbench-aggregate` instance；
- deploy env example 与 ensure-runtime-workers 迁移逻辑；
- `enqueue_workbench_all_aggregate_refresh`；
- refresh service 中 `aggregate_only`、`publish_all_aggregate` 和 month publish 后 all enqueue 分支；
- builder 的 `refresh_workbench_all_scope_from_active_shards`；
- relation repository、rehydrate script、测试和文档中的 aggregate-only 调用/声明。

同时把普通 `workbench` worker 改为可 claim `scope_key=all` 的 fan-out command；`all` 只负责规范化并投递 month scopes，不写页面数据。month generation 激活本身就是 all query token 变化，不需要第二次发布。

统一部署切换前必须用现有 queue ops 统计 all-lane pending/processing/failed 事件；在短暂静默旧 producer 后，让旧 worker/既有重试流程 drain 到零，再一次性切换 registry 并 stop/disable aggregate worker。该操作只记录进发布交接，本次主控禁止实际执行。不要为一次迁移新增 event rewrite 脚本、兼容 handler 或长期分支。

### 6.4 cache warmer

删除 `WorkbenchGroupsPageCacheWarmer`、enable env、worker `post_refresh_warmer` wiring 及其测试/文档。默认首屏采用 request fill；刷新发布不承担 Redis 可用性和缓存生成延迟。

### 6.5 删除完成的机械证明

至少设置以下 guard：

- 旧 provider/API assembler/raw payload assembler/on-demand get-or-build/aggregate/warmer 类名、模块名和 env 名在运行代码、deploy 与当前事实/运维文档中为零引用；历史 implementation notes/migration state log 可保留带日期的历史记录，guard 必须排除这些归档而不是改写历史。
- production route 不存在 legacy fallback/fail-open 分支；
- main Workbench worker 可处理 all fan-out，registry/deploy/App Health 不再登记 aggregate instance；
- `/api/workbench` 只有一个 payload owner；
- row detail 只有 active generation query owner。

## 7. 分步实施顺序

### Step 0：冻结受控基线与调用方清单

1. 在本地或隔离的生产等价数据规模、200 groups/zone、混合负载下记录端到端与每 statement p50/p95/p99；本次不调用生产 API、不使用生产 token。
2. 保存当前慢查询 `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)`、返回行数、payload bytes、浏览器 parse/commit/layout。
3. 对 `/api/workbench` 与 `/api/workbench/summary` 做仓库内 client inventory；若已有无需生产操作的 access-log 证据，可以附入报告，否则把 35 天生产 access-log 核查作为不可跳过的统一发布门。
4. 对旧类名、route helper、repository 方法、`_build_api_workbench_payload` 的全部内部调用方、worker instance、env、scripts/tools、tests、docs 做 whole-repo inventory；仓库内已知 consumer 必须在本次迁移，不等待生产 access log。

通过条件：受控基线可复现，仓库内 consumer 全部有迁移结论，旧代码清单没有未知内部调用方；生产 external consumer 核查已作为发布门写入交接，不得被误报为已经完成。

### Step 1：建立可信的 repository cold path

1. 抽出 repository 内唯一 canonical-owner SQL 语义，供 exact summary 与两区 page 复用。
2. 在一个已有 transaction 中读取 generation context、summary、两区 page 和 preview rows。
3. 删除 all-scope 全表 window/string aggregation 后分页的实现。
4. 只物化首屏需要的 preview；detail 保持窄查。
5. 复用现有 request metrics/structured logging 记录查询阶段耗时、statement 数、扫描/返回行数、cache outcome、payload bytes、状态和 timeout 分类；不记录业务 payload 或敏感字段，不新增监控平台。
6. 用跨月 relation、重复 typed identity、空 scope、400-group page 做 correctness 与 EXPLAIN 验证。

通过条件：cold path 结果与独立 canonical expected set 完全一致，且不依赖 Redis。

### Step 2：收敛 facade、API 与前端

1. facade 增加单一 initial-page 方法，完成参数规范化、轻量 freshness、cache 和错误分类。
2. `GET /api/workbench` 接收两区现有 query object 并返回同快照首屏；迁移仓库内 consumer 后删除旧合同和冗余 summary route。统一部署前再完成生产 external consumer 门禁，不在代码里保留兼容路径。
3. 先解除 `ImportWorkflowPage` 对 `fetchWorkbenchInitialPage` 的调用：只等待后端返回的 operation barrier targets；无 targets 不读取关联台。随后把 `fetchWorkbenchInitialPage` 改为单请求。
4. 将 repository 已有 generation-set version 传播到 load-more、search/filter、group detail、row detail；409 时原子重载。initial/background reload 直接返回不同 version 时也必须在应用 payload 前原子清空旧 selection/detail/pagination。
5. 增加显式 refreshing banner，把 refreshing/stale/failed/unavailable/version-mismatch 纳入 `canWriteWorkbench` 门禁；所有 relation/override/exception action 同时传 expected version，后端 Workbench action gate 使用同一轻量 context fail closed。

通过条件：首屏只有一次业务 API；跨版本 page/detail 不会混合；刷新期间旧数据明确可辨且无写入口。

### Step 3：加入最小缓存

1. 复用现有 Workbench cache 的 stable normalization/version hash/schema/TTL，只为 combined 默认首屏增加一个纯 key 函数；不增加 cache class。
2. key/payload 同时携带 generation-set token 和 query schema version。
3. Redis miss/error 走相同 cold path；不 enqueue refresh，不改变 HTTP 语义。
4. 删除 warmer 与其配置/wiring。

通过条件：cache hit、miss、Redis down 三条路径 DTO 等价，只有 latency/cached 标记不同。

### Step 4：删除全部旧链和 aggregate lane

1. 先按第 6.1 节迁移 Search、Batch Accounting、Workbench ignore-row、settings reset、scripts/tools 等实际调用方；用 characterization/regression 证明其他页面输出不变。
2. 再删除 provider/assembler/get-view、无运行时用途的 legacy CostStatisticsService wiring、旧测试与 manifest contract；不得颠倒顺序。
3. main Workbench worker 接管 all fan-out command；普通 relation 写仍只 enqueue affected months。
4. 保留 cost-statistics month publish fan-out，并用回归测试锁定。
5. whole-repo 扫描与 architecture guard 证明无旧符号、无 fallback、无双 payload owner、无其他页面 generic full-payload 依赖。

通过条件：删除 guard、registry/deploy contract、queue fan-out 和全部回归测试通过。

### Step 5：受控性能证据与发布交接

1. 在与 Step 0 相同环境复测 cold/hot、Redis down、refreshing、generation switch 和混合负载。
2. 对相同数据和负载给出 before/after p50/p95/p99、statement 数、扫描/返回行数、buffers、payload 和浏览器阶段；运行 Redis down 与其他页面隔离回归。
3. 在本地/测试 worker 环境验证新 active generation 发布后 SSE 自动替换，以及 main Workbench worker 的 `all` fan-out；不得操作生产 queue 或 worker。
4. 生成统一发布交接：external consumer 门、all-lane drain 命令与观察项、release bundle 顺序、canary 指标、回滚步骤和生产性能用例。本次不执行这些生产步骤。

通过条件：correctness、定向/全量测试、受控性能与隔离门槛通过，旧运行符号/配置零引用，发布交接完整。生产 SLO、无旧 worker/旧 route 流量和回滚演练保留到统一发布闭环验收。

## 8. 性能与可信度验收门槛

统一场景：每区 200 groups、生产等价数据规模、混合业务负载；报告同时给出样本数、p50/p95/p99、DB statements、rows scanned/returned、buffers、payload bytes 和浏览器耗时。下表是最终生产验收门槛；本次实施必须用受控环境验证同一用例和明显回归，但只有统一部署后的生产测量才可以把这些门槛标记为 production-passed。

| 指标 | 门槛 |
| --- | --- |
| 默认首屏 hot p95 / p99 | ≤ 200ms / ≤ 400ms |
| Redis unavailable 或 DB cold p95 / p99 | ≤ 500ms / ≤ 800ms |
| 搜索、筛选、后续分页 p95 / p99 | ≤ 500ms / ≤ 800ms |
| group detail / row detail p95 / p99 | ≤ 200ms / ≤ 400ms |
| page-facing freshness/status p95 / p99 | ≤ 100ms / ≤ 200ms |
| relation write → 新 active generation 可见 p95 / p99 | ≤ 1s / ≤ 2s |
| Workbench query statement timeout | 0 |
| 其他页面 p95 回归 | ≤ 5%，且数据/状态合同不变 |
| 初始压缩 payload | ≤ 500KB |
| 400 groups 的 JSON parse + React commit + layout p95 | ≤ 150ms |
| 同一页面跨 generation 混读 | 0 |
| refreshing/stale 状态下 relation mutation | 0 |

不能通过提高 statement timeout、减少返回正确数据、跳过 freshness 或预热测试环境来达标。

### 8.1 有证据才允许的升级路径

1. 如果重写后的 cold p95 仍 >500ms，先以 EXPLAIN 证明具体表达式/连接为瓶颈，只增加一个 Workbench-only expression/composite index，并单独验证写放大与其他页面回归。
2. 如果浏览器阶段超标，先使用原生 `content-visibility: auto`；只有实际 profiling 仍失败才另行评审虚拟列表。
3. 只有经过 query rewrite + 受证据支持的单一索引仍无法达标，才向用户重新提出 projection 方案；本计划内禁止自行引入。
4. 只有深分页实测超标才评审 keyset；只有并发 cold miss 证明 dogpile 才评审 single-flight。

### 8.2 可观测性与告警

复用现有 request/worker/DB 指标，不建立新的 telemetry 服务。发布报告和持续监控至少能按 endpoint、zone、cache outcome、freshness status 区分 latency，并观察 statement timeout、409 version conflict、503 query timeout、Redis error、DB pool wait 和 payload bytes。

告警只对可行动问题设置：statement timeout 非零、首屏 SLO 连续超标、refreshing 超过既有 worker SLO、failed/unavailable、其他页面 p95 回归超过 5%。generation token、tenant 等只记录不可逆或既有安全标识，禁止把 row payload、票据、金额明细写入性能日志。

## 9. 七类测试闭环

七类均适用，不以单一 happy-path 性能测试代替。

1. **业务核心单元测试**
   - cross-month canonical owner、relation/member 去重、paired/unpaired 完整分区。
   - 空 scope、重复 typed identity、非法 owner、collapsed summary/member 边界。
   - exact summary 与相同 filter 的 group counts 一致。

2. **Service 层测试**
   - initial-page orchestration、单一只读 snapshot、cache hit/miss/Redis failure。
   - refreshing/stale/failed/fresh 状态和 generation mismatch。
   - query timeout 返回 `query_timeout`，且不伪造 refresh enqueue。
   - amount check 与 OA source-id expansion 只走 canonical command resolver，批量结果与旧行为一致且不调用 HTTP row-detail helper。

3. **API 合同测试**
   - initial success shape、paired/unpaired query 白名单与非法 JSON/字段/month/filter/type、权限、503、409。
   - groups page、group detail、row detail 都校验 expected version。
   - Workbench relation/override/exception action 缺 expected version 为 400、版本冲突为 409、refreshing/stale 为 409、failed/unavailable 为 503；共享 relation command 的其他页面入口不受该页面 gate 影响。
   - `/api/workbench` 旧 full-payload shape 在 cutover 后不得继续出现。

4. **Read model、cache、worker 测试**
   - month generation 原子切换改变 token，旧 cache 不能命中新版本。
   - refreshing 时稳定旧 payload 可读但不标 fresh。
   - main Workbench worker 正确 fan-out all；aggregate instance/event/warmer 不存在。
   - month publish 继续投递 cost-statistics 既有 targets。

5. **前端组件与交互测试**
   - loading/empty/error/refreshing/stale/fresh、显式 banner 和写按钮禁用。
   - load-more/search/filter/detail 带 version；409 清理选择并完整重载。
   - initial/background reload 收到不同 version 时，即使没有 409，也原子清空旧 selection/detail/pagination；相同 version 不做无意义重置。
   - Redis/cold/hot 对前端展示合同无差异。
   - ImportWorkflowPage 有 barrier targets 时等待既有 barrier；没有 targets 时不请求任何 Workbench 首屏/groups API。

6. **端到端业务流测试**
   - confirm/withdraw → affected month dirty → worker publish → token 变化 → SSE 重载。
   - worker 刷新期间继续显示旧 stable generation，禁止写；新版本激活后自动替换。

7. **现有功能回归测试**
   - 其他页面 API/read model/permissions/export 不变，p95 回归 ≤5%。
   - Search 的结果、排序、status/project filter 与 cache clear 不变；Batch Accounting 的 list/submit/withdraw 不变；settings reset 通过 durable targets 收敛；当前 SQL Cost Statistics API/worker 不依赖已删除 legacy service。
   - workbench_relation 与 cost-statistics fan-out 不丢失。
   - local runtime、generation convergence、operations dashboard 和 HTTP SLO probes 已迁移，不保留 summary/full-payload 旧探针。
   - deploy registry/App Health 不再期待 aggregate worker。
   - whole-repo guard 证明旧 provider/API assembler/raw payload assembler/on-demand get-or-build/fallback/warmer/aggregate symbols 为零。

建议验证命令以仓库入口为准：

```bash
bash scripts/verify.sh lint
bash scripts/verify.sh backend
bash scripts/verify.sh frontend
bash scripts/verify.sh e2e
bash scripts/verify.sh docs
```

此外执行 Workbench 定向 backend/frontend/E2E 测试、SQL EXPLAIN 基线与本地/隔离环境 performance regression。本次禁止生产只读 performance smoke，也禁止加载生产 token；统一发布后如需生产验证，只能通过 `scripts/with-production-admin-token.sh <command>` 加载，不打印、不入库。

## 10. 文档影响

实施时必须同步更正以下长期事实，不能让文档继续宣称存在有效 all aggregate publish：

- `docs/modules/reconciliation-workbench/README.md`、`boundary-io.md`、`tests.md`；
- `docs/modules/read-models/boundary-io.md`；
- `docs/modules/runtime-workers/boundary-io.md`；
- `docs/architecture/module-boundaries/read-model-contracts.md`；
- `docs/app-architecture/runtime-and-ownership.md`；
- `docs/architecture/persistence-and-read-models.md`、`docs/architecture/backend-refactor/architecture-inventory.md`；
- `docs/dev/api-contracts.md`；
- `docs/operations/monitoring.md`、`docs/operations/runtime-worker-governance.md` 与 deploy README/manifest 生成说明。

如果 Search、Batch Accounting、Cost Statistics 或 imports 模块的 `boundary-io.md` 当前登记了 generic full Workbench payload / `fetchWorkbenchInitialPage` 依赖，则同步删除该依赖；只记录 I/O owner 变化，不改它们的产品口径。

产品业务口径没有变化：paired/unpaired 与正式关系事实源保持不变，因此除非实施发现当前产品文档有事实冲突，不修改产品规则。

## 11. 发布、监控与回滚

### 11.1 本次实施 goal 的硬停止线

- 代码、测试、文档、受控性能证据和发布交接完成后立即停止；不要部署、canary、访问生产性能接口、加载生产 admin token、drain queue 或停 worker。
- 不执行 `git add/commit/push`、merge/rebase 或 release 创建，避免把同时进行的其他 thread 改动卷入。本任务最终报告只列出自己修改的文件和验证证据。
- 受控环境结果标记为 `implementation-verified`；发布状态固定记录为 `deployment_status: deferred_by_user`，不得写成 production-passed。

### 11.2 所有 thread 汇总后的统一发布前

- 先汇总全部 thread，检查最终 diff/冲突并形成单一 release bundle；复跑定向与全量测试，不能直接复用各 thread 结束时的旧结果。
- 完成至少 35 天生产 access-log external consumer 门禁、全量备份和生产等价 performance baseline；外部 consumer 必须先迁移，不得临时恢复旧 API fallback。
- 确认 registry、systemd env、RabbitMQ dispatch、App Health 和 queue 中不再需要 aggregate lane。
- 确认其他页面 regression evidence 与 p95 基线。

### 11.3 统一发布中

- 使用 `./scripts/deploy-oa.sh` 正式入口。
- 在切换 release 前短暂静默仍会产生 aggregate-only event 的旧 producer，使用现有旧 worker/runtime queue ops 将 all-lane active event drain 到零；随后一次性启用能处理 ordinary `all` fan-out 的新 `workbench` registration，并由 deploy convergence stop/disable 已不在 registry 的 `workbench-aggregate`。不新增队列改写工具，不静默丢弃普通 month refresh。
- 小流量 canary 后再扩大；持续观察 statement timeout、DB buffers/CPU、Redis error、worker latency、409 rate 和前端可用时间。
- canary 后执行第 8 节完整生产性能矩阵与其他页面隔离对比；未通过就停止放量，不能靠提高 timeout 或恢复隐藏旧链达标。

### 11.4 回滚

- 前端、后端、worker registry/deploy manifest 必须作为一个 release bundle 回滚，禁止新前端配旧 API 或新 registry 配旧 worker；不回滚 canonical facts，不重建旧 projection。
- 本计划不包含 schema migration，active month generations 保持可读，因此应用回滚是主要手段。
- 不在新 release 内保留或重新启用 legacy provider、row-detail fallback 或伪 aggregate 作为运行时开关。紧急回滚到上一个完整 release bundle 可能暂时恢复旧实现，但它只是事故止损，不是新架构的 fallback；修复后仍必须重新完成删除门禁。
- 若新查询 correctness gate 失败，直接停止放量；继续由最后一个验证通过的应用版本读取现有 generation。

## 12. 完成定义

### 12.1 本次实施 goal 完成

只有同时满足以下条件，主控才可以把本次实施 goal 标记 complete：

- 同一受控数据/负载下的 cold/hot/write-to-fresh/前端/隔离性能回归完成，查询计划和资源使用达到第 8 节工程门槛或给出可复现的环境差异；不能声称生产 SLO 已通过。
- summary 与两区页面共享 canonical-owner 语义，并通过独立 expected-set 验证。
- initial、pagination、search/filter、group detail、row detail 全链版本固定。
- refreshing 旧版本展示、禁写、自动替换行为通过组件与 E2E 测试。
- Workbench action API 在缺版本、版本冲突和 non-fresh 状态下服务端 fail closed，不能绕过前端禁写。
- legacy full API、on-demand raw/full page build、row-detail fallback、aggregate lane、warmer 运行代码和配置全部删除。
- `_build_api_workbench_payload` 的 Search/Batch Accounting/write/settings/ops 调用方全部按窄 I/O 解耦，其他页面输出与 read model 未改变。
- `ImportWorkflowPage` 不再读取 Workbench 首屏探测刷新，只消费 operation barrier targets。
- 仓库内 consumers 已迁移；生产 external consumer 核查明确留在统一发布门；代码中没有隐藏兼容分支。
- 七类测试、定向/全量验证、长期文档更新、发布/监控/回滚交接完成；测试失败不得以“可能来自其他 thread”为由隐藏，必须给出可归属证据。
- 其他页面 read model、API、数据和性能没有被污染。
- `git status` 与最终 diff 证明没有覆盖、暂存、提交或删除其他 thread/用户改动；最终报告包含 `deployment_status: deferred_by_user`、未执行生产步骤和剩余生产风险。

### 12.2 统一发布后的 production-verified 完成

以下条件必须在用户统一部署窗口另行执行，不能由本次主控伪造或提前勾选：

- 合并后的 release candidate 通过全量验证、备份与 external consumer 门禁。
- all-lane 已由旧 release drain 为零，aggregate worker 按 release bundle 停用，新普通 Workbench worker 的 `all` fan-out 正常。
- 生产 canary、cold/hot/write-to-fresh/浏览器/隔离 SLO 全部通过，statement timeout 为零，无旧 route/worker 流量。
- 回滚演练和持续监控通过；确认其他页面 p95 回归不超过 5%，且 API/read model/数据合同不变。

只有本节通过，功能才可以标记 `production-verified`。

## 13. 最终设计判断

该方案的复杂度来自现有跨月 generation、刷新一致性和旧链删除责任，而不是新增基础设施。最终关联台运行模型仍只有：**一个既有 generation 事实源、一个 repository SQL owner、一个 query facade、一个首屏 API、一个可丢弃缓存和一个现有 Workbench worker lane。** Search/Batch Accounting 等模块只通过各自窄输入读取所需数据，不再复用页面 full payload。

因此它同时满足：

- 简洁：删除的模块多于新增模块，没有第二套 projection。
- 高性能：直接消除 all-scope 重 SQL、串行多请求和过度 payload。
- 高信赖度：同快照、同 owner 规则、同 generation token、明确 stale/refreshing、失败关闭。
- 强隔离：所有变化局限在 Workbench 查询/缓存/worker lane，其他页面 read model 不变。
