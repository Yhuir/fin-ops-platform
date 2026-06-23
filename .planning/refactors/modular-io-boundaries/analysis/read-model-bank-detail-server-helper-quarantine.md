# Bank Detail Server Helper Quarantine

**日期:** 2026-06-24
**Boundary:** `read-models:bank-detail-server-helper-quarantine`
**状态:** `implementation-closed`
**模块闭环:** `implementation-gap-open`
**范围:** 删除 `server.py` 中已无调用者的 bank detail read/cache helper，新增静态 guard 防止旧 helper 回归，并登记仍保留的 Application callback/gateway wrapper；不改变 API shape、业务规则、read model schema、worker、前端或 Go/Fiber/Go Worker。

## Previous State

- `read-models:bank-detail-pilot-verification-and-template-revision` 已确认 `bank_detail` 试点不能标记为模块闭环。
- `BankDetailsApplicationService` 已拥有 bank detail SQL read/cache/freshness helper 的当前实现。
- `server.py` 仍保留一组同名或旧语义 helper，但 targeted `rg` 显示其中 read/cache/payload helper 只剩定义，没有生产调用者。
- 真正仍有调用者的 Application paths 是 refresh gateway wrapper、category mutation callback、suggestion callback、application service factory、derived lifecycle executor 和 available-month scope helper。

## Selected Boundary

本轮只处理最小 server helper 污染面：

- 删除已无调用者的 `Application` read/cache/payload helper。
- 新增静态 guard，证明这些 helper 不得回归到 `server.py`，且对应 owner 在 `BankDetailsApplicationService`。
- 对保留的 `Application` paths 做分类，不在本 slice 中迁移 callback/side-effect 语义。

## Transition Guard

- 当前分支为 `dev`，`origin/dev` 已 fast-forward。
- Queue 下一项是 `read-models:bank-detail-server-helper-quarantine`。
- CodeGraph 已用于结构检索；最终调用者依据以当前文件内容和 `rg` literal 结果为准。
- 不连接真实 PostgreSQL、Redis、RabbitMQ，不执行生产写入。

## Removed Paths

从 `backend/src/fin_ops_platform/app/server.py` 删除：

- `Application._bank_detail_scope_keys_for_range(...)`
- `Application._bank_detail_scope_summary(...)`
- `Application._with_bank_detail_auto_tag_rule_freshness(...)`
- `Application._bank_detail_accounts_refreshing_payload(...)`
- `Application._bank_detail_transactions_refreshing_payload(...)`
- `Application._with_bank_detail_tag_dictionary(...)`
- `Application._enqueue_bank_detail_read_model_refreshes_unless_refreshing(...)`
- `Application._bank_detail_redis_cache_key(...)`
- `Application._get_bank_detail_cached_payload(...)`
- `Application._set_bank_detail_cached_payload(...)`

这些行为的当前 owner 是 `BankDetailsApplicationService`：

- `_scope_keys_for_range(...)`
- `_scope_summary(...)`
- `_with_auto_tag_rule_freshness(...)`
- `_accounts_refreshing_payload(...)`
- `_transactions_refreshing_payload(...)`
- `_with_tag_dictionary(...)`
- `_enqueue_read_model_refreshes_unless_refreshing(...)`
- `_redis_cache_key(...)`
- `_get_cached_payload(...)`
- `_set_cached_payload(...)`

## Retained Path Classification

| Path | Caller / owner | Classification | Allowed behavior | Forbidden writes | Deletion / migration condition | Test evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `Application._enqueue_bank_detail_read_model_refreshes(...)` | import/settings/derived lifecycle/category callback | `gateway-backed wrapper` | Normalize non-empty scopes, wake cache transport, delegate to `ReadModelRefreshGateway.enqueue_many("bank_detail", ...)` | Direct SQL writes to `job.outbox_events`, `job.read_model_dirty_scopes`, readiness, cache payload or App Status | Migrate import/settings/lifecycle producers to a dedicated bank detail refresh collaborator | `test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary` |
| `Application._delete_bank_detail_redis_cache(...)` | refresh wrapper | `gateway-adjacent wakeup wrapper` | Publish optional `bank_detail_read_model_refresh` wakeup through runtime Redis helper | Become freshness source, write cache payload, write dirty/outbox/readiness | Rename/migrate together with refresh collaborator | Covered indirectly by refresh wrapper classification |
| `Application._latest_bank_detail_auto_category_suggestion(...)` | `BankDetailsApplicationService` callback | `compat-only callback` | Compute current suggestion from import transaction and auto category service | Write category facts, dirty scopes, outbox, readiness, cache or audit | Move suggestion calculation behind service/collaborator dependency | Factory classification guard |
| `Application._after_bank_category_confirmation_mutation(...)` | `BankDetailsApplicationService` callback | `compat-only side-effect callback` | Enqueue bank detail/turnover refresh through wrappers, invalidate workbench, record audit | Direct SQL writes to queue/readiness/cache/App Status or category facts | Extract bank detail category side-effect port | Existing API tests plus next boundary |
| `Application._bank_details_application_service(...)` | route factory | `dependency-factory-only` | Construct `BankDetailsApplicationService` with explicit dependencies/callbacks | Business rules, HTTP response construction inside service, direct job SQL | Reduce callbacks after side-effect port extraction | Factory classification guard |
| `Application._derived_lifecycle_bank_detail_executor(...)` | derived lifecycle registry | `registered producer` | Expand lifecycle scope and call gateway-backed refresh wrapper | Direct job SQL/readiness/cache writes | Shared lifecycle producer extraction | Existing lifecycle/read model tests |
| `Application._bank_detail_available_month_scope_keys(...)` | service factory + derived lifecycle | `scope-calculator support` | Read import service and derive available month scopes | Dirty/outbox/readiness/cache writes | Move to shared bank detail scope calculator | Existing reapply/lifecycle tests |

