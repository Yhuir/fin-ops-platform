# Server.py Route Owner Inventory

**日期:** 2026-06-23
**Boundary:** `server-py:route-owner-inventory`
**状态:** `closed-autonomous`
**范围:** 增加 `server.py` 与已拆分 `routes_*.py` 的 route owner inventory 静态守卫；不拆分 `server.py`，不改 runtime 行为，不改 API shape，不改业务语义，不改 SQL/read model/worker/前端，不进入 Go/Fiber 或 Go Worker。

## 实现前分析

本轮审阅了前序 `batch-accounting:legacy-route-contract` analysis、当前状态审计、路线图、影响测试闸门、运行时归属文档和模块索引。CodeGraph 指向 `Application` 仍是主要 route dispatch/依赖组装中心，且当前已有多个 route owner module:

- `routes_bank_details.py` / `BankDetailsApiRoutes`
- `routes_cost_statistics.py` / `CostStatisticsApiRoutes`
- `routes_etc.py` / `EtcBusinessBatchApiRoutes`
- `routes_no_oa_bank_batches.py` / `NoOaBankBatchApiRoutes`
- `routes_oa_pending_payments.py` / `OaPendingPaymentApiRoutes`
- `routes_output_invoice_collections.py` / `OutputInvoiceCollectionApiRoutes`
- `routes_pending_invoices.py` / `PendingInvoiceApiRoutes`
- `routes_tax.py` / `TaxApiRoutes`
- `routes_turnover_ledger.py` / `TurnoverLedgerApiRoutes`
- `routes_workbench.py` / `WorkbenchApiRoutes`

现状不是从零开始：多个模块已经由 route module 承接业务/查询入口，`server.py` 多数保留 HTTP path dispatch、session/json/error mapping、依赖组装和少量 legacy handler。风险在于后续修改可能新增 `routes_*.py` 却没有接入 `server.py` factory，或让既有 route module handler 回退成 `server.py` 私有业务逻辑，重新扩大中心文件职责。

本轮选择一个窄切片：为已存在的 route module 建立静态 inventory guard。该 guard 不要求一次性拆分所有 handler，也不强制把尚未迁移的 legacy handler 迁出；它只证明每个已登记 route owner module:

1. 文件存在。
2. class 存在。
3. `server.py` 从对应 module 导入 owner class。
4. `server.py` 有明确 accessor/factory 或初始化属性承接该 owner。
5. 对应 handler 中至少出现一次 route owner accessor/attribute 委托。

实现结果：新增 `test_server_route_owner_inventory_stays_registered`，并在 `docs/app-architecture/runtime-and-ownership.md` 的 legacy 边界小节登记该 guard。运行时行为未变。

## 模块 IO 合同

| 项 | 合同 |
| --- | --- |
| 输入 | `server.py` route dispatch、已存在 `routes_*.py` owner module、静态 AST/source guard。 |
| 输出 | 失败即测试报出缺失 owner/import/factory/delegate；成功不改变 runtime payload。 |
| 状态 | 不改变业务/UI/read model/worker 状态；只把 route owner inventory 变成可测试合同。 |
| 事件 | 不新增事件。 |
| read model contract | 不改变；本轮只保护 route owner，不触发 refresh。 |
| force refresh contract | 不适用。 |
| operation barrier contract | 不适用。 |
| canonical facts | 不改变任何 canonical fact owner。 |
| shared fact owner | 不改变共享事实源；route owner module 不因此获得事实源写权限。 |
| 权限 | 不改变权限；route module 既有 session/permission 调用保持原状。 |
| 审计 | 不改变审计。 |
| public surface | HTTP path、method、response shape 不变。 |
| internal-only surface | `server.py` 仍是 dispatch/assembly；route owner module 是对应页面/API 的 public handler owner；业务 internals 仍归 service/repository。 |
| allowed dependencies | `server.py` 可 import route owner class、构造 owner、在 `_handle_api_*` handler 中委托 owner method。 |
| forbidden dependencies | 已登记 route owner 不得无 owner/factory；新拆 route module 不得只放文件而不接入 `server.py`；本轮不新增 direct write/read model refresh 例外。 |
| legacy retirement/quarantine | `server.py` residual route handler 继续作为 legacy/shared boundary，被本 analysis 登记为后续拆分对象；本轮不删除。 |
| test contract | `test_server_route_owner_inventory_stays_registered` 锁定 route module/import/factory/delegate inventory。 |
| docs impact | 更新运行时归属文档；全局/模块状态机定义不变。 |

## 改动前影响分析

### 1. 模块范围

- 目标模块: `server-py` shared boundary
- 模块类型: 共享边界
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
| route / HTTP mapping | 是 | `server.py` route owner imports/factories/delegates | route owner 回退到中心 handler 或新 route module 未登记 | 新增静态 guard |
| application service | 否 | 无 | 不改 service | 不适用 |
| domain service / policy | 否 | 无 | 不改业务规则 | 不适用 |
| repository / SQL | 否 | 无 | 不改 SQL | 不适用 |
| transaction / UoW | 否 | 无 | 不改写事务 | 不适用 |
| audit | 否 | 无 | 不改审计 | 不适用 |
| permission | 否 | route module 既有 session/permission mapping | 不改权限 | 既有 tests |

### 3. read model / worker 影响

