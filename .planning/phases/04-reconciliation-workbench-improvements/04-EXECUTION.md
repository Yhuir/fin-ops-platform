---
phase: 04-reconciliation-workbench-improvements
status: implementation_verified
updated: 2026-07-16
head_at_start: 78ace2630ed0d72f3e40eedbc0e16ce78cd61164
deployment_allowed: false
production_validation_allowed: false
deployment_status: deferred_by_user
---

# 关联台高性能链路执行状态

## 主控约束

- 事实源保持现有 PostgreSQL 统一事实源与 Workbench active generation；不新增 projection。
- 只优化关联台链路。跨模块消费者只能迁移到明确的窄查询 I/O，不改变其他页面的 read model、业务口径或刷新语义。
- Ponytail：优先复用现有 repository、facade、generation、version/freshness 合同；删除旧链，不保留 fallback、双写、兼容旁路或预留抽象。
- 本阶段不部署、不读取生产 token、不停止或 drain worker、不执行生产性能验证。
- 本阶段不执行 `git add`、commit、push、merge、rebase；由用户在其他 thread 完成后统一处理工作树与部署。
- 只保留本文件作为执行状态；每个后续 prompt 必须由上一个 prompt 的证据决定。

## 共享工作树保护基线

启动 HEAD：`78ace2630ed0d72f3e40eedbc0e16ce78cd61164`（`main`）。以下文件属于其他 thread，禁止修改、覆盖、格式化或清理：

| 文件 | 启动/发现时 SHA-256 |
| --- | --- |
| `backend/src/fin_ops_platform/services/cost_statistics_read_model_refresh.py` | `1219fa60dfd55b90ef0d4748cff323dc691b8c4bb408edf089b8e9dabad7032e` |
| `backend/src/fin_ops_platform/services/cost_statistics_read_model_repository.py` | `11f5480f4232bc525bc7db7dadf1234b4fa2d5e069cc243d845d828df275bf15` |
| `docs/modules/oa-pending-payments/README.md` | `aeadf2d8ac7d0b13270a1c0ed21df7391d64459027ad1a8ec5949d25d4567815` |
| `.planning/phases/05-cost-statistics-improvements/05-01-PLAN.md` | `d057aebfa061820da23014ed52e236f5a120b37c99c1cb385ec59b30669404ca` |
| `.planning/phases/05-cost-statistics-improvements/05-01-SUMMARY.md` | `8d88e10b6b7ea6e08dee6d5ab7adf8bf5eee651cb439691cc32efde5b01ed0a9` |
| `.planning/phases/05-cost-statistics-improvements/05-02-PLAN.md` | `92b8f8c2ad76d74d8728396e6f7aabdee2cc2fbe8cabf8bdad18f7493ee2d075` |
| `.planning/phases/08-oa-pending-payments-improvements/08-PERFORMANCE-INTEGRITY-GOAL-PROMPT.md` | `d54333ac4f534f2f5b00fc4efcd89df2570b42426d49416150e43d3aa56d7115` |
| `docs/modules/cost-statistics/performance-freshness-lock-overlay-design.md` | `3e2510d948f2a4d1d0dffbfa9d92e27594def92f8eb03ee9090bfbb683e2e65c` |
| `docs/modules/oa-pending-payments/performance-integrity-design.md` | `3c84ff15f1fc9bbeb0e4366fd2b9b034adc5dcd15793e5dd826ca6b6949a2215` |
| `backend/src/fin_ops_platform/app/worker.py` | `60c9276d08cdea85cf2e9c33b9d4b6a2c4884c1e21c923106e1429baa32fe7cc` |
| `backend/src/fin_ops_platform/services/cost_tax_sql_projection.py` | `51eb8c55eb4ff1ba77af9cdd3d46f203b9600996cde5cf149bd9b8af97aafa3b` |
| `backend/src/fin_ops_platform/services/oa_projection_sync.py` | `b5993a08d81eeb2bd0198b42d83fce40524c8b780483529d789299eeb1d97361` |
| `tests/test_cost_statistics_sql_runtime.py` | `f2740285bdad5f82855b7aae58df6e37112373a3b0adad5378c79380f64aa140` |
| `backend/src/fin_ops_platform/postgres/migrations/0104_oa_pending_payment_source_snapshot.sql` | `eea33f914cac5866395ca4924096142cdd677c4f25b9385da71120076f26fab5` |
| `backend/src/fin_ops_platform/services/postgres_repositories/oa_pending_payment_source_snapshot.py` | `b6f30aadd607d84c921c6af90670644f0fa92e4449eb670e597445cfa82b6105` |
| `backend/src/fin_ops_platform/services/postgres_repositories/oa_pending_payment_admission.py` | `7b909852af4208bc1fd5f8c885c0b83e8715f7e29c9f38032939341967ef65d9` |
| `tests/postgres_test_utils.py` | `3289ca43132569767d9c111ac683f88f02b546c7c8efa9fc81148faea55a0971` |
| `tests/test_oa_projection_sync_service.py` | `f7396b8bafdae8e8461739c8fd5ec12fff223f76e4814a5d0706379c1cbd4a1b` |
| `tests/test_postgres_migrations.py` | `4223afd1e2f74347f6c25a2ed6a1ea019a53f2fa5af1f5dda1b302d5138dce53` |
| `tests/test_oa_pending_payment_source_snapshot_repository.py` | `214c6e00f7fa7935fcc96f808399da3c62f950e25d329708e72ef5086bdd69fa` |

Phase 04 的 `04-PLAN.md`、`04-GOAL-PROMPT.md` 和本文件属于本任务。

`backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` 是共享目标文件：其他 thread 已在 cost-statistics 区域加入 publish/fence hunk；发现时该 pre-existing diff 的 SHA-256 为 `daf6a0352b3d005a078085d6a4abe376ce1da94be74bc07a7ebe30d467aa09b5`。Phase 04 只允许编辑 Workbench 区域，并必须逐轮确认该 pre-existing hunk 原样保留。

以下长期文档也已被其他 thread 修改，后续 Phase 04 若必须编辑其中的 Workbench 事实，只能追加/修改 Workbench 独立段落并保留现有 diff：`read-model-contracts.md` (`ae10ca03...`)、cost-statistics boundary/state/tests (`3f0fd09b...` / `f521bc7e...` / `6e4c8797...`)、read-models boundary (`271a517d...`)、runtime-workers boundary (`bfc0676e...`)、runtime-worker-governance (`bbe0c08f...`)。括号内为发现时单文件 pre-existing diff SHA-256。

## Prompt 01：全链路基线审计

状态：`completed`

### 已核对事实源与边界

已读取根入口、系统架构、app 架构、模块索引、模块边界 inventory，以及以下直接/上下游合同：

- reconciliation-workbench、workbench-relations、canonical-facts；
- read-models、runtime-workers、read model contracts、runtime worker governance；
- Search、Batch Accounting、Imports、Cost Statistics、Data Reset；
- Workbench 产品规格、API 合同、状态机、测试矩阵与历史实施记录。

结论：现有 active generation 原子发布模型是正确事实边界；高延迟来自查询链路与旧聚合链，而不是缺少新的 projection。设计方向合理，无需增加中间事实存储、通用 gateway 层或新的 worker 类型。

### 当前生产读链

```text
Workbench 页面 / ImportWorkflow 状态刷新
  -> web workbench/api.ts
  -> /api/v2/workbench/summary + /api/v2/workbench/groups
  -> WorkbenchQueryFacade.summary()/groups()
  -> WorkbenchRelationRepository
  -> active generation 中按 scope/page 读取
```

同时仍存在一条必须删除的旧链：

```text
/api/workbench 及若干内部消费者
  -> WorkbenchLegacyApiSqlReadProvider
  -> WorkbenchApiPayloadAssembler / WorkbenchRawPayloadAssembler
  -> get_workbench_view / _get_or_build_workbench_read_model
  -> 全量 payload、旧缓存或非 SQL fallback
```

### 旧链迁移与删除矩阵

| 旧入口/模块 | 当前问题 | 目标 I/O / 删除条件 |
| --- | --- | --- |
| `GET /api/workbench` legacy provider/assembler/raw assembler | 全量 payload、重复 owner、timeout/fallback 语义 | 前端初始加载迁到一个组合 initial-page 合同后删除生产入口及三个旧模块；whole-repo 运行时引用为零 |
| 独立 `summary()` 首屏请求 | 与 groups 分开取数，增加往返和版本漂移窗口 | repository/facade 在同一事务、同一 active generation/version 返回 summary + first page；页面首屏只发一次请求 |
| `SearchService.grouped_workbench_loader` | 依赖全量页面 payload | 复用 repository 的窄搜索输入；不得引入新 read model 或通用 port |
| legacy `CostStatisticsService` 的 grouped loader 组装 | 仍注入全量 Workbench builder | 若生产调用方为零则删除 legacy 组装；保留现有 CostStatisticsQueryService/read model/worker，不触碰其数据链 |
| Batch Accounting fallback | SQL 窄 loader 不可用时回退全量 builder | 现有窄 SQL loader 变为必需依赖并 fail fast；删除 fallback lambda |
| ignored rows fallback | SQL repository 不可用时回退全量 read model | 使用现有 `list_workbench_ignored_rows` 窄查询并 fail fast；不改变 ignored 数据合同 |
| Settings data reset 完成钩子 | 调用全量 builder 模拟重建完成 | 只依赖既有 lifecycle targets/barrier；删除页面读取副作用 |
| `WorkbenchWriteFacade` full payload 注入 | 写链反向依赖全量读 payload | 金额校验/ignored 操作只接收现有 canonical row/ignored 窄 loader；删除 full payload 依赖 |
| row detail live/in-memory/SQL fallback | 可绕过 active generation，造成同页版本不一致 | row detail 只从请求 version 对应的 active generation repository 读取；旧 fallback 代码和文档全部删除 |
| `ImportWorkflowPage` legacy full-payload fallback | 额外触发旧读链 | 只使用 refresh targets/status；删除 legacy fallback |
| `workbench-aggregate` lane | materialize `all` 聚合，成本高且与 query-composed all 重复 | 主 Workbench worker 在 `all` refresh 时 fan-out 月 scope；删除 aggregate registry/env/deploy/tests/docs |
| groups page cache warmer | 预热复杂化且不解决冷路径 owner | 删除 warmer、env、wiring、测试与文档；保留 fresh gate 后的既有 payload cache 能力 |
| probes/scripts/测试夹具 | 继续固化旧 `/api/workbench` 或 aggregate 语义 | 迁到 initial-page/groups 与 query-composed all；零引用门禁覆盖运行时代码、部署与当前文档 |

