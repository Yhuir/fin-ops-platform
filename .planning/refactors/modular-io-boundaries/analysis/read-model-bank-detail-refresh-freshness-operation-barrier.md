# Bank Detail Refresh Freshness Operation Barrier

**日期:** 2026-06-24
**Boundary:** `read-models:bank-detail-refresh-freshness-operation-barrier`
**状态:** `implementation-closed`
**范围:** 为 `bank_detail` 写后刷新和强制刷新响应补齐 operation barrier targets，证明目标 scope 使用具体月份、refresh 入队继续走 `ReadModelRefreshGateway` / scope policy registry；不改变 API 既有字段、不改前端、不启动 Go/Fiber/Go Worker。

## 目标

本 slice 只关闭 `bank_detail` freshness/barrier 的窄实现边界：

- 分类确认、撤销、人工分类、清除人工分类继续返回既有 `affected_months`，并额外返回 `read_model_scope_keys` 与 `freshness_targets`。
- 自动标签规则重应用 force refresh 返回同一组 `read_model_scope_keys` 与 `freshness_targets`。
- 当存在具体月份 scope 时，operation barrier target 不使用 `bank_detail:all`。
- `bank_detail` refresh 仍通过 `ReadModelRefreshGateway.enqueue_many("bank_detail", ...)`，由 scope policy registry normalize/validate/dedupe 后进入 durable queue。

## Impact Analysis

| 层 | 是否影响 | 文件/符号 | 风险 | 测试 |
| --- | --- | --- | --- | --- |
| route / HTTP mapping | 否 | `routes_bank_details.py` 保持不变 | 无新增 route 行为 | API 回归测试覆盖响应 payload |
| application service | 是 | `BankDetailsApplicationService` | 写后同步字段必须和 affected months 一致 | `test_category_mutation_response_returns_bank_detail_operation_barrier_targets` |
| repository / SQL | 否 | 无 | 不改 SQL / schema | 既有 SQL runtime 全文件回归 |
| dirty scope / outbox | 是 | `_enqueue_read_model_refreshes(...)` 既有 gateway path | force refresh 不能退回 `all` 或绕过 gateway | `test_reapply_endpoint_enqueues_bank_detail_refresh_without_changing_rules` |
| operation barrier | 是 | `OperationFreshnessBarrierService` target contract | 其它月份 pending 不能阻断当前月份 | `test_bank_detail_target_uses_exact_month_scope_for_operation_barrier` |
| frontend | 否 | `BankDetailsPage` 已用 operation barrier helper | 本轮不改 UI，后续可消费后端 targets | 前端不适用 |
| permissions / audit | 否 | 既有 bank details session/audit | 权限和审计语义不变 | 既有 API 测试通过 |

## IO Contract Delta

### Inputs

- 分类写操作：`transaction_id`、category payload、actor。
- 自动标签重应用：当前可用 bank detail month scopes。

### Outputs

新增兼容字段：

- `read_model_scope_keys`: 需要等待的 `bank_detail` scope。
- `freshness_targets`: `[{ "read_model_key": "bank_detail", "scope_key": "<YYYY-MM|all>" }]`。

既有字段保持：

- `affected_months`
- `read_model_status`
- `refresh_enqueued`
- `refresh_reason`
- `enqueued_jobs`

### States

未改变 read model 状态机。`fresh`、`refreshing`、`stale`、`missing`、`failed`、`unavailable` 语义仍以 `docs/modules/read-models/state-machine.md` 为准。

### Events

- `bank_detail.read_model.refresh` 仍是唯一 bank detail refresh event。
- 分类写入 reason 仍是 `bank_detail_category_confirmation_changed`。
- 规则重应用 reason 仍是 `bank_auto_tag_rules_reapply_requested`。

### Read Model / Force Refresh Contract

- 强制刷新路径仍是 `ReadModelRefreshGateway`。
- Gateway 继续使用 `ReadModelScopePolicyRegistry` 验证 `bank_detail` 只接受 `YYYY-MM` 或 `all`。
- 页面/调用者应等待 `freshness_targets` 指定的 scope；当有具体月份时不能等待 fan-out-only `all` 作为 fresh proof。

### Operation Barrier Contract

`freshness_targets` 与 `read_model_scope_keys` 一致。`OperationFreshnessBarrierService` 读取 App Status runtime snapshot，按 `bank_detail.read_model.refresh` 的目标 scope 判定：

- target scope readiness fresh 且 target scope 无 pending/failed outbox -> `fresh`
- target scope pending/processing -> `refreshing`
- target scope failed/dead-lettered -> `blocked`
- 其它月份 outbox pending 不阻断当前 target scope。

## Legacy Classification

- 本轮未删除 `server.py` 剩余 legacy helper；它们仍是后续 `read-models:bank-detail-legacy-contamination-removal` 的候选。
- 本轮没有新增 legacy path。
- `server.py` 两个 SQL read helper 仍保持上一 slice 的 `compat-only` application-service delegate 状态。

## 七类测试映射

| 类别 | 是否适用 | 本轮处理 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改分类业务规则、金额、权限决策或状态转移。 |
| 2. Service-layer tests | 适用 | 新增分类写入 response freshness target 测试，覆盖 service contract。 |
| 3. API contract tests | 适用 | 更新 reapply API 测试，证明 force refresh 响应包含目标 scope 和 targets。 |
| 4. Read model/cache/background job tests | 适用 | `test_bank_details_sql_runtime` 和 `test_operation_freshness_barrier` 覆盖 refresh scope、stale/fresh/barrier 行为。 |
| 5. Frontend component and interaction tests | 不适用 | 前端已存在 operation barrier wait helper，本轮不改 UI 或 API client 映射。 |
| 6. End-to-end business-flow integration tests | 不适用 | 无本地 `PGSQL_URL` / staging；真实 worker drain 仍作为 production evidence deferred。 |
| 7. Existing feature regression tests | 适用 | 全量 bank detail SQL runtime、auto tag API、operation barrier 单测回归。 |

## State Machine Impact

- 全局 workflow definition: unchanged。
  - 已审阅 `03-REFACTOR-STATE-MACHINE.md`，本轮没有新增状态、transition、guard 或 completion label。
- 模块 state definition: unchanged。
  - 已审阅 `docs/modules/read-models/state-machine.md` 与 `docs/modules/runtime-workers/state-machine.md`；状态语义未变。
- Progress/accounting changed:
  - `read-models:bank-detail-refresh-freshness-operation-barrier` -> `implementation-closed`
  - `bank_detail` module remains `implementation-gap-open`，因为 legacy removal、pilot verification/template revision 和真实生产 worker/readiness 证据仍未闭合。
- Next prompt:
  - `read-models:bank-detail-legacy-contamination-removal`

## 验证结果

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime -v` 通过，53 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v` 通过，36 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_operation_freshness_barrier -v` 通过，9 tests。

## 未测风险

- 未连接真实 PostgreSQL、Redis、RabbitMQ。
- 未执行生产 read-only SSH/HTTP SLO。
- 未证明真实 worker drain 的 operation-to-fresh p95/p99；缺少 local `PGSQL_URL` 和 staging DB，因此不能声明生产闭环。
- BankDetails 分类写入前端暂未消费后端返回的 `freshness_targets`；现有页面仍按当前 rows/date filter 生成 targets。后续如要严格以后端 targets 为准，应在前端 slice 单独处理。
- `server.py` 仍保留 bank detail legacy helper，下一边界必须继续 legacy contamination removal/quarantine。
