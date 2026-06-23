# Bank Detail Category Side-Effect Port Extraction

**日期:** 2026-06-24
**Boundary:** `read-models:bank-detail-category-side-effect-port-extraction`
**状态:** `implementation-closed`
**模块闭环:** `implementation-gap-open`
**范围:** 将银行明细分类写后的 refresh / turnover fan-out / workbench invalidation / audit 副作用从 `Application._after_bank_category_confirmation_mutation(...)` callback 抽为显式 service port；不改变分类业务规则、API response shape、read model schema、worker、前端或 Go/Fiber/Go Worker。

## Previous State

- `read-models:bank-detail-server-helper-quarantine` 已删除 `server.py` 中无调用者的 bank detail read/cache/payload helper。
- `Application._after_bank_category_confirmation_mutation(...)` 仍作为 `BankDetailsApplicationService` 的 callback 注入，负责：
  - enqueue `bank_detail` refresh
  - enqueue `turnover_ledger:all` refresh
  - invalidate Workbench after bank transaction category mutation
  - record bank category audit
- `BankDetailsApplicationService._persist_category_mutation(...)` 已是分类写后的统一 service 内部入口，但 side effects 仍可回落到 `Application` 私有方法。

## Selected Boundary

本轮只关闭 category mutation side-effect callback 污染面：

- 新增 `BankDetailCategoryMutationSideEffectPort`。
- `Application` 只在 `_bank_details_application_service(...)` 中构造并注入该 port。
- 删除 `Application._after_bank_category_confirmation_mutation(...)`。
- `BankDetailsApplicationService._persist_category_mutation(...)` 调用显式 port；无 port 时保留现有 fallback，供纯 service/local 测试与兼容实例使用。
- 将 `Application._latest_bank_detail_auto_category_suggestion(...)` 分类为短期 `compat-only read callback`，本轮不迁移；它只计算 suggestion，不写 canonical facts、dirty scope、outbox、readiness、cache 或 audit。

## Transition Guard

- 当前分支为 `dev`，`origin/dev` 已 fast-forward。
- Queue 下一项为 `read-models:bank-detail-category-side-effect-port-extraction`。
- 已使用 CodeGraph 和 targeted search 分析 `Application._after_bank_category_confirmation_mutation`、`Application._latest_bank_detail_auto_category_suggestion`、`BankDetailsApplicationService._persist_category_mutation`、factory injection 和相关测试。
- 不连接真实 PostgreSQL、Redis、RabbitMQ，不执行生产写入。

## Removed Path

从 `backend/src/fin_ops_platform/app/server.py` 删除：

- `Application._after_bank_category_confirmation_mutation(...)`

旧路径不得回归。`tests/test_platform_runtime_boundary_guards.py` 现在证明：

- `server.py` 不再定义 `_after_bank_category_confirmation_mutation`。
- `Application._bank_details_application_service(...)` 不再把该 callback 注入 `BankDetailsApplicationService`。
- factory 必须构造并注入 `BankDetailCategoryMutationSideEffectPort`。

## New Explicit Port

新增 `backend/src/fin_ops_platform/services/bank_detail_category_side_effects.py`：

| Method | Inputs | Outputs | Allowed behavior | Forbidden behavior |
| --- | --- | --- | --- | --- |
| `BankDetailCategoryMutationSideEffectPort.after_mutation(...)` | `transaction_id`、`actor_id`、`action`、`affected_months`、`metadata` | side effects only; returns `None` | 通过注入的 gateway-backed callbacks enqueue `bank_detail` 和 `turnover_ledger` refresh；调用 Workbench invalidation；写 audit | 直接 SQL 写 `job.outbox_events`、`job.read_model_dirty_scopes`、readiness、cache、App Status 或 category facts |

Port dependencies:

- `enqueue_bank_detail_refresh`: 当前由 `Application._enqueue_bank_detail_read_model_refreshes(...)` 提供，仍是 gateway-backed wrapper。
- `enqueue_turnover_ledger_refresh`: 当前由 `Application._enqueue_turnover_ledger_read_model_refreshes(...)` 提供，仍是 gateway-backed wrapper。
- `invalidate_workbench_after_category_mutation`: 当前 Workbench invalidation callback。
- `audit_service`: 当前 audit service。

## Retained Path Classification

| Path | Classification | Allowed behavior | Forbidden writes | Deletion / migration condition | Test evidence |
| --- | --- | --- | --- | --- | --- |
| `Application._latest_bank_detail_auto_category_suggestion(...)` | `compat-only read callback` | Read one import transaction, build auto-category input row, return current suggestion | category facts、dirty/outbox/readiness/cache/App Status/audit writes | Move suggestion calculation to a dedicated suggestion provider/collaborator when the category selection boundary is next touched | Existing API validation tests and factory classification guard |
| `Application._enqueue_bank_detail_read_model_refreshes(...)` | `gateway-backed wrapper` | Delegate `bank_detail` refresh to `ReadModelRefreshGateway.enqueue_many(...)`; publish optional wakeup | direct job SQL/readiness/cache payload/App Status writes | Later shared refresh producer extraction | Static guard |
| `Application._enqueue_turnover_ledger_read_model_refreshes(...)` | `gateway-backed wrapper` | Delegate `turnover_ledger` refresh to `ReadModelRefreshGateway.enqueue_many(...)` | direct job SQL/readiness/cache payload/App Status writes | Later turnover/shared lifecycle extraction | API/service tests |
| `Application._bank_details_application_service(...)` | `dependency-factory-only` | Construct `BankDetailsApplicationService` and explicit side-effect port | business rules, HTTP responses, direct queue SQL | Reduce remaining callbacks in later boundaries | Static guard |