### 性能基线证据

仓库现有生产证据 `.planning/refactors/read-model-performance-optimization/evidence/20260702T071757Z/workbench-profile/production-workbench-profile.txt` 显示：

- 历史 `all` aggregate 发布约 `7.8–15.1s`，月 scope 多为 `1.1–3.2s`；
- 当时 active all generation 约 960 groups / 1941 group rows / 1701 rows；
- group_rows、groups、rows 三张表总占用分别约 103MB、82MB、79MB。

计划文档记录的历史 API 证据为：summary `160–209ms`、单月 paired/unpaired `433–693ms`、all paired/unpaired `7–11s`，并出现约 10 秒超时。该证据足以证明优化必要性，但 profile 中有一处列名不匹配和一处 pg_stat 占位错误，不能把不完整片段当作优化后验收结果。

本机未配置 `FIN_OPS_TEST_DATABASE_URL`，且本阶段禁止生产验证。因此实现期以 repository/API 契约测试、查询计数/SQL 形态门禁和可重复的本地非生产 benchmark 为主；最终生产 p95/p99 仅形成待部署验证手册，不伪造结果。

### 审阅结论

- 计划整体合理，没有必要增加 projection、事件消费层、第二套缓存、双读或通用查询抽象。
- 发现并补齐的遗漏是：API 文档仍明确允许 row detail live/in-memory fallback；read-model/worker 文档仍把 `workbench-aggregate` 作为正式 repair lane。这两类旧合同必须与代码同步删除。
- 发现并补齐的隔离责任是：Search、Batch Accounting、Settings Reset、ignored rows、Imports、legacy Cost Statistics 组装不能在删除旧 builder 后悄悄回退或变空；每个消费者必须迁到现有窄 I/O，并有回归测试。
- 当前没有无法从仓库事实源确定的内部调用方。外部未知消费者通过发布前 compatibility/zero-reference 检查处理；本阶段不以隐藏 fallback 兜底。

## Prompt 02：初始页快照与版本合同

状态：`completed`

目标：先在 `PostgresReadModelRepository` 与 `WorkbenchQueryFacade` 内建立同一事务、同一 generation/version 的 summary + paired/unpaired first page 组合读取，并补齐 repository/service 测试；暂不改 HTTP、前端和旧链。代码审阅发现当前 all-scope summary 仍累加月 summary，而 groups 使用 logical-group owner，因此本轮只完成快照/version 基础合同，不会错误宣称 canonical-owner 已闭环；下一轮必须以该合同为边界重写 all-scope canonical-owner cold SQL。完成后根据查询形态、版本语义和测试证据决定 Prompt 03。

验收边界：

- 复用现有数据结构与 SQL helper，不创建新 projection/table/worker/gateway；
- initial page 只读取请求 scope 所需数据，不 materialize 全量 payload；
- `month=all` 继续 query-compose 月 shards，并在同一快照内返回一致 version/freshness；
- 空数据、非法 scope/filter、过期 expected version、分页边界有明确合同；
- 只修改 Phase 04 目标文件与测试；不触碰共享工作树保护清单。

完成证据：

- 新增 `PostgresReadModelRepository.get_workbench_initial_page(...)`，生产路径要求 transaction 能力，并在同一个 transaction 内执行 `REPEATABLE READ READ ONLY` 与 transaction-local `statement_timeout = 2s`。
- 首屏强制 paired/unpaired `page=1`、`page_size=200`、`detail_level=summary`；调用方不能通过 query 放大首屏。
- summary、paired、unpaired 任一缺 version 或 version 不同均 fail closed；状态合并优先级为 failed > refreshing > stale > fresh。
- 新增 `WorkbenchQueryFacade.initial_page(...)`，保持 repository/freshness/OA status/error mapping 边界；尚未接 HTTP，也未引入 Redis 新 owner。
- 验证：`tests/test_workbench_query_facade.py tests/test_workbench_sql_runtime.py` 共 190 passed、6 subtests passed；四个目标文件 ruff 通过；`git diff --check` 通过。
- 七类测试判断：本轮覆盖 service-layer 与 read-model/cache/background-job 类中的 read snapshot/version/miss/fail-closed；API、frontend、E2E 尚未接线所以本轮不适用；business core 仅新增版本不变量，已在 repository 测试覆盖；existing regression 由两份完整 Workbench 测试文件覆盖。

## Prompt 03：all-scope canonical owner 与 cold SQL

状态：`completed`

目标：只在 `PostgresReadModelRepository` 的 Workbench SQL owner 与 `tests/test_workbench_sql_runtime.py` 内完成 `month=all` canonical owner 收敛：logical group 跨 zone 只能有一个 owner，paired 优先；summary/count/page 使用相同 owner/member identity 语义；默认 initial page 避免重复的 window/string aggregation 和全详情物化。不得改 route、facade、frontend、schema/index 或 worker。

停止条件：跨月、跨 zone、重复 member identity、summary/page counts 与 version 的 correctness 测试通过；SQL 形态证明分页前 owner 唯一且没有 materialized all generation；若没有测试数据库，不伪造 EXPLAIN，只记录待受控环境执行的 SQL/plan 门。

完成证据：

- `_workbench_active_month_groups_sql(...)` 是唯一 logical group owner：`DISTINCT ON (all_scope_group_id)` 按 paired 优先、scope month/updated_at 决定稳定 owner；不再按 `zone + logical_group_id` 产生两个 owner。
- 默认 initial/groups/detail 使用非聚合 owner SQL，不执行 `string_agg(searchable_text)` 或第二个 canonical window；只有普通全文搜索/自定义排序启用同一 owner zone 内的 metadata window。
- all summary 不再累加月 summary counts；它消费同一 canonical group 子查询，并按 `(pane, object_identity_key || row_id)` 去重 canonical members。zone counts、global counts 与 groups page 的物理 member join 都限定 canonical owner zone。
- all scope 仍只 join active month generations，未读取或写入 materialized all generation，未新增 schema/index/projection。
- 新增/更新 SQL correctness/shape 测试覆盖 paired 跨 zone 优先、非 mergeable scope 前缀、member identity distinct、默认无 string aggregate、搜索保留 aggregated metadata、version 固定。
- 验证：两份 Workbench 测试 191 passed、6 subtests passed；ruff 与 `git diff --check` 通过。
- 限制：`FIN_OPS_TEST_DATABASE_URL` 未配置，未执行真实 PostgreSQL EXPLAIN/ANALYZE；最终受控性能证据必须补跑，不能把 SQL 形态测试表述为 SLO 已通过。

## Prompt 04：initial HTTP、默认缓存与 expected version

状态：`completed`

目标：只收敛 Workbench facade/route/server wiring/API contract：`GET /api/workbench` 改为组合 initial page；解析白名单 `paired_query`/`unpaired_query`；复用现有 Workbench cache key 纯函数形成仅默认首屏的 versioned Redis 缓存；Redis miss/down 回相同 repository cold path；为 `/groups` 和 row detail 补 `expected_read_model_version` 服务端 409。暂不改前端、不删除跨模块 consumer 或 worker lane。

停止条件：API contract tests 覆盖 200/202/400/409/503、fresh/refreshing/stale、Redis hit/miss/down DTO 等价、timeout 不 enqueue refresh；route 不拼 SQL/业务 payload，server 不再让 `/api/workbench` 走 legacy provider；默认 initial 之外不缓存。

完成证据：

- `GET /api/workbench` 现在只经 `WorkbenchReadApiRoutes.initial(...) -> WorkbenchQueryFacade.initial_page(...)`，接受严格白名单的 `paired_query` / `unpaired_query` JSON object；旧 `WorkbenchLegacyApiSqlReadProvider` 已从 server import、builder 和该 HTTP 入口移除。
- 首屏默认查询使用 active generation/version 派生的专属 Redis key；只有无过滤的固定 `page=1/page_size=200/detail=summary` 首屏可缓存。cache hit 校验 payload version，miss/down 走同一 repository cold path；Redis 不是 freshness owner，filtered query 不读写该 cache。
- page-facing freshness 改为 generation/dirty-scope/schema 的轻量 context，不再在 groups/initial 热路径读取 worker heartbeat、outbox backlog 或 consistency audit。
- `/groups` 与 `/rows/{row_id}` 接收 `expected_read_model_version`；facade 和 repository 在 cache/read 前 fail closed，冲突返回 409。公开 row detail route 已删除 ETC/live/file-cache/opaque-OA/legacy fallback，只保留 generation repository owner。
- statement timeout 统一返回 `503 {error: query_timeout, read_model_status: unavailable, retryable: true}`，不再伪装 refreshing，也不因查询慢 enqueue refresh。
- 测试覆盖 initial 200/202/400/503、fresh/stale/refreshing、默认 cache hit/miss/down、filtered cache bypass、groups/row 409、row detail 无 fallback 和 HTTP wiring。定向验证：`tests.test_workbench_routes tests.test_workbench_query_facade tests.test_workbench_sql_runtime` 共 206 passed；目标 route/facade/cache/server/tests ruff 通过；`git diff --check` 通过。
- 当前共享 `read_models.py` 的整文件 ruff 被另一 thread 在 OA 区域的未完成变量引用阻挡；Phase 04 未编辑该区域，没有越界修复。Workbench 定向测试完整导入并执行了该共享模块。

## Prompt 05：前端单请求与跨版本读取一致性

状态：`completed`

