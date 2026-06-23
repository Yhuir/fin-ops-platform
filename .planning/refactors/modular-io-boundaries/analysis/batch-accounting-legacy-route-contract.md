# Batch Accounting Legacy Route Contract

**日期:** 2026-06-23
**Boundary:** `batch-accounting:legacy-route-contract`
**状态:** `closed-autonomous`
**范围:** 增加批量账务 route handler 静态边界守卫；不改 runtime 行为、不改 API shape、不改业务语义、不改 SQL/read model/worker/前端、不进入 Go/Fiber 或 Go Worker。

## 实现前分析

本轮审阅了批量账务模块 README、状态机、测试矩阵、实施记录、Workbench 模块文档、前序 Workbench amount-check analysis、全局 roadmap 与 impact/test gates。CodeGraph 和代码搜索确认当前批量账务关键边界：

- `GET /api/batch-accounting` route 调用 `BatchAccountingService.build_payload(...)`，并以 `use_sql_read_model=True` 注入 SQL read model loader。
- `POST /api/batch-accounting/submit` route 只做 session、JSON、DTO、错误映射和写后 lifecycle/read model schedule；业务写入委托 `BatchAccountingService.submit(...)`。
- `POST /api/batch-accounting/{relation_id}/withdraw` route 只做 session、JSON、DTO、错误映射和写后 lifecycle/read model schedule；业务写入委托 `BatchAccountingService.withdraw(...)`。
- `BatchAccountingService` 已有测试和静态 guard 防止 submit/withdraw/repair 直接回退到 `WorkbenchPairRelationService` 写 relation。

本轮选择补齐 route 层污染防线：新增静态 guard，禁止 batch-accounting route handler 在 GET 路径执行 legacy repair、relation command/direct pair write、dirty/outbox/read model schedule；禁止 submit/withdraw route handler 绕过 `BatchAccountingService` 直接调用 relation write internals。route 允许保留 HTTP/session/DTO/error mapping 和写后 lifecycle/read model scheduling。

## 模块 IO 合同

| 项 | 合同 |
| --- | --- |
| 输入 | GET query: year/bank_year/oa_year/bucket/page 参数；submit/withdraw JSON body + OA session headers。 |
| 输出 | GET 返回批量账务 DTO + `workbench_relation` read model freshness；submit/withdraw 返回 relation mutation result + affected months。 |
| 状态 | 本轮不改变业务/UI/read model/worker 状态；只把 route handler boundary 变成可测试合同。 |
| 事件 | submit/withdraw 成功后仍由现有 route 调用 `batch_accounting_relation_changed` lifecycle。GET 不发事件。 |
| read model contract | GET 通过 `BatchAccountingService` / `WorkbenchRelationReadFacade` freshness 边界读取；GET 禁止同步 repair 或直接 schedule refresh/write。 |
| force refresh contract | 不适用；本轮不新增 force refresh。 |
| operation barrier contract | 不变；前端 submit/withdraw 后仍等待 `workbench_relation` operation barrier。 |
| canonical facts | 批量账务不拥有独立事实源；relation canonical fact 仍由 `WorkbenchRelationCommandService` / relation repository 管理。 |
| shared fact owner | `workbench_relation` 是共享 read model；批量账务 route 不得直接写 relation fact 或 read model fact。 |
| 权限 | submit/withdraw route 必须先走 `_batch_accounting_mutation_session(...)`；本轮不改权限。 |
| 审计 | 不变；relation command/history 和 lifecycle metadata 继续由既有链路负责。 |
| public surface | `/api/batch-accounting`、`/api/batch-accounting/submit`、`/api/batch-accounting/{relation_id}/withdraw` response shape 不变。 |
| internal-only surface | route handler 内禁止 direct relation internals；`BatchAccountingService` 是业务边界。 |
| allowed dependencies | route 可调用 `_batch_accounting_service(...)`、session resolver、JSON loader、error mapper、scope calculation、write后 persist/lifecycle scheduling。 |
| forbidden dependencies | GET route 禁止 repair/write/schedule；submit/withdraw route 禁止 direct `confirm_relation`、`withdraw_relation`、direct pair write fallback 或 repair。 |
| legacy retirement/quarantine | `_repair_batch_accounting_relation_case_ids` 保留为显式 repair path，不允许回到 GET list path；submit route 的 pair snapshot rollback 是 compat-only persistence rollback，不是 canonical write entry。 |
| test contract | `test_batch_accounting_route_handlers_do_not_bypass_service_boundaries` 锁定 route handler 不绕过 service boundary。 |
| docs impact | 更新 batch-accounting tests、implementation notes、state-machine 变更记录；全局状态机定义不变。 |

## 改动前影响分析

### 1. 模块范围

- 目标模块: `batch-accounting`
- 模块类型: 页面模块
- 本次改动类型: static architecture guard + docs/state accounting
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 read model freshness 语义: 否
- 是否改变 read model partition/scope/incremental projection 策略: 否
- 是否改变权限或审计: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. 后端影响