## Impact Analysis

| 层 | 是否影响 | 文件/符号 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| route / HTTP mapping | 否 | `routes_bank_details.py` | API status/shape 不应变化 | bank detail API 回归 |
| application service | 是，边界保护 | `BankDetailsApplicationService` | 必须继续拥有 read/cache/freshness helper | 新增 static guard |
| repository / SQL | 否 | `BankDetailReadModelRepositoryPort` | 不改 SQL/schema | 既有 SQL runtime 回归 |
| read model freshness/cache | 是，旧 helper 删除 | `server.py` dead helper removal | 旧 helper 回归会绕开 service owner | 新增 static guard + read model tests |
| worker/queue | 是，分类 | retained gateway wrapper | wrapper 必须继续走 gateway，不直接 SQL 写 queue | 新增 static guard |
| frontend | 否 | BankDetails page/API | API shape 不变 | 不适用 |
| permissions/audit | 否 | routes/service audit | 分类 callback 未迁移，审计语义不变 | existing API tests |

## 七类测试映射

| 类别 | 是否适用 | 本轮处理 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改分类规则、金额、状态转换或权限决策。 |
| 2. Service-layer tests | 适用 | 新增 `PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary`，证明 read/cache owner 在 service。 |
| 3. API contract tests | 适用，回归 | 复跑 bank detail route/API targeted tests，保护 response shape。 |
| 4. Read model/cache/background job tests | 适用 | guard 覆盖 helper ownership 和 gateway wrapper；SQL runtime/operation barrier 回归覆盖 freshness/cache 行为。 |
| 5. Frontend component and interaction tests | 不适用 | 无前端/API client/UI 改动。 |
| 6. End-to-end business-flow integration tests | 不适用 | 无 local `PGSQL_URL`/staging；本轮不做生产写入或 worker drain。 |
| 7. Existing feature regression tests | 适用 | 复跑 bank detail targeted regression set。 |

## State Machine Impact

- Global workflow definition: unchanged。
  - 已审阅 `03-REFACTOR-STATE-MACHINE.md`；本轮不新增状态、transition、guard 或 status label。
- Module state definition: unchanged。
  - 已审阅 `docs/modules/read-models/state-machine.md`、`docs/modules/bank-details/state-machine.md`、`docs/modules/runtime-workers/state-machine.md`；本轮删除 dead helper 并新增 guard，不改变业务/read model/worker 状态语义。
- Progress/accounting changed:
  - `read-models:bank-detail-server-helper-quarantine` -> `implementation-closed`
  - `bank_detail` module remains `implementation-gap-open`
  - 下一边界：`read-models:bank-detail-category-side-effect-port-extraction`
- Go state:
  - unchanged，仍 `blocked-by-prerequisite`

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v` 通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_read_model_architecture_guards -v` 通过，7 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_details_routes tests.test_bank_details_sql_runtime tests.test_operation_freshness_barrier -v` 通过，104 tests。
- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py` 通过。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` 通过。
- `bash scripts/verify.sh docs` 通过。
- `git diff --check` 通过。

Broader check note:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v` 当前有 2 个与本 slice 无关的失败：
  - `test_app_invoice_writes_stay_in_core_repository` 报 `tools/repair_submitted_etc_invoice_overlaps.py` direct `update app.invoices` SQL。
  - `test_oa_attachment_invoice_create_permission_is_gated_by_recognition_service` 报 `tools/oa_attachment_invoice_promotion.py` / server OA attachment promotion guard。
- 这两个失败不涉及 bank detail、read model helper 删除、`server.py` bank detail refresh wrapper 或本轮新增 guard；本轮未扩大到 ETC/OA invoice repair/promotion 模块。

## 未测风险

- 未连接真实 PostgreSQL、Redis、RabbitMQ。
- 未执行生产 read-only SSH/HTTP SLO。
- 未证明真实 `bank_detail` worker drain 的 enqueue-to-fresh SLO。
- Category mutation side-effect callback 仍在 `Application`，下一步需要抽成明确 side-effect port 或继续隔离。