目标：只修改 Workbench 前端 API/client/page state 与对应前端测试：`fetchWorkbenchInitialPage(...)` 改为单次 `GET /api/workbench`；把 initial 返回的 `read_model_version` 固定传播到 load-more、search/filter、group detail、row detail；initial/background reload 收到不同 version 时原子清空 selection、detail、pagination 和旧 group state；409 触发整页原子 reload，不能混合新旧 generation。refreshing/stale/failed/unavailable 必须显式展示并纳入页面写入门禁。暂不改后端 action gate、跨模块 consumer、worker/aggregate 或旧模块删除。

停止条件：组件/API 测试证明首屏只有一个业务请求；paired/unpaired query shape 等价；same-version reload 不丢用户状态，different-version/409 一次性清理并重载；groups/group detail/row detail 都携带 expected version；non-fresh 页面没有可用写入口。不得增加状态管理库、通用 store、兼容请求或第二套 DTO。

完成证据：

- `fetchWorkbenchInitialPage(...)` 已收敛为单次 `GET /api/workbench`，把两区既有 query 映射为严格的 `paired_query` / `unpaired_query`；首屏不再发 summary + 两个 groups 请求。
- initial 顶层 generation version 被传播到 paired/unpaired page；load-more、group detail、row detail 均携带 `expected_read_model_version`。API client 保留 409 status/error code，页面可识别 version conflict 后触发完整首屏重载。
- 页面只接受最后一次 initial 请求结果；same-version 后台刷新保留 selection/detail，different-version 原子清除 selection、detail、pagination/group page、展开区和所有未提交 dialog，再替换两区数据，禁止新旧 generation 混合。
- refreshing/stale/failed/unavailable 有明确页面状态；`canWriteWorkbench` 同时要求页面 generation fresh 且 version 非空。旧的“refreshing 仍可关联”测试已改为禁写合同。
- 没有新增状态库、store、DTO owner、缓存或兼容请求；复用页面本地 state/ref 与现有 API mapper。
- 测试新增/更新：首屏单请求/query shape、groups/group detail/row detail expected version、409 error contract、same-version 保态、different-version 原子重置、refreshing/stale 禁写/提示、现有 action/detail/filter/路由回归。
- 验证：六份 Workbench 前端定向测试共 147 passed；`npm run build` 通过；八个本轮目标文件 `git diff --check` 通过。构建仍输出现有 HeroUI/Tailwind CSS minify 与 bundle-size warning，本轮未改依赖或全局样式，不属于 Workbench 查询合同失败。
- 七类测试判断：frontend component/interaction、API client contract、read-model/version UI state、existing feature regression 适用并已覆盖；business core、backend service、跨模块 E2E 本轮没有新增后端/业务行为，分别由后续 action gate 与最终 E2E 轮覆盖。

## Prompt 06：Workbench action generation/freshness 服务端门禁

状态：`completed`

目标：只收敛 Workbench 页面 action API、`WorkbenchWriteFacade`/现有 query context 依赖与前端 action payload：所有 relation、override、exception 类 Workbench 写请求必须携带当前 `expected_read_model_version`；route 在进入 write facade 前复用现有 `WorkbenchQueryFacade` 轻量 page context 校验。缺版本返回 400，version 冲突或 refreshing/stale 返回 409，failed/unavailable 返回 503；不得把 gate 下沉到共享 relation command，不得改变其他页面 API/read model/写命令行为。

停止条件：先全量列出 Workbench 页面所有写 endpoint 与 client 调用，证明没有漏掉 preview/apply/cancel/ignore/cash-special 等入口；每个实际改变 relation/override/exception 状态的 endpoint 服务端 fail closed，preview 是否要求 version 必须按其是否依赖 generation rows 从代码事实决定并保持一致；frontend 永远取 active generation ref，不从 row/payload 猜 version。backend API/service 与 frontend tests 覆盖 400/409/503/fresh、权限、版本切换和其他页面共享 command 回归。不得新建通用 middleware、precondition service、共享 command 分支或 compatibility fallback。

完成证据：

- 全量列出并覆盖 17 个 Workbench action handler，包括 relation confirm/withdraw 的 preview+submit、统一异常 preview+apply、mark/cancel exception、ignore/unignore、cash special、bank exception、personal advance 等入口；每个入口都在 write facade 或 preview 数据解析前经过同一现有 server guard。
- `WorkbenchQueryFacade.write_precondition(...)` 直接复用轻量 `get_workbench_groups_freshness_status(...)`：缺 `expected_read_model_version` 返回 400，generation mismatch 返回 409，refreshing/stale 返回 409，failed/unavailable/missing stable generation 返回 503；不执行 full page query，不新建 middleware/service/store，也未修改共享 relation command。
- 所有 Workbench 前端 action/preview payload 都从页面 active generation ref 发送版本；API type 将版本设为必填。服务端拒绝旧 generation 后，页面重新读取 initial；新 generation 通过现有原子 apply 清空旧 selection/detail/dialog，禁止用户在旧选择上重试写入。
- 前端错误识别从“任意 409”收窄为三个 Workbench generation/freshness error code，避免把普通业务冲突误判为 generation 切换。
- 后端定向验证：`tests.test_workbench_query_facade tests.test_workbench_routes` 共 42 passed；目标 Python 文件 Ruff 通过。前端定向验证：`WorkbenchApi`、`WorkbenchExceptionModal`、`WorkbenchSelection` 共 94 passed，其中新增“preview 后 generation 切换时写入 409、数据不移动、自动 reload 并清空旧选择”的交互测试；`npm run build` 和目标文件 `git diff --check` 通过。构建只有既有 CSS minify/bundle warning。
- 扩大运行 7 份历史 Workbench 写测试共 273 tests，得到 111 failures / 44 errors。失败证据集中在旧内存 `/api/workbench` full-payload 读取现已按 SQL-only 合同返回 503，以及旧 action fixture 缺 generation 返回 400；没有为让旧测试变绿而恢复 fallback。该结果作为后续旧链迁移/删除的输入，不是保留双路径的理由。
- 七类测试判断：business precondition、service/read-model freshness、API contract、frontend interaction、跨层 generation race 与 existing regression 均适用并已覆盖；本轮不改 worker/部署，所以 background-worker 与生产部署验证不适用。生产性能验证仍按主控约束延期。

## Prompt 07：写链解除 legacy full-payload 反向依赖

状态：`completed`

目标：先对 `_build_api_workbench_payload`、`_get_or_build_workbench_read_model`、公开 row-detail helper 与 `WorkbenchWriteFacade` 做 whole-repo 结构/文本扫描；本轮只迁移 Workbench 写命令自身仍依赖 legacy full page/HTTP detail 的金额、OA source id、ignore-row 等输入，改为复用现有 canonical row/relation/ignored 窄 loader。不得同时修改 Search、Batch Accounting、Settings、Imports、worker/aggregate/warmer；这些由后续 prompt 根据本轮零引用差额逐项处理。

停止条件：所有 Workbench preview/write 的事实输入来自明确的 canonical/relation 窄 I/O，不再通过页面 DTO、公开 row-detail route、full payload builder 或 on-demand read model 反向解析；权限、幂等、audit、amount mismatch、stale preview、dirty scope 和 rollback 行为测试保持。若现有依赖足够则只重连并删除旧注入；不得新建 resolver class、通用 port、fallback 或重复事实模型。完成后用 CodeGraph impact/whole-repo scan 计算剩余 legacy consumer，生成下一 prompt。

完成证据：

- CodeGraph caller/impact 与 whole-repo 文本扫描确认写链遗留为三处：`ignore_row` 构建 full grouped payload、`unignore_row` 使用带 full-read-model fallback 的 ignored loader、金额/OA source id 经内部公开 row-detail helper 反查页面 DTO。
- `WorkbenchWriteFacade` 删除未使用的 `amount_check_for_row_ids`、`resolve_live_row`、`build_workbench_payload`、`build_ignored_rows_payload` 四个注入；没有新增类、port、service 或兼容分支。
- `ignore_row` 通过现有 `resolve_live_rows_direct([row_id], month_hint=...)` 只解析目标 canonical row；金额校验、row type、withdraw rows 与 OA source ids 同样复用该批量窄 resolver，不再调用 HTTP row-detail 或 page DTO。内部 `_get_api_workbench_row_detail_payload` 因运行时零调用已删除。
- `unignore_row` 使用单独的 `_list_workbench_ignored_rows_for_write(...)`，只允许现有 PostgreSQL `list_workbench_ignored_rows(scope_key=...)`；repository 缺失时 fail fast，不回退 `_get_or_build_workbench_read_model`。公共 ignored API/Search 的迁移留给下一 prompt，未在本轮越界修改。
- 新增单元/服务测试证明 ignore 只调用一次 canonical batch resolver、unignore 只调用 injected narrow loader、SQL write loader 缺失时失败且存在时传递正确 scope；原 generation gate 的 dirty-queue 测试同步发送 expected version，并把 gate 隔离为该测试之外已覆盖的责任。
- 验证：`tests.test_workbench_auth_context_idempotency tests.test_workbench_sql_runtime` 共 200 passed；`tests.test_workbench_dirty_queue_wiring` 17 passed；目标 Python Ruff 通过。扩大回归中的 stale/idempotency 两组仍因其 fixture 读取已删除语义的内存 `/api/workbench` 而失败，保留为后续测试迁移输入，没有恢复旧 route。
- 剩余生产 legacy full payload consumer 已收敛为：Search/legacy CostStatistics 构造注入、Settings reset 完成探测、Batch Accounting generic fallback、公共 ignored API fallback；worker/aggregate/warmer 是独立删除面。

## Prompt 08：Search 与 ignored rows 窄查询迁移

状态：`completed`