| 项 | 是否影响 | 具体内容 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| read_model_key | 否 | 不改 | 无 | 不适用 |
| scope_type/scope_key | 否 | 不改 | 无 | 不适用 |
| source/schema version | 否 | 不改 | 无 | 不适用 |
| readiness/freshness | 否 | 不改 | 无 | 不适用 |
| dirty scope / outbox | 否 | 不改 | 无 | 不适用 |
| worker registry / App Status | 否 | 不改 | 无 | 不适用 |
| Operation barrier / force refresh | 否 | 不改 | 无 | 不适用 |
| Redis/RabbitMQ behavior | 否 | 不改 | 无 | 不适用 |

### 4. 前端影响

无前端改动。

### 5. 跨模块影响

- 上游模块: 所有经 `server.py` dispatch 的页面/API。
- 下游模块: 已拆 `routes_*.py` owner 和其 services。
- 共享 facts/read model/worker/frontend event/operation barrier: 不改变。
- 旧功能可能受影响: 只有静态测试失败会暴露 owner drift；runtime 不变。
- 旧 route/service/repository/read model/frontend API 是否仍被调用: 是，`server.py` residual handlers 继续存在；本轮 classify 为 legacy/shared boundary，后续按队列小步处理。
- 新链路是否可能读取旧模块内部状态: 本轮不新增新链路；新增 guard 防止已拆 route owner 消失。

### 6. Legacy 分类

| Legacy path | 当前调用者 | 目标状态 | 删除/隔离证据 | 防污染测试 |
| --- | --- | --- | --- | --- |
| `server.py` residual `_handle_api_*` without route module owner | `Application.handle_request` | compat-only / shared boundary | 暂不删除；需要按模块逐步迁移 | 本轮 inventory guard 限定已拆 route owner 不回退 |
| 已存在 `routes_*.py` owner 未登记到 `server.py` | 无合法状态 | forbidden | 新 guard 要求 import/factory/delegate | 新静态 guard |
| 已登记 route owner handler 回退到 direct `server.py` business path | 无合法状态 | forbidden | 新 guard 要求至少一个 accessor/attribute delegate | 新静态 guard |

## State Machine Impact

- 全局工作流状态: `AutonomousContinue`，当前执行状态为 `autonomous-continue-after-batch-accounting-legacy-route-contract`。
- 选中边界进入前状态: `server-py:route-owner-inventory` 为 `pending`。
- 已审阅状态机文件:
  - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
  - `docs/modules/read-models/state-machine.md`
  - `docs/modules/app-shell-navigation/state-machine.md`
  - `docs/modules/batch-accounting/state-machine.md`
- 全局状态机定义: definition unchanged。本轮不新增、重命名或改变 workflow state、transition、guard、stop/defer condition 或 completion criterion。
- 模块状态机定义: definition unchanged。本轮新增共享 route owner 静态守卫，不改变业务状态、UI 状态、read model 状态、worker 状态、operation barrier 状态、force-refresh 状态、permission 状态或 legacy-retirement 状态定义。
- 成功流转: `pending` -> `closed-autonomous`，自动执行状态更新为 `autonomous-continue-after-server-py-route-owner-inventory`。
- defer/block 流转: 若发现已登记 route owner 缺失且无法无行为变更修复，应记录 `deferred-module-failure`；若需要生产写或敏感凭据，应记录 `needs-human-production-gate`。当前未触发。
- 完成时必须更新: 本 analysis、`tests/test_platform_runtime_boundary_guards.py`、`docs/app-architecture/runtime-and-ownership.md`、`autonomous/STATE.md`、`autonomous/MODULE-QUEUE.md`、`autonomous/JOURNAL.md`、`autonomous/NEXT-PROMPT.md`。

## 七类测试映射

| 类别 | 是否适用 | 本轮计划 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改业务规则、金额、状态转换、分类、权限或去重。 |
| 2. Service-layer tests | 适用 | 新增 static route owner inventory guard，保护 route/service 边界不回退。 |
| 3. API contract tests | 间接适用 | 不改 API shape；运行 app check 和现有 route boundary guard。 |
| 4. Read model/cache/background job tests | 不适用 | 不改 read model/cache/worker。 |
| 5. Frontend component and interaction tests | 不适用 | 无前端变化。 |
| 6. End-to-end business-flow integration tests | 不适用 | 不改跨模块运行链路。 |
| 7. Existing feature regression tests | 适用 | 运行平台静态 guard、app check、docs check、diff check。 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- 远端 GitHub fetch 在本轮中两次遇到 `LibreSSL SSL_connect: SSL_ERROR_SYSCALL`；提交前会重试。该问题不是业务 blocker。
- 敏感凭据处理: 不读取、不记录凭据。

## 验证结果

- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v` 通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_route_handlers_do_not_bypass_service_boundaries -v` 通过。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` 通过。
- `bash scripts/verify.sh docs` 通过。
- `git diff --check` 通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests -v` 未全绿，失败项为既有平台边界风险，非本 slice 引入：
  - `test_app_invoice_writes_stay_in_core_repository`: `backend/src/fin_ops_platform/tools/repair_submitted_etc_invoice_overlaps.py` 含 direct `update app.invoices` SQL。
  - `test_oa_attachment_invoice_create_permission_is_gated_by_recognition_service`: `backend/src/fin_ops_platform/tools/oa_attachment_invoice_promotion.py` 传递 `allow_create`，且静态断言未识别 `server.py` 中换行的 `allow_create=(decision.action == CREATE_INVOICE_AND_LINK)`。

## 后续边界

下一步推进 `go-hot-path:workbench-compute-admission`：

- 只做 Workbench matching/grouping/check Go hot path admission review。
- 不实现 Go/Fiber/Go Worker，除非 `11-GO-HOT-PATH-CARVE-OUT.md` 的 admission gates 全部通过并具备等价测试计划。