## Impact Analysis

| 层 | 是否影响 | 文件/符号 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| route / HTTP mapping | 否 | `routes_bank_details.py` | API status/shape 不应变化 | bank details route/API 回归 |
| application service | 是 | `BankDetailsApplicationService._persist_category_mutation` | 必须继续保存 category snapshot、保持 affected months 和 response contract | service/API tests |
| side-effect port | 是 | `BankDetailCategoryMutationSideEffectPort.after_mutation` | refresh/audit/workbench fan-out 必须保持原语义 | new/updated service + API tests |
| repository / SQL | 否 | category/read model repositories | 不改 SQL/schema | SQL runtime regression |
| read model freshness | 是，间接 | bank_detail refresh + operation barrier target | `bank_detail` refresh scope 必须保持 affected month，不回退 all | operation barrier/API tests |
| worker/queue | 是，间接 | refresh wrappers | port 不得直接 SQL 写 queue 表 | static guard |
| frontend | 否 | BankDetails page/API | API response shape 不变 | 不适用 |
| permissions/audit | 是，审计路径迁移到 port | audit action metadata | audit entity/action/metadata 必须保持 | API/service tests |

## 七类测试映射

| 类别 | 是否适用 | 本轮处理 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改分类规则、candidate validation、金额、状态转换或权限决策。 |
| 2. Service-layer tests | 适用 | 更新 `_persist_category_mutation` tests，证明 side-effect port 抑制 fallback，port failure 不跑 fallback。 |
| 3. API contract tests | 适用，回归 | 复跑 `tests.test_bank_auto_tag_rules_api` 和 `tests.test_bank_details_routes`，保护 category API response shape 和权限映射。 |
| 4. Read model/cache/background job tests | 适用 | 复跑 `tests.test_bank_details_sql_runtime` 与 `tests.test_operation_freshness_barrier`；static guard 证明 port 不直接 SQL 写 queue 表。 |
| 5. Frontend component and interaction tests | 不适用 | 无前端/API client/UI 改动。 |
| 6. End-to-end business-flow integration tests | 不适用 | 无 local `PGSQL_URL`/staging；本轮不做生产写入或真实 worker drain。 |
| 7. Existing feature regression tests | 适用 | 复跑 bank detail targeted regression set。 |

## State Machine Impact

- Global workflow definition: unchanged。
  - 已审阅 `03-REFACTOR-STATE-MACHINE.md`；本轮不新增状态、transition、guard 或 status label。
- Module state definition: unchanged。
  - 已审阅 `docs/modules/read-models/state-machine.md`、`docs/modules/bank-details/state-machine.md`、`docs/modules/runtime-workers/state-machine.md`；本轮只迁移 side-effect owner，不改变业务/read model/worker 状态语义。
- Progress/accounting changed:
  - `read-models:bank-detail-category-side-effect-port-extraction` -> `implementation-closed`
  - `bank_detail` module remains `implementation-gap-open` because production DB/worker evidence is still unavailable and several Application gateway/scope support wrappers remain classified but not globally extracted.
  - 下一边界：`server-py:legacy-handler-extraction-implementation`
- Go state:
  - unchanged，仍 `blocked-by-prerequisite`

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/bank_detail_category_side_effects.py backend/src/fin_ops_platform/services/bank_details_application_service.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_sql_runtime.py tests/test_bank_auto_tag_rules_api.py tests/test_platform_runtime_boundary_guards.py` 通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v` 通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime.BankDetailSqlRepositoryTests.test_category_mutation_side_effect_port_suppresses_fallback_enqueue_audit_and_invalidate tests.test_bank_details_sql_runtime.BankDetailSqlRepositoryTests.test_category_mutation_side_effect_port_failure_does_not_run_fallback_side_effects tests.test_bank_details_sql_runtime.BankDetailSqlRepositoryTests.test_category_mutation_refreshes_turnover_ledger_all_scope tests.test_bank_details_sql_runtime.BankDetailSqlRepositoryTests.test_category_mutation_response_returns_bank_detail_operation_barrier_targets -v` 通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_manual_assignment_endpoint_allows_unmatched_row_to_choose_active_tag tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_manual_assignment_delete_endpoint_clears_manual_category tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_bank_category_mutation_side_effect_port_enqueues_turnover_ledger_all_refresh -v` 通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v` 通过，36 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime -v` 通过，53 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes tests.test_operation_freshness_barrier -v` 通过，15 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_read_model_architecture_guards -v` 通过，7 tests。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` 通过。
- `bash scripts/verify.sh docs` 通过。
- `git diff --check` 通过。
- diff secret scan for this slice returned no matches.

## 未测风险

- 未连接真实 PostgreSQL、Redis、RabbitMQ。
- 未执行生产 read-only SSH/HTTP SLO。
- 未证明真实 `bank_detail` worker drain 的 enqueue-to-fresh SLO。
- `Application._latest_bank_detail_auto_category_suggestion(...)` 仍是只读 compat callback，后续触碰 category selection/suggestion 边界时应迁移到显式 collaborator。
- `Application._enqueue_bank_detail_read_model_refreshes(...)`、`Application._enqueue_turnover_ledger_read_model_refreshes(...)` 和 available-month scope helper 仍是 classified support wrappers，未在本 slice 中做共享 lifecycle/refresh producer 抽取。