目标：只迁移 SearchService 的 Workbench 输入与公共 ignored rows API：先锁定 Search 当前消费字段、过滤/排序/cache-clear 语义和 repository 现有能力；复用或增加一个仅返回 Search 已消费 row/zone/project/status context 的 active-generation 窄 repository 方法，直接注入现有 SearchService callable；`/api/workbench/ignored` 与 Search ignored 输入统一要求现有 `list_workbench_ignored_rows(...)`，删除 `_get_or_build_workbench_read_model` fallback。不得改 Search 自身 read model、结果 DTO、缓存策略、其他页面行为，也不得处理 Cost Statistics、Settings、Batch、worker。

停止条件：搜索请求不再构建 Workbench page/full payload；status/project/month/query 排序、ignored 结果与 cache invalidation characterization 等价；repository/route 缺失时 fail fast，不返回空集合伪成功；`_get_or_build_workbench_read_model` 不再被 ignored path 调用。只新增当前 Search 所需的具体窄 SQL/callable，不建通用 search gateway、projection、缓存或适配层。完成后按剩余 `_build_api_workbench_payload` production refs 生成下一 prompt。

完成证据：

- 审计确认生产 `/api/search` 已由 `SearchQueryFreshnessService` 读取独立 Search SQL read model；本轮没有修改其 read model、worker、scope、source versions、DTO、fan-out 或前端。需要迁移的是非 PostgreSQL 本地即时查询对 Workbench full payload 的旧输入。
- `PostgresReadModelRepository.list_workbench_search_rows(scope_key=YYYY-MM)` 用一个有界 SQL 只读取单月 active generation 的 Workbench row、zone、group 和项目上下文；拒绝 `all` 无界 scope。没有新增 port、projection、gateway、cache、adapter 或状态表。
- `Application` 的 `SearchService` 装配只注入该窄 callable；`SearchService` 删除 `raw_workbench_loader`、`grouped_workbench_loader`、`ignored_rows_loader` 及其 raw/grouped payload 索引实现，未保留并行 fallback。现有 query cache、month index cache、结果 DTO、过滤、排序、limit 和 clear-cache 行为不变。
- `/api/workbench/ignored` 只调用现有 `list_workbench_ignored_rows(...)`；repository 缺失返回 `503/read_model_unavailable`，不再调用 `_get_or_build_workbench_read_model`。同时补齐原计划遗漏：ignored SQL 增加 active-generation join，历史 generation 不再污染 ignored 结果和 unignore 输入。
- Search API 的三条旧 full-payload/cache-snapshot 测试已迁到明确的窄 row fixture，继续保护 OA/bank/invoice DTO、ignored status 和不触发 raw rebuild；SearchService characterization 保护 project/status/group/month/limit/cache-clear 等价语义。
- CodeGraph 已索引 `list_workbench_search_rows`，旧 `_build_api_workbench_ignored_rows_payload` 符号为零；文本扫描确认 Search 生产装配不再引用 `_build_api_workbench_payload`，`_get_or_build_workbench_read_model` 不再被 ignored path 调用。
- 验证：Search API/service 12 passed；Search SQL/runtime/bootstrap/ignored 扩大回归 99 passed；完整 `tests.test_workbench_sql_runtime` 177 passed；目标 Python Ruff、`bash scripts/verify.sh docs`、`git diff --check` 全部通过。
- 七类测试判断：business core 本轮不改规则；service/read-model、API contract、read-model active generation、跨模块 Search/Workbench、existing regression 适用并已覆盖；frontend 不改行为无需新增；生产性能/部署验证继续按主控约束延期。

## Prompt 09：Settings Reset 移除 full-page 完成探测

状态：`completed`

目标：只处理 Settings data reset 成功路径仍调用 `_build_api_workbench_payload("all")` 的运行时引用。先读取 settings/reset 与 Workbench 模块边界、`SettingsDataResetService` 的 action 结果、现有 derived-data lifecycle target envelope、queue/barrier 和 API tests；确认该 full-page read 当前承担的真实语义后，删除它。reset 完成/接受语义只能由既有 durable lifecycle targets、job/operation barrier 或已有结果字段表达，不得用页面 GET/同步 rebuild 猜测完成。

停止条件：Settings reset 的 invoices/OA/rebuild 等受影响 action 不再调用 Workbench full payload/raw assembler/on-demand read model；既有 response shape、权限、audit/backup、幂等、affected scopes、queue targets 和失败行为保持；若 lifecycle targets 已完整则只删调用与旧测试，若确有缺口只补入现有 target envelope，不新增 refresh service、queue 类型、poller、projection 或兼容 fallback。不得触碰 Cost Statistics、Batch Accounting、Search、worker/aggregate/warmer 或部署。完成后按剩余 `_build_api_workbench_payload` production refs 生成下一个唯一 prompt。

完成证据：

- `_execute_settings_data_reset(...)` 已删除 `_build_api_workbench_payload("all")` completion probe 和重复 `_schedule_or_run_workbench_auto_matching_for_scopes(...)`；OA reset 只复用已有 `settings_reset_completed` lifecycle。
- durable lifecycle 成功登记后明确返回 `rebuild_status=pending`；Workbench read model 或 matching dirty scope lifecycle executor 报错时返回 `status=partial`、`rebuild_status=failed`，不再把“已入队”伪装成“已 fresh”。
- Settings 测试不再调用 legacy full builder。回归覆盖单次 matching dirty 登记、无同步 OA/Workbench row build、无同步 OCR、附件缓存保留、后台 job pending、lifecycle enqueue failure；OA 过滤与附件缓存投影正确性继续由专属 Mongo adapter 测试拥有。
- 文档同步更新 data-safety-reset/settings boundary、状态机、测试矩阵和实施记录，明确 reset job 完成与下游 active generation fresh 是两个状态。
- 验证：`tests.test_settings_data_reset_service` 23 passed；目标 Python Ruff、`bash scripts/verify.sh docs`、目标文件 `git diff --check` 通过。CodeGraph/测试表明 legacy 本地 runtime 在 lifecycle 展开 matching 月份时仍会读取 OA month catalog，但不构建 OA rows；生产 PostgreSQL projection 的同名 I/O 是一个 distinct-month SQL，本轮未为该非 full-page 元数据查询新增抽象。
- 剩余 `_build_api_workbench_payload` 生产引用只有 legacy `CostStatisticsService` 构造注入、Batch Accounting fallback 和 builder 定义本身；Search、ignored、Settings 已清零。

## Prompt 10：Batch Accounting 删除 Workbench full-payload fallback

状态：`completed`

目标：只处理 `Application._batch_accounting_service()` 向 `BatchAccountingService` 注入的 `grouped_workbench_loader=lambda month: self._build_api_workbench_payload(month)` 及由此固化的测试。先审计 Batch Accounting 未提交首屏、submit preview/submit、submitted bucket/detail 各自消费的 Workbench 字段和现有三个 SQL 窄 loader；确认所有实际生产路径都有对应窄 I/O 后，把窄 loader 改为明确必需依赖或在缺失时 fail closed，并删除 generic grouped fallback。

停止条件：Batch Accounting 的 list/summary/detail/preview/submit/withdraw 不再调用 Workbench full payload、raw assembler、on-demand read model 或页面 DTO fallback；SQL 窄 repository 缺失/异常必须返回既有明确 unavailable/error contract，不能返回空集合或切回旧 builder；现有权限、年份过滤、分页、relation count/list、submit/withdraw、audit、operation barrier 和其他页面 read model 行为保持。只复用现有 `load_batch_accounting_workbench_payload`、submit/submitted 专属 loader 与 relation facade，不新建 projection、gateway、adapter、缓存、通用 port 或兼容分支。不得修改 Cost Statistics、Search、Settings、worker/aggregate/warmer 或部署。完成后 whole-repo 扫描剩余 full-builder consumer，并根据共享工作树冲突状态生成下一个唯一 prompt。

完成证据：

- `BatchAccountingService` constructor 已删除 `grouped_workbench_loader`；`_build_workbench_row_context(...)` 不再在专属 loader 缺失/返回非 dict 时调用 Workbench full-page builder。
- 未提交列表、submit/withdraw scope backfill、已提交银行上下文分别只使用现有 `load_batch_accounting_workbench_payload`、`load_batch_accounting_submit_workbench_payload`、`load_batch_accounting_submitted_bank_workbench_payload`；submitted 不会跨用 unsubmitted loader。
- 对应 loader 缺失或 payload 无效统一返回 `503 batch_accounting_workbench_read_model_unavailable`；旧 relation 缺 scope metadata 时仍按既有合同尝试 submit 窄 loader，失败后只使用 relation 自带 month/all fallback，不构建全页。
- Batch 测试 fixture 已全部迁到专属 loader，不再 patch `_build_api_workbench_payload`。新增 unsubmitted 缺失/无效 loader、submit 缺窄 loader、submitted 跨用 loader 的负向 API 契约。
- runtime boundary guard 同时检查 Batch service/factory 不出现 generic/full builder，并锁定三个专属 loader wiring；模块 boundary/state/tests/implementation、app runtime ownership 与 API contract 已同步。
- 验证：Batch API + runtime boundary + SQL active-generation loader 共 48 passed；目标 Python Ruff、docs verify、目标 diff check 和 Batch runtime/test 零引用扫描通过。
- whole-repo 生产引用只剩 legacy `CostStatisticsService` 构造注入与 `_build_api_workbench_payload` 定义；Batch、Search、ignored、Settings、Workbench write 均已清零。

## Prompt 11：审计并删除 legacy CostStatisticsService full-payload consumer

状态：`completed`

目标：只处理 `Application.__init__` 中 legacy `CostStatisticsService(grouped_workbench_loader=self._build_api_workbench_payload, ...)` 及其真实运行时调用方。先用 CodeGraph impact/callers 和 whole-repo scan 判定现代 Cost Statistics 页面/API/read model/worker 是否已经完全由 `CostStatisticsQueryService`、projection builder 和 SQL repository 拥有；若 legacy service 生产调用方为零，删除 Application 实例与仅服务该链的 runtime wiring，保留仍有独立单元价值的纯 service 代码/测试到最终旧模块删除审计；若仍有当前生产调用方，只将该调用迁到现有 Cost 专属 SQL/read-model I/O，禁止引入第二套 projection 或把 Workbench full payload 重新包装为新 port。

