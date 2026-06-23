# Bank Detail Legacy Contamination Removal

**日期:** 2026-06-24
**Boundary:** `read-models:bank-detail-legacy-contamination-removal`
**状态:** `implementation-closed`
**范围:** 删除 `server.py` 中已无生产调用者的 bank detail SQL read compat helper，并把测试入口迁移到 route/application service 公共边界；不改变银行明细 API shape、业务规则、read model schema、worker、前端或 Go/Fiber/Go Worker。

## Previous State

- `read-models:bank-detail-repository-port-extraction` 已把 `server.py` 的 `_get_bank_detail_accounts_from_sql_read_model(...)` 与 `_get_bank_detail_transactions_from_sql_read_model(...)` 降级为 application-service delegate。
- `read-models:bank-detail-refresh-freshness-operation-barrier` 已补齐写后/强制刷新响应中的 `read_model_scope_keys` 与 `freshness_targets`。
- 本轮前这两个旧 helper 只剩测试直接调用；CodeGraph callers 未发现生产代码调用。

## Selected Boundary

删除一个最小 legacy contamination path：

- Removed:
  - `Application._get_bank_detail_accounts_from_sql_read_model(...)`
  - `Application._get_bank_detail_transactions_from_sql_read_model(...)`
- Retained canonical path:
  - HTTP handlers -> `BankDetailsApiRoutes` -> `BankDetailsApplicationService.accounts_payload(...)`
  - HTTP handlers -> `BankDetailsApiRoutes` -> `BankDetailsApplicationService.transactions_payload(...)`

## Transition Guard

- 工作区 clean，分支为 `dev`。
- `origin/dev` fast-forward 已确认，`origin/main` 已无待合入差异。
- Planning 状态一致：下一边界是 `read-models:bank-detail-legacy-contamination-removal`，Go hot-path 仍 blocked。
- CodeGraph 证明两个旧 helper 的 caller 只在 `tests/test_bank_auto_tag_rules_api.py`。

## Impact Analysis

| 层 | 是否影响 | 文件/符号 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| route / HTTP mapping | 是，间接 | `BankDetailsApiRoutes.accounts/transactions` 成为测试和生产唯一读入口 | route status mapping 必须保持 200/202 语义 | `tests.test_bank_auto_tag_rules_api` |
| application service | 否 | `BankDetailsApplicationService` 未改 | 无业务逻辑变化 | 既有 API/read model 回归 |
| repository / SQL | 否 | `BankDetailReadModelRepositoryPort` 未改 | port contract 仍需保留 | 既有 repository port 测试 |
| read model freshness | 否 | freshness/status/enqueue 逻辑未改 | route 测试必须显式 SQL runtime，避免误走 legacy live service | 更新测试设置 `_requires_sql_read_model_runtime = lambda: True` |
| operation barrier | 否 | 未改 | 上一 slice 行为需回归 | 后续组合验证 |
| frontend | 否 | 未改 | API shape 不变 | 不适用 |
| permissions / audit | 否 | 未改 | 无权限/审计语义变化 | 既有 API 测试 |

## IO Contract Delta

### Inputs

无新增输入。银行明细 accounts/transactions 仍接收原有筛选、分页和分类 filter。

### Outputs

无 API 输出字段变化。删除的是 `Application` 私有 compat helper，不是 HTTP/API contract。

### States

未改变 read model 状态机。`fresh`、`refreshing`、`stale`、`schema_mismatch`、`missing`、`failed`、`unavailable` 语义仍以 `docs/modules/read-models/state-machine.md` 和 `docs/modules/bank-details/state-machine.md` 为准。

### Events

无新增或删除 event。`bank_detail.read_model.refresh`、`bank_detail_category_confirmation_changed`、`bank_auto_tag_rules_*` reason 不变。

### Read Model / Force Refresh / Operation Barrier

本轮不改变 gateway、scope policy、dirty/outbox 或 operation barrier。测试通过 route/application public boundary 继续覆盖：

- refreshing scope 不重复 enqueue。
- stale scope enqueue 一次。
- auto-tag rule version mismatch 标 stale。
- shared store 最新规则版本可作为 freshness proof。

## Legacy Retirement Contract

| Legacy path | 当前调用者 | 目标状态 | 证据 | 防污染测试 |
| --- | --- | --- | --- | --- |
| `Application._get_bank_detail_accounts_from_sql_read_model(...)` | 仅旧测试 | removed | CodeGraph callers 只在测试；代码删除后 `rg` 不再发现 backend 定义/调用 | `test_bank_detail_legacy_sql_helpers_are_removed_from_application_boundary` |
| `Application._get_bank_detail_transactions_from_sql_read_model(...)` | 仅旧测试 | removed | CodeGraph callers 只在测试；代码删除后 `rg` 不再发现 backend 定义/调用 | `test_bank_detail_legacy_sql_helpers_are_removed_from_application_boundary` |

删除后新链路不得通过 `Application` 私有 helper 访问 bank detail SQL read model；测试必须走 `BankDetailsApiRoutes` 或 `BankDetailsApplicationService` 公共入口。

## 七类测试映射

| 类别 | 是否适用 | 本轮处理 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改分类、金额、状态转换或权限规则。 |
| 2. Service-layer tests | 适用 | 既有 freshness tests 改为通过 route/application boundary 验证。 |
| 3. API contract tests | 适用 | `tests.test_bank_auto_tag_rules_api` 覆盖 route facade 读路径 200/202 与 response payload。 |
| 4. Read model/cache/background job tests | 适用 | 覆盖 refreshing 不重复入队、stale 入队一次、auto-tag 版本 freshness。 |
| 5. Frontend component and interaction tests | 不适用 | 无前端改动，API shape 不变。 |
| 6. End-to-end business-flow integration tests | 不适用 | 无本地 PGSQL_URL/staging；真实 worker drain 仍作为后续 pilot verification/defer。 |
| 7. Existing feature regression tests | 适用 | 完整 `tests.test_bank_auto_tag_rules_api` 回归。 |

## State Machine Impact

- Global workflow definition: unchanged。
  - 已审阅 `03-REFACTOR-STATE-MACHINE.md`，本轮没有新增状态、transition、guard 或 completion label。
- Module state definition: unchanged。
  - 已审阅 `docs/modules/read-models/state-machine.md`、`docs/modules/bank-details/state-machine.md`、`docs/modules/runtime-workers/state-machine.md`；状态语义未变。
- Progress/accounting changed:
  - `read-models:bank-detail-legacy-contamination-removal` -> `implementation-closed`
  - `bank_detail` module remains `implementation-gap-open`，因为 pilot verification/template revision 与真实生产 worker/readiness 证据或 defer 状态仍未闭合。
- Next prompt:
  - `read-models:bank-detail-pilot-verification-and-template-revision`

## 验证结果

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v` 通过，36 tests。
- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_bank_auto_tag_rules_api.py` 通过。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_details_routes tests.test_bank_details_sql_runtime tests.test_operation_freshness_barrier -v` 通过，104 tests。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` 通过。
- `bash scripts/verify.sh docs` 通过。
- `git diff --check` 通过。

## 未测风险

- 未连接真实 PostgreSQL、Redis、RabbitMQ。
- 未执行生产 read-only SSH/HTTP SLO。
- 未证明真实 `bank_detail` worker drain 的 enqueue-to-fresh SLO。
- `server.py` 仍保留其它 bank detail 兼容 helper，包括 scope summary、cache、refresh wrapper 和 dynamic suggestion provider；它们不是本窄 slice 的删除对象，后续 pilot verification 必须决定是否继续拆分或登记为 compat-only。