| 层 | 是否影响 | 文件/符号 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| route / HTTP mapping | 是 | `Application._handle_api_batch_accounting*` | route 未来绕过 service 直接 repair/write | 新增静态 guard |
| application service | 否 | `BatchAccountingService` | 已有 command/facade guard 继续保护 | 既有 tests |
| domain service / policy | 否 | 金额、bucket、version、owner policy | 不改行为 | 不适用 |
| repository / SQL | 否 | 无 | 不改 SQL | 不适用 |
| transaction / UoW | 否 | command service / route scheduling | 不改写事务 | 不适用 |
| audit | 否 | relation history/lifecycle metadata | 不改审计 | 不适用 |
| permission | 否 | `_batch_accounting_mutation_session` | guard 确认 mutation route 保留 session gate | 静态 guard |

### 3. read model / worker 影响

| 项 | 是否影响 | 具体内容 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| read_model_key | 否 | `workbench_relation` | 不改 key | 不适用 |
| scope_type/scope_key | 否 | affected months/row scopes | 不改计算 | 既有 tests |
| readiness/freshness | 否 | GET 仍经 facade/service | route 未来直接读旧 relation | 新增 static guard |
| dirty scope / outbox | 否 | 写后 lifecycle/schedule 不变 | GET 不得写 | 新增 static guard |
| worker registry / App Status | 否 | 不改 | 无 | 不适用 |
| Operation barrier | 否 | 前端仍等待 `workbench_relation` | 不改 | 不适用 |
| Redis/RabbitMQ behavior | 否 | 不改 | 无 | 不适用 |

### 4. Legacy 分类

| Legacy path | 当前调用者 | 目标状态 | 删除/隔离证据 | 防污染测试 |
| --- | --- | --- | --- | --- |
| `_repair_batch_accounting_relation_case_ids` | 显式 app repair helper | compat-only explicit repair | 不在 GET route 中调用 | 新 route guard |
| `Application._workbench_pair_relation_service.snapshot()/from_snapshot(...)` | submit route persistence rollback | compat-only rollback | 仅用于 schedule persist 失败回滚，不是 canonical write entry | 本 analysis 记录；service direct-write guards 继续保护 |
| direct relation command/pair write from route | 无合法调用者 | forbidden | route 只能委托 `BatchAccountingService` | 新 route guard |

## State Machine Impact

- 全局工作流状态: `AutonomousContinue`，当前执行状态为 `autonomous-continue-after-workbench-amount-check-query-contract`。
- 选中边界进入前状态: `batch-accounting:legacy-route-contract` 为 `pending`。
- 已审阅状态机文件:
  - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
  - `docs/modules/batch-accounting/state-machine.md`
  - `docs/modules/reconciliation-workbench/state-machine.md`
- 全局状态机定义: definition unchanged。本轮不新增、重命名或改变 workflow state、transition、guard、stop/defer condition 或 completion criterion。
- 模块状态机定义: definition unchanged。本轮新增 route 边界守卫，不改变业务状态、UI 状态、read model 状态、worker 状态、operation barrier 状态、force-refresh 状态、permission 状态或 legacy-retirement 状态定义。
- 成功流转: `pending` -> `closed-autonomous`，自动执行状态更新为 `autonomous-continue-after-batch-accounting-legacy-route-contract`。
- defer/block 流转: 若发现 route 已有 direct write/repair 且无法安全拆除，应记录 `deferred-module-failure`；若需要生产写或敏感凭据，应记录 `needs-human-production-gate`。当前未触发。
- 完成时必须更新: 本 analysis、`tests/test_platform_runtime_boundary_guards.py`、batch-accounting tests/implementation notes/state-machine、`autonomous/STATE.md`、`autonomous/MODULE-QUEUE.md`、`autonomous/JOURNAL.md`、`autonomous/NEXT-PROMPT.md`。

## 七类测试映射

| 类别 | 是否适用 | 本轮计划 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改金额、bucket、version、状态转换或权限判断。 |
| 2. Service-layer tests | 适用 | `test_batch_accounting_route_handlers_do_not_bypass_service_boundaries` 新增 static route/service boundary guard，防止 route 绕过 service boundary。 |
| 3. API contract tests | 间接适用 | 不改 API shape；既有 batch API tests 继续保护 GET/submit/withdraw。 |
| 4. Read model/cache/background job tests | 间接适用 | guard 确认 GET route 不写 read model schedule/repair；既有 relation facade tests 继续保护 freshness。 |
| 5. Frontend component and interaction tests | 不适用 | 无前端变化。 |
| 6. End-to-end business-flow integration tests | 不适用 | 不触发真实 submit/withdraw 流程变化。 |
| 7. Existing feature regression tests | 适用 | 运行 batch accounting targeted API/static guards，必要时 app check/docs check。 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮是静态架构守卫。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- 敏感凭据处理: 不读取、不记录凭据。

## 后续边界

下一步推进 `server-py:route-owner-inventory`：

- 聚焦 `server.py` 残留 route owner inventory 和少量静态守卫。
- 不做大规模 route 拆分，不改变业务语义，不进入 Go/Fiber 实现。