停止条件：生产 Cost Statistics 页面/API/query/export/detail/worker 不再引用 `_build_api_workbench_payload`、Workbench page DTO/raw assembler/on-demand full read model；不改变 Cost Statistics 既有 API DTO、active/all scope、tag filter、bank-detail dependency、source version/freshness、worker fan-out、audit 或其他页面。优先删除无调用者 wiring，不为保留 legacy class 而新增 adapter。必须读取 cost-statistics boundary/state/tests/implementation 和 read-model contract，检查共享工作树现有 Cost 改动并只做可归属的最小 diff；若发现同一目标行仍被别的 thread 未完成修改，先转去 worker/aggregate 清理并在执行状态记录冲突，不覆盖对方工作。不得部署或执行 Git 操作。完成后根据 full-builder 零引用状态生成下一个唯一 prompt。

完成证据：

- CodeGraph callers 与 whole-repo runtime scan 证明 legacy `CostStatisticsService` 没有当前生产调用者；现代 Cost Statistics route/query/export/detail/worker 已由 `CostStatisticsQueryService`、SQL repository 和既有 projection/worker 链拥有。
- `Application` 已删除 `CostStatisticsService` import 与 `self._cost_statistics_service = CostStatisticsService(... grouped_workbench_loader=self._build_api_workbench_payload ...)` 实例；没有新增 adapter、port、projection、fallback 或第二套 read model。
- runtime boundary guard 新增禁止项，防止 server 恢复 legacy service 实例、full-builder grouped/raw loader wiring；Cost Statistics 当前 API DTO、scope、tag filter、source version/freshness、worker fan-out 及其他页面未修改。
- Cost Statistics boundary/implementation 文档已同步记录运行时所有权和旧 wiring 删除；共享工作树中其他 thread 的 Cost projection/worker/frontend 变更未被覆盖。
- 验证：Cost runtime boundary guard + 完整 `tests.test_cost_statistics_api` 共 21 passed；目标 Ruff、docs verify、目标 diff check 通过；server runtime 对 `CostStatisticsService`、`_cost_statistics_service` 和 grouped full-builder 注入零引用。
- `_build_api_workbench_payload` 生产调用方已归零，只剩定义与其专属 assembler wiring；下一 prompt 只删除该死代码和由它独占的旧测试/文档，不机械删除仍被 raw generation/write 链使用的 raw/live/OA builders。

## Prompt 12：删除零调用的 Workbench API full-payload builder

状态：`completed`

目标：在 production callers 已归零的前提下，只删除 `Application._build_api_workbench_payload(...)`、`_workbench_api_payload_assembler(...)`、`WorkbenchApiPayloadAssembler` 模块及其纯 legacy 单元测试/边界 guard；先逐项区分其 helper 是否仍被 generation、raw builder、write、Batch/Cost/Search 或其他页面独立使用，独立使用的 helper 必须保留。同步把仍直接调用/patch full builder 的当前测试迁到已存在的 initial/summary/groups、active-generation SQL repository、canonical row resolver 或专属页面 read-model fixture；若测试只保护已删除兼容 API/assembler，则删除而不复制实现。

停止条件：production runtime、current tests 和当前模块/API/架构文档对 `_build_api_workbench_payload`、`_workbench_api_payload_assembler`、`WorkbenchApiPayloadAssembler` 零引用；导入和实例缓存一并删除；不得删除仍服务 generation/raw/live/OA/write 链的 `WorkbenchRawPayloadAssembler`、`WorkbenchLivePayloadBuilder`、`WorkbenchOaPayloadBuilder` 或共享 helper。不得为测试增加兼容 facade、fallback、第二套 payload builder、projection、cache 或 generic port。必须保持 Workbench initial/summary/groups、写链、Search、Batch、Cost 与 Settings 的现有窄 I/O 及 response contract；不得部署或执行 Git 操作。完成后以 whole-repo old-chain inventory 决定下一唯一 prompt 是 aggregate/worker 清理还是测试/文档收口。

完成证据：

- 删除 `Application._build_api_workbench_payload(...)`、assembler factory/cache/import，以及 `WorkbenchApiPayloadAssembler`、`WorkbenchLegacyApiSqlReadProvider`、只服务旧 DTO 的 `InvoiceInventoryStatsService` 模块和实现细节单测。
- `test_workbench_v2_api.py` 的业务用例不再调用/patch full builder；写链测试直接验证 canonical/read-model 输入与 command result，SQL/runtime 测试直接验证当前 initial API 的 fresh/unavailable contract。Cost API 的 legacy test fixture 临时改读现有 Workbench read model payload，未恢复生产 wiring。
- architecture guard 已从“隔离但保留”改为“旧文件/符号不得存在”；当前 production runtime 对 provider/API assembler/full-builder 零引用。历史 refactor prompt/state 保留为归档，旧 query-plan 加入非当前事实源声明。
- reconciliation-workbench boundary/implementation 文档已同步；Search、Batch、Cost、Settings 和 Workbench write 的窄 I/O 未改变，没有新增 projection、facade、adapter、cache 或 fallback。
- 验证：34 个定向 Workbench V2/SQL/runtime boundary/Cost API 测试通过；目标 Ruff、docs verify、目标 diff check 通过。
- 结构扫描确认 raw/live/OA builders 仍被 generation/write 链独立使用，本轮未机械删除；下一风险最高残留是 `workbench-aggregate` registry/queue/refresh/deploy lane，warmer 单独后置。

## Prompt 13：删除伪 workbench-aggregate lane，main worker 接管 all fan-out

状态：`completed`

目标：只删除 `workbench-aggregate` 独立 worker lane 与 materialized-all aggregate scheduling。复用现有 ordinary `workbench.read_model.refresh` 事件和 main `workbench` worker：当 main worker claim `scope_key=all` 时，只规范化/列出可用 month scopes、按既有 gateway/queue contract 投递月份 refresh，并在 fan-out 接受后完成 all command；不得构建或发布 `workbench:all` generation。月份 generation 的原子构建/激活及既有 Cost Statistics fan-out 保持不变。

停止条件：删除 runtime registry aggregate instance/kind/scope split、deploy aggregate env 与迁移 helper、`enqueue_workbench_all_aggregate_refresh`、`aggregate_only`/`publish_all_aggregate`/materialized-all publish 分支，以及 SQL projection/relation writer/rehydrate/scripts/tests/当前事实文档中的生产声明；main `workbench` registration 不再 exclude `all`，能够处理 ordinary all fan-out，且 month refresh publish/complete/source-version current guard/下游 fan-out 不回归。不得新增 event、worker、兼容 handler、queue rewrite、projection 或 all materialization；不得改其他 read model scope/DTO，不得 drain queue、停 worker、部署或执行 Git 操作。先读取 read-model/runtime-worker boundary 与 governance，检查共享工作树中 worker/registry 的其他 thread 修改并做最小兼容 diff。完成后运行 registry/deploy/queue/refresh/relation/architecture 回归和 whole-repo 零引用扫描，再生成 cache-warmer 删除 prompt。

完成证据：

- runtime registry 已删除独立 aggregate registration，main `workbench` 不再排除 `all`；独立 env example 与 deploy migration/drain helper 已删除，激活时仍由 registry 白名单收敛未登记实例。
- `scope_key=all` 现在只通过既有 `ReadModelRefreshGateway.enqueue_many(...)` 投递月份 shards，传播 tenant、priority、trace 和显式 `force_refresh`，fan-out 接受后按 event source version 完成 durable command；不构建或发布全局 generation。
- 删除 refresh service 的 aggregate-only 状态机、SQL projection 的全局发布函数、runtime queue aggregate helper、relation producer 的额外 aggregate 投递和 rehydrate 的 materialized-all builder；已知月份的 relation 只投递月份，月份发布后的 Cost Statistics fan-out 保持。
- 当前 read-model/worker/governance/测试文档改为单 lane 合同；历史生产 repair 报告明确标记归档。运行时代码、脚本和部署面只剩两条负向删除 guard 引用旧 worker 名称。
- 验证：Prompt 13 定向 registry/deploy/queue/relation/refresh 测试 106 passed；扩大到 Workbench SQL + worker/queue/relation 时在进入架构 allowlist 前 289 passed。全量架构 guard 被共享工作树另一个 Cost Statistics thread 尚未同步的 direct-fresh/direct-enqueue allowlist 阻挡，失败符号分别位于 `cost_statistics_query_service.py`，与本 prompt 无关且未越界修改。
- Ruff 与旧符号扫描通过；未部署、未接触生产队列、未执行 Git 操作。真实 systemd 收敛和 queue/handler p95 留待统一发布门禁。

## Prompt 14：删除同步 Workbench 首屏 cache warmer

状态：`completed`

目标：只删除 Workbench month generation 发布后的同步 Redis page-cache 预热。保留现有默认首屏 versioned cache 的 query-time read-through（fresh gate 后 cache hit/miss/down 仍回同一 repository cold path）；删除 `WorkbenchGroupsPageCacheWarmer`、同步预热 env 开关、worker construction/injection、refresh service `post_refresh_warmer` 与结果字段，以及只保护预热实现的测试和当前文档。发布成功不再被额外 Redis/page SQL I/O 延长。

停止条件：先用 CodeGraph callers/impact 与全仓文本扫描证明 warmer 只由 Workbench refresh worker 使用；删除后 month publish、Cost Statistics fan-out、dirty source-version completion 与 query-time versioned cache 合同保持。不得删除 `WorkbenchGroupsPageCache`/cache key/read-through，不得新增 async warmer、event、worker、cache 层、fallback 或兼容开关；不得修改其他页面缓存。定向测试覆盖 publish 成功不调用 page query/Redis、默认 cache hit/miss/down 和 worker wiring；同步 docs/env/monitoring，完成 whole-repo 零引用、Ruff/docs/diff 门禁。不得部署、操作生产或执行 Git。

完成证据：

- 删除 `WorkbenchGroupsPageCacheWarmer`、同步 env gate、worker 构造/注入、refresh service `post_refresh_warmer` 与 `cache_warmup` 结果字段；没有新增异步 event、worker 或缓存层。
- `WorkbenchGroupsPageCache` 的 key/schema/TTL 纯函数与 `WorkbenchQueryFacade` 默认首屏 versioned read-through 完整保留；cache miss/down 仍走同一 fresh SQL repository cold path，Redis 不是 freshness owner。
- 新回归证明 month publish 不调用 page query、按 source version 完成 dirty scope且不返回 warmup 字段；静态删除 guard 锁定 class/env/injection 不得回流。旧符号仅剩该负向 guard 字符串。
- 文档明确 worker 不承担 page SQL/Redis I/O，监控只观察 query owner 的 fresh-gated cache。
- 验证：定向 29 passed；扩大 Workbench query/SQL/worker registry/deploy 回归 230 passed、48 subtests passed；目标 Ruff 通过。未部署、未访问真实 Redis/worker、未执行 Git。

## Prompt 15：删除 repository legacy full-view adapter

状态：`completed`

目标：只删除没有生产调用者的 `PostgresReadModelRepository.get_workbench_view(...)` 及其专属 snapshot/materialized-all/rows-page helpers、`Application._get_persisted_workbench_read_model(...)`，并删除只保护这些兼容 DTO 的 fake connections/tests。当前 Workbench initial/summary/groups/group detail/row detail/search/ignored/Batch Accounting 专属 repository I/O 保持不变。

停止条件：先确认 helper 调用边界，保留仍被 current groups/detail 使用的 `_materialize_workbench_group_payloads(...)`，不能机械删除结构化 member materialization。当前代码/测试/长期事实文档对 `get_workbench_view` 和 `_get_persisted_workbench_read_model` 零引用；新增负向 guard 防止兼容 full-view adapter 回流。不得触碰 Cost shared worktree、on-demand/raw assembler（下一 prompt 单独处理）、projection schema、API DTO、cache、worker 或其他页面。完成后运行 Workbench SQL/query/current consumer 回归、Ruff/docs/diff 与零引用扫描；不得部署或执行 Git。

完成证据：

- 删除 `get_workbench_view(...)`、materialized-all/full snapshot adapter、generic rows-page SQL 和无调用 `_get_persisted_workbench_read_model(...)`；current initial/summary/groups/group detail/row detail/search/ignored/Batch Accounting 窄 I/O 未变。
- 保留 `_materialize_workbench_group_payloads(...)`，因为 current groups/detail 仍用它从同 generation 的结构化 membership + row owner 组装最终 DTO。
- 删除六个只保护 legacy full-view DTO 的 SQL tests/fakes；新增负向 guard。长期 persistence/read-model 文档已切到 facade + 窄 repository owner，并删除 materialized-all 事实。
- 验证：WorkBench SQL/query、Search、Batch Accounting 与删除 guard 235 passed、10 subtests passed；目标 Ruff 通过；旧符号只剩负向 guard。未触碰 Cost shared files、未部署、未执行 Git。

## Prompt 16：删除 Application on-demand full build 与 raw assembler

状态：`completed`

目标：删除生产调用者已为零的 `Application._get_or_build_workbench_read_model(...)`、`_build_raw_workbench_payload(...)`、`_workbench_raw_payload_assembler(...)`、`WorkbenchRawPayloadAssembler` 与只服务该 on-demand cache gate 的 `WorkbenchCacheReadPayloadHelper`。同步删除其 import/cache helper/wiring、专属单测和 extraction guard。保留 current SQL projection、query facade、canonical row resolver、relation grouping，以及仍有独立 current caller 的 OA parser/version/relation helpers。

停止条件：用 CodeGraph callees 和文本扫描逐项区分 exclusive helper 与 shared helper；不得因名字含 raw 就机械删除仍被 current OA/canonical write/repair 调用的模块。重要 action 业务测试必须迁到 current canonical row resolver/relation service fixture；只保护旧 GET/full cache/Mongo fallback/visibility DTO 的测试直接删除，不能用 test compatibility facade 恢复生产方法。当前 runtime/test/docs 对三个 Application old methods、两个旧 module/class 零引用；负向 guard 锁定删除。共享 Cost tests 若仍引用 on-demand method，必须先确认其 legacy service 已无生产 owner，再在不覆盖另一 thread Cost 改动的前提下单独收口。不得新增 projection/adapter/fallback，不部署、不执行 Git。

完成证据：

- 删除 on-demand getter、raw payload builder/assembler、cache-read helper，以及只服务 cache rebuild 的 OA invoice-offset repair helper；current invoice-offset relation builder 改为直接复用已有附件匹配函数，没有新增替代层。
- Cost API 的共享 dirty 测试文件只做精确迁移：relation fixture 直接写 active relation，并用 current identity arbitration + relation grouping 构造测试输入；保留另一 thread 新增的分页/freshness/ETag 修改。19 个 Cost API tests 通过。
- Workbench 写入 characterization 不再 GET 本地整页 API，改为 canonical query rows；generation precondition 在该 business/UOW 测试文件中显式隔离，真实 400/409/503/fresh 合同继续由 query facade、routes、auth-context tests 负责。46 passed、3 subtests passed。
- 删除仍保护旧 GET/cache/Mongo/row-detail fallback 的 V2 tests；保留的 current V2 tests 43 passed。ETC tests 改断言 relation fact，122 passed、4 skipped；SQL projection 既有 ETC summary tests继续保护 summary/detail payload。
- 新增 personal-advance canonical row failure tests；`tests/test_workbench_auth_context_idempotency.py` 32 passed、2 subtests passed。目标 Ruff 与删除 guard 通过。
- whole-repo 运行时扫描对 on-demand/raw/cache 旧符号为零；当前命中只允许负向 guard和历史实施记录。未部署、未执行生产验证或 Git。

## Prompt 17：删除 raw/on-demand 失活后的 exclusive helper cascade

状态：`completed`

目标：对 Prompt 16 删除后失去生产调用者的 Workbench live/OA/retained-all/selected-scope raw payload builders 及其 Application wrappers 做一次结构化 dead-code sweep。先删除已由 CodeGraph 证明仅互相调用或仅被测试调用的 builder/wiring/tests，再沿 callees 逐项判断 raw mutation、OA attachment repair、supplemental retention、live merge、group-row payload、grouped retention 和 ETC summary DTO helper；只删除 production caller 为零的节点。保留 settings reset 仍调用的 retention month/date parser、current SQL projection、canonical resolver、relation command/grouping service、OA sync/attachment promotion 和 ETC relation cleanup。

停止条件：每个被删 symbol 都有 CodeGraph caller/whole-repo text 证据；不能因为名称相似删除 current SQL projection 或 write repair 所需逻辑。运行时代码不存在 test-only service module/wrapper/instance cache；对应 extraction guard 改为负向 deletion guard，旧 tests 删除而不是复制兼容实现。完成 current Workbench SQL/query/write、ETC、settings reset、OA projection、boundary guard、Ruff/docs/diff 验证。不得触碰另一 thread 的 Cost shared files，不部署、不执行 Git。

完成证据：

- CodeGraph caller 与 whole-repo 扫描证明被删 builder/executor/port 只由自身 Application wrapper 或旧实现测试引用；删除后 server 的 Workbench 相关 method 单引用盘点已无本链残留。
- 删除 24 个只服务旧 full/raw payload 的 service modules，覆盖 live/OA/retained/selected-scope builder、canonical/raw repair、live merge、group-row payload、OA invoice-offset read-time sync/desired/repair executors 与其 relation read ports；对应实现细节测试和 extraction guard 同步删除。
- 删除 server 中失活的 raw/full wrapper、instance cache、OA attachment raw row-index surface、read-time relation repair、旧 ETC summary DTO 拼装、grouped payload 二次 override/tag、legacy row-detail/action/persistence/matching compat helpers；`WorkbenchPayloadRelationReadPort` 缩到当前 canonical row resolver 实际需要的单行 relation read。
- `WorkbenchOaAttachmentContextRowIndex` 保留确认关联仍使用的 grouped-generation context I/O，删除 raw payload methods并补 grouped index test；retention parser 保留 Settings reset 唯一 `parse(...)` I/O并新增窄边界 guard。
- 删除零生产调用的 `WorkbenchApiRoutes` read compat class、server construction 和测试 fixture；`routes_workbench.py` 当前 owner inventory 改为 `WorkbenchReadApiRoutes`，row detail guard 只允许 query facade -> active generation repository，不再要求已删除 fallback。
- 保留 current `WorkbenchSqlProjectionBuilder` 的 ETC summary row、`_etc_invoice_summary_row_id(...)` relation cleanup id、SQL projection、canonical resolver、relation command/grouping、OA projection/promotion 与 Settings reset month/date logic；没有新增替代层、projection、worker、cache 或 fallback。
- 验证：Prompt 17 功能回归 455 passed、4 skipped、18 subtests；完整 `tests/test_platform_runtime_boundary_guards.py` 202 passed、34 subtests；legacy route 删除后的 Workbench V2 + Cost API 51 passed。目标 Ruff 全部通过。
- 文档：reconciliation-workbench boundary/implementation 与 workbench-relations implementation 已记录旧链删除和保留的窄 I/O；历史记录不改写，但新增当前条目明确取代旧 fallback/executor 描述。
- 七类测试判断：service/read-model、API contract、read-model/generation、跨模块 ETC/Settings/OA、existing regression 适用并已覆盖；本轮未改前端用户交互、业务匹配规则或部署，所以 business-core 新规则、frontend 与生产 E2E 不新增，最终前端/E2E 回归由后续 prompt 统一执行。

## Prompt 18：Import Workflow 解除 Workbench 首屏刷新探测

状态：`completed`

目标：只修改导入页前端及其直接测试，删除 `ImportWorkflowPage.refreshWorkbenchStatus(...)` 在 `operationBarrierTargets` 为空时调用 `fetchWorkbenchInitialPage(...)` 的 fallback。存在 targets 时继续使用既有 `waitForOperationFreshness(...)`；没有 targets 表示后端未声明需要等待的 read model，导入反馈直接完成，不能读取关联台页面来猜刷新完成。

停止条件：Import Workflow production code 不再 import/call Workbench initial-page API；有 targets 的等待、无 targets 的零 Workbench 请求、导入完成/错误反馈和现有 settings load 行为均有组件回归。不得修改后端 import DTO、operation barrier、Workbench API/page、其他页面 read model 或新增 target 推断/fallback。目标前端测试、build、Ruff/TypeScript 与 docs impact 判断通过；不得部署或执行 Git。

完成证据：

- `ImportWorkflowPage` 删除 `fetchWorkbenchInitialPage` import、`WORKBENCH_VIEW_MONTH` 和空 targets fallback；完成回调改为 `completeImportFeedback(...)`：targets 为空立即 success，非空只调用现有 `waitForOperationFreshness(...)`。进度文案改为“受影响页面”，不再把所有 import targets 误称为关联台刷新。
- `apiMock` 仅增加可选 confirm target envelope；deterministic Browser fixture 使用后端现有 `operation_barrier_targets` 合同。没有修改 import DTO、barrier API、Workbench page/API、settings load 或其他页面 read model。
- `ImportCenterPage.test.tsx` 新增两条组件回归：空 targets 零 barrier/零 Workbench 请求；显式 targets 请求一次 barrier、body 精确且零 Workbench 请求。整文件 24 passed。
- 银行流水与发票 Browser E2E 的成功链改为等待 `POST /api/operation-barrier/status`，并断言 `GET /api/workbench/summary` 为零；取消、preview stale、confirm failure 同时断言零 barrier/零 Workbench 页面请求。两份 spec 共 13 passed。
- `npm run build` 通过；只有既有 HeroUI CSS minify 与 chunk-size warning。`bash scripts/verify.sh docs`、目标 `git diff --check` 通过。
- 银行流水/发票的 boundary、state、E2E spec/coverage、tests 与 implementation notes 已同步为“只等待后端声明 targets；空 targets 直接完成；禁止页面读取 Workbench 猜状态”。
- 七类测试判断：frontend component、API target mapping、read-model/barrier 交互、跨模块 Browser flow、existing regression 适用并已覆盖；本轮未改业务规则、后端 service/repository、worker 或部署，因此 business-core、后端 service 新用例和生产 worker 验证不适用。未部署、未执行 Git 操作。

## Prompt 19：删除冗余 Workbench summary HTTP 合同与旧 manifest port

状态：`completed`

目标：最终页面首屏已由单次 `GET /api/workbench` 返回 summary + paired/unpaired first page，因此删除仍独立暴露的 `GET /api/workbench/summary` HTTP/facade/route/server handler/metric owner，并把仓库内 local runtime、convergence、HTTP SLO probe、mock/tests 和当前事实文档迁到 initial-page 合同；同时从 `read_model_manifest.py` 删除已经不存在的 `get_workbench_view` repository port。保留 `PostgresReadModelRepository.get_workbench_summary(...)` 作为 combined initial-page 同快照内部 I/O，不删除 summary 表或统计语义。

停止条件：生产 route/facade/server、运行脚本、current tests、mock 与当前事实文档不再把独立 summary endpoint 当运行合同；known repository consumers 全部迁到 `GET /api/workbench` 或合法 `/groups`，外部 consumer access-log 检查明确留在 deferred unified-release gate，不能为未知外部调用保留兼容 route。manifest 只声明实际存在的 repository ports；initial-page summary correctness、freshness/version/cache、operations metrics、probes 和其他页面回归保持。不得删除 repository summary I/O、修改 read model schema/worker、增加 redirect/fallback/feature flag、访问生产、部署或执行 Git。

完成证据：

- 删除 `server.py` 的独立 summary HTTP dispatch/handler、`WorkbenchReadApiRoutes.summary(...)` 和 `WorkbenchQueryFacade.summary(...)`；operations metric owner、SLO probe、local runtime 与 generation convergence 工具全部迁到 combined initial。没有 redirect、fallback、feature flag 或第二套 DTO owner。
- `read_model_manifest.py` 删除已不存在的 `get_workbench_view`，增加实际公开的 `get_workbench_initial_page`；`get_workbench_summary` 及 summary 表保留为 combined initial 同快照内部窄 I/O。
- `check-local-runtime.sh` 从一次 combined initial 读取 summary/paired/unpaired；`validate_workbench_generation_convergence` 先读 initial version，再以 `expected_read_model_version` 固定 groups。新增窄单测锁定该顺序并禁止旧 endpoint。
- 当前 API、app architecture、module boundary、runtime call chain、local development、backend README 和 monitoring 已改为 combined initial 事实；明确历史 query plan/state log/日期报告保留为归档。当前运行树的旧 path 字面量只剩负向 deletion guards。
- Browser E2E 首次暴露共享 mock 仍缺 `read_model_version`，新前端门禁因此正确禁用确认关联。本轮没有绕过门禁；将 `legacyWorkbenchPayload` 收口为 `workbenchInitialPayload`，并让 initial/groups mock 在变更前后返回一致且可切换的 generation version。
- 验证：独立 route/facade/SQL/runtime 组 444 passed；probe/metrics/manifest/guard/convergence 组 255 passed；前端 5 文件 151 passed；三类 import E2E 18 passed，Workbench relation fan-out 在修正 mock 后 1 passed；`npm run build`、Ruff、`bash scripts/verify.sh docs`、shell syntax、py_compile 和目标 `git diff --check` 通过。构建只有既有 HeroUI CSS 与 chunk-size warning。
- 七类测试判断：service/read-model、API contract、frontend interaction、跨模块 Browser flow 和 existing regression 适用并已覆盖；本轮不改业务规则、projection/worker 或持久化 schema，所以 business-core 新规则与 background-job 新行为测试不适用。未部署、未访问生产、未执行 Git。

## Prompt 20：可丢弃 PostgreSQL 受控性能与查询计划证据

状态：`completed`

目标：使用本机已运行的 PostgreSQL 17 创建一个名称明确含 `test` 的临时可丢弃数据库，应用当前 migrations，以合成但结构真实的 active month generations 构造至少 paired/unpaired 各 200 groups 的受控数据集。直接调用当前 `PostgresReadModelRepository` 和现有 HTTP/facade 可拆分边界，采集 combined initial cold/hot、search/filter/page、group/row detail 的样本数、p50/p95/p99、statement 数、payload bytes 与 `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)`。验证 Redis unavailable 走同一 SQL cold path，不需要真 Redis；以既有 Browser latency attachment/React tests 作前端受控证据，不伪造生产对等数据或 production-passed 结论。

停止条件：临时 DB 必须在本 prompt 结束前删除，禁止连接任何不含 `test` 的 DB，禁止加载生产 token/数据、运行生产 smoke、部署或操作 worker/queue。优先使用现有 migration helper、repository 和内嵌一次性采样命令；不为性能证据增加 runtime tool、telemetry service、projection、index、cache 或依赖。如果 cold p95 超过 500ms，只用 EXPLAIN 定位瓶颈并停下报告，未经用户授权不实现索引。记录环境差异（合成数据、无并发业务负载、未经 Nginx/真 Redis/生产网络），不能把形状测试冒充 SLO。完成后根据实测结果决定下一个唯一 prompt 是性能缺口分析还是最终全量回归/交接收口。

完成证据：

- 在本机 PostgreSQL 17.10 创建 `fin_ops_workbench_perf_test_codex04_20260716`，应用当前 0001–0107 migrations，构造 2 个 active month shards、400 logical groups（paired/unpaired 各200）、800 canonical/group rows 和同 generation summary/stats。测量结束已 `dropdb`，并查询 `pg_database` 确认删除。
- correctness：combined initial 返回 paired/unpaired 各200 groups，summary counts 同为 200，initial/freshness 均为 fresh；search、group detail、row detail 均保持同一 composed generation-set version。
- 单并发、PG buffer 不强制清空的受控样本：initial first request 156.807ms；initial warm 60 样本 p50/p95/p99 = 75.432/89.493/251.018ms，payload 345,120 bytes；page 2 p95/p99 = 21.069/21.344ms；search = 28.559/41.024ms；group detail = 4.133/4.432ms；row detail = 1.762/2.143ms；freshness = 0.558/1.230ms。该结果只是 local implementation evidence，不是 production-passed。
- EXPLAIN；canonical summary execution 18.100ms、shared hits 17,514、无 read/temp spill；400 可见组成员物化 9.384ms、shared hits 15,321、无 read/temp spill；all groups page 2.823ms。没有证据触发 index 升级门，因此不新增索引。
- 重要新缺口：默认 combined initial 虽然延迟形状通过，却执行 20 statements（含 2 条 transaction-local setup）。其中 generation/source/status 被 summary、paired、unpaired 重复读取，两区 count/page/member 分别往返；本机低延迟掩盖了这个生产尾延迟风险。
- 局限：数据是合成结构不是生产基数，没有混合业务并发、Nginx/网络/真 Redis/browser pipeline；为不影响其他 thread 未重启 PostgreSQL 清 shared buffers；实施前未保存同数据集 baseline，不伪造 before/after。这些差异和最终生产矩阵一并留在统一发布门。

## Prompt 21：收敛 combined initial 重复 DB 往返

状态：`completed`

目标：只在 `PostgresReadModelRepository.get_workbench_initial_page(...)` 及其现有私有 SQL/helper 边界内收敛默认 `month=all` combined initial 的重复 I/O。一次读取 active month generation set/source versions/freshness context，summary 继续使用同一 canonical-owner SQL owner，paired/unpaired 的 total/row counts、各首200 page 和 selected members 应按区批量读取，禁止再两次完整调用公开 `get_workbench_groups_page(...)`。目标是默认 all-scope initial 不超过 10 statements（含 `SET TRANSACTION` 与 transaction-local timeout），且不复制 canonical owner 规则。

停止条件：不新增 projection/table/index/cache/worker/gateway/dependency/public repository port，不改独立 `/groups`、group detail、row detail 的查询合同或其他页面。优先抽出小而具体的私有 initial batch helper，不建 query-plan class、generic executor 或第二 SQL owner；当 paired/unpaired 查询含搜索/筛选时必须保持现有结果和 version 合同，不得用快路径忽略条件。先以 fake-connection 形状测试锁定默认路径 statement 上限、同快照、计数/页面/成员一致，再重建可丢弃 DB 复跑 Prompt 20 的 correctness/延迟/EXPLAIN。如果为达到 statement 目标必须引入通用查询抽象或复制大段 filter SQL，停止并报告取舍，不过度设计。不部署、不访问生产、不执行 Git。

完成证据：

- 默认 `month=all` 且两区 query 为空时，`get_workbench_initial_page(...)` 在原有 repeatable-read/read-only 事务内只读取一次 active generation/source context、canonical summary 和 freshness；两区 page 通过一个 window query 读取，两区可见 members 通过一次既有 materializer 批量读取。带搜索、筛选或排序的请求继续走原有 `get_workbench_groups_page(...)`，没有复制或绕过 filter SQL。
- 新路径复用 `_workbench_active_month_groups_sql(...)`、canonical summary、现有 group sanitation/count/summary helper；没有新增 projection、表、索引、缓存、worker、gateway、依赖、public port 或第二 SQL owner。独立 `/groups`、group/row detail 与其他页面合同未变。
- fake connection 回归锁定：同一 generation version、paired/unpaired 各区 totals/row counts/members 一致、一次事务、statement 总数不超过 10、只有一个 combined page query 和一个 combined member query，且不再出现独立 count 或重复 source_versions read。版本漂移的 fail-closed 用例显式走 filtered generic path。
- `tests.test_workbench_sql_runtime`、`tests.test_workbench_query_facade`、`tests.test_workbench_routes` 共 191 passed；目标 Ruff 通过。既有 characterization 会打印一次预期 retention timeout 日志，但 suite 成功。
- 第二个可丢弃 PostgreSQL 17.10 数据库使用同规模 2 shards / 400 groups / 800 rows fixture。correctness 返回 paired/unpaired 各 200、summary counts 一致、fresh、同 version；默认首屏固定 7 statements，语句序列为事务设置 2 条、summary generation context、canonical summary、freshness、combined zone pages、combined members。
- 优化后首请求 89.958ms；补齐 relation_id 使 payload 更接近基线后，60 次样本 p50/p95/p99 = 58.581/70.962/109.974ms，SQL p50/p95/p99 = 45.121/51.408/93.839ms，payload 341,319 bytes。相比 Prompt 20 的 20 statements，往返数精确降低 65%；前后 fixture 非逐字节相同，所以 latency 只作为方向性证据，不宣称严格 A/B。
- EXPLAIN：canonical summary 17.583ms / 17,826 shared hits，combined zone pages 3.823ms / 324 hits，combined members 12.072ms / 23,394 hits；无 disk read 或 temp spill。没有证据触发 index/projection 升级门。
- 临时数据库 `fin_ops_workbench_perf_test_codex04_p21` 已删除并确认不存在。长期 Workbench boundary/implementation notes 已同步。仍未访问生产、部署、操作 worker/queue 或执行 Git。

## Prompt 22：最终全量回归、旧链零引用与延期发布交接

状态：`completed`

目标：只做本 goal 的最终验证与交接，不再主动扩展实现。全仓扫描 legacy Workbench full-payload、on-demand/raw/live/OA builder、aggregate/warmer、独立 summary endpoint、Import Workflow Workbench fallback 等旧运行链，允许历史归档和负向 deletion guards，禁止当前 production runtime/current docs/mock/probe 回流。运行 Workbench backend、read-model/worker/consumer、frontend、关键 Browser flow、build、Ruff、docs 和 diff 校验；对共享脏工作树中的非本 goal 失败精确归因，不修改其他 thread。

停止条件：本 goal 可归属测试与文档全部通过；旧运行链只剩明确 allowlist；受控测试数据库全部删除；七类测试覆盖、性能证据边界、共享文件重叠与剩余风险均记录。发布、生产 token、production smoke/性能、worker/queue 操作和所有 Git 操作继续禁止。统一发布交接必须明确外部旧 summary consumer access-log 门、合并后 full regression、备份、旧 all-lane drain、`deploy-oa.sh`、canary、真实基数/并发 SLO、隔离性和回滚门；这些只记录，不执行。

完成证据：

- 最终全仓后端回归执行 4073 个测试，34 skipped；只剩 3 个失败，分别是 Pending Invoice lifecycle、Cost Statistics explorer API probe 和共享 read-model allowlist，均对应其他并行 thread 的当前修改。Workbench、本 goal 改动及其上下游定向回归失败为零。没有为让全仓表面变绿而修改其他 thread。
- 全量后端暴露的旧本地 Workbench fixture 已迁到 test-only canonical grouping + generation freshness gate；没有恢复本地 `/api/workbench` full payload、runtime fallback 或第二个 DTO owner。定向 50 个 Workbench/import/no-OA/turnover/write/version 用例中，目标链全部通过；唯一非目标失败是当时尚未完成的 Cost Statistics probe。
- `bash scripts/verify.sh frontend` 退出码 0：前端全量测试与生产 build 通过；仅有既有的 500kB chunk warning。
- 首轮 `bash scripts/verify.sh e2e` 为 171 passed / 8 failed。根因是浏览器 mock/断言仍使用旧分区首屏：写后强制检查 `GET /api/workbench/groups`、combined initial 缺少分页/generation metadata、fresh refetch error 只挂在旧 groups handler，以及错误允许 non-fresh generation 写入。只迁移测试合同和 mock，不改生产链路；专项复跑 26/27，加最后一个分页语义修正后 1/1 通过。
- 最终 `bash scripts/verify.sh e2e` 为 179/179 passed（7.5m），覆盖 Workbench confirm/withdraw/exception/ignore/network recovery/non-fresh gate/large page、导入、Search 下游、Bank Details、Pending Invoice、Cost Statistics、Tax Offset、OA Pending、权限和其他页面隔离。
- `bash scripts/verify.sh lint`、`bash scripts/verify.sh docs`、`git diff --check` 全部通过。PostgreSQL 查询确认不存在 `fin_ops_workbench_perf_test_codex04%` 临时数据库。
- whole-repo 旧链扫描确认 `backend/src`、`web/src`、`deploy`、`scripts` 对 legacy provider/API/raw assembler、on-demand full builder、旧 repository view、`/api/workbench/summary`、`workbench-aggregate`、cache warmer 与 aggregate publish helper 为零引用。测试中只保留负向 deletion guards；文档命中只位于本 Phase 计划/执行记录、带日期的 implementation notes、migration/refactor prompt/state log 与已显式标记“历史发现归档”的 query plan。
- 当前保留的 `WorkbenchQueryService` 与 `LiveWorkbenchService` 不是页面旧链：前者仍为 generation/canonical local source，后者仍提供写链所需的窄 row resolver；它们不拥有 `GET /api/workbench` combined initial，也不构成 fallback。没有为追求字面零符号而删除当前独立职责。
- 本 goal 没有执行部署、生产 token、生产访问、worker/queue drain/stop、Git 暂存/提交/push/merge/rebase。`deployment_status: deferred_by_user`。

七类测试闭环：

1. 业务核心：canonical owner、relation/group 分区、cross-month/duplicate/invalid owner、write version/freshness precondition。
2. Service：initial snapshot、query facade、Redis hit/miss/down、timeout、Search/Batch/Settings/ignored 窄 I/O、worker fan-out。
3. API：combined initial/query validation、groups/detail expected version、action 400/409/503、权限与错误 envelope。
4. Read model/cache/worker：generation 原子激活、fresh/stale/refreshing、cache version、main worker all fan-out、旧 aggregate/warmer deletion guards。
5. 前端：loading/empty/error/non-fresh、版本切换清理、写入禁用、分页/筛选/detail、失败恢复。
6. E2E：179 个全站浏览器用例覆盖关键 relation write-to-visible、导入与下游 fan-out。
7. 现有功能回归：Search、Batch Accounting、Settings、Imports、Bank Details、Pending Invoice、Cost Statistics、Tax Offset、OA Pending、Turnover、权限/导出及旧链零引用。

延期统一发布门：

1. 等其他 thread 全部完成，形成单一 release candidate；逐块解决共享文件冲突并复跑合并后的 backend/frontend/E2E/lint/docs，当前 3 个他线程后端失败必须由对应 owner 收敛。
2. 核查至少 35 天生产 access log（保留不足则使用全部窗口），确认没有外部 `/api/workbench/summary` 或旧 full-payload consumer；若有，先迁移明确 owner，不恢复 hidden fallback。
3. 执行备份与恢复点检查；短暂静默旧 aggregate producer，使用既有 queue/runtime ops 将旧 all-lane pending/processing/failed drain 到零，不新增 event rewrite 工具。
4. 使用 `./scripts/deploy-oa.sh` 一次发布 frontend/backend/worker registry 完整 bundle；确认旧 `workbench-aggregate` 已由 deploy convergence 停用，main Workbench worker ordinary `all` fan-out 正常。
5. canary 验证 combined initial、groups/detail、write generation barrier、SSE 自动替换、409/503、权限和回滚入口；任何 correctness/freshness/隔离失败都停止放量。
6. 通过 `scripts/with-production-admin-token.sh <command>` 在授权窗口执行真实基数和混合并发的 cold/hot/Redis-down/search/page/detail/write-to-fresh/Nginx/browser矩阵，记录 p50/p95/p99、statements、EXPLAIN buffers、payload、DB pool、Redis、worker、其他页面 p95；不得打印或提交 token。
7. 验证第 8 节生产 SLO、statement timeout=0、其他页面 p95 回归不超过 5%，并完成监控观察与完整 release bundle 回滚演练后，才能标记 `production-verified`。
