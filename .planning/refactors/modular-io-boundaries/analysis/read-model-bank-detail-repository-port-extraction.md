# Bank Detail Repository Port Extraction

**日期:** 2026-06-24
**Boundary:** `read-models:bank-detail-repository-port-extraction`
**状态:** `implementation-closed`
**范围:** 为 `bank_detail` read model 查询侧建立窄 repository port，并把 `server.py` 旧 SQL read helper 收敛为委托 `BankDetailsApplicationService` 的 query boundary；不拆全量 `postgres_repositories/read_models.py`，不改 API response shape，不启动 Go/Fiber/Go Worker。

**后续状态更新:** `read-models:bank-detail-legacy-contamination-removal` 已在 2026-06-24 删除本文件中提到的 `server.py` 两个 compat-only SQL helper。本文保留为当时 slice 记录，不再代表当前代码状态。

## 目标

本 slice 只关闭第一步实现边界：

- `PostgresStateStore.bank_detail_sql_read_repository` 不再直接返回共享的 `PostgresReadModelRepository`。
- 新增 `BankDetailReadModelRepositoryPort`，只暴露 BankDetails 页面查询需要的 read-side 方法。
- `server.py` 的旧 `_get_bank_detail_*_from_sql_read_model(...)` helper 不再直接读取 `_bank_detail_sql_read_repository`，而是委托 `BankDetailsApplicationService` 的 read model query 边界。
- 测试证明 port 不暴露无关 read model 方法，且旧 helper 不会绕过 application service 直接摸 repository。

## 当前实现

新增文件：

- `backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py`

更新：

- `backend/src/fin_ops_platform/services/postgres_state_store.py`
  - 初始化 `self._bank_detail_sql_read_repository = BankDetailReadModelRepositoryPort(self._sql_read_model_repository)`。
  - `bank_detail_sql_read_repository` property 返回该 port，而不是共享大 repository。
- `backend/src/fin_ops_platform/app/server.py`
  - `_get_bank_detail_accounts_from_sql_read_model(...)` 委托 `self._bank_details_application_service()._accounts_from_sql_read_model(...)`。
  - `_get_bank_detail_transactions_from_sql_read_model(...)` 委托 `self._bank_details_application_service()._transactions_from_sql_read_model(...)`。

## 边界说明

### 输入

- accounts: `date_from`, `date_to`
- transactions: `account_key`, date range, keyword, category filters, pagination
- scope proof 仍由 `BankDetailsApplicationService` 通过 repository port 的 `bank_detail_scope_keys_for_range(...)` 与 `bank_detail_scope_summary(...)` 判断。

### 输出

不改变 API payload shape。目标测试覆盖：

- accounts payload
- transactions payload
- `read_model_status`
- `cache_status`
- `read_model_scope_keys`
- stale/refreshing enqueue behavior

### 状态

本 slice 不改变 read model freshness 状态机，也不改变 worker/readiness/outbox/dirty scope 语义。

### 事件

本 slice 不新增 refresh producer。刷新入队仍由 `BankDetailsApplicationService` 通过 `ReadModelRefreshGateway` 执行。

### 权限

权限仍在 BankDetails API route/session 层处理；repository port 不读取 HTTP cookie/header/session。

## Legacy Classification

- `server.py` 的 `_get_bank_detail_accounts_from_sql_read_model(...)` 与 `_get_bank_detail_transactions_from_sql_read_model(...)` 在本 slice 时仍保留为 `compat-only` helper，因为当时现有测试和少量旧调用点仍直接调用它们；该状态已被后续 `read-models:bank-detail-legacy-contamination-removal` supersede，当前代码已删除这两个 helper。
- 这两个 compat helper 已被降级为 application service delegate，不能直接读 `_bank_detail_sql_read_repository`，也不能直接访问共享 `PostgresReadModelRepository`。
- `server.py` 中剩余 `_bank_detail_scope_keys_for_range(...)`、`_bank_detail_scope_summary(...)`、cache payload helper 等旧辅助函数尚未删除；它们进入下一步 `read-models:bank-detail-legacy-contamination-removal` 的候选范围，当前 slice 不做大范围删除。

## Bank Account Balance 过渡依赖

`BankDetailsApplicationService.accounts_payload(...)` 现有行为会优先读取 `list_bank_account_balances(...)` 以保持账户余额 response shape。`BankDetailReadModelRepositoryPort` 暂时保留这个只读方法作为 BankDetails accounts endpoint 的过渡依赖。

这不表示 `bank_account_balance` 模块已并入 `bank_detail`：

- `read_model_manifest.py` 中 `bank_detail` 与 `bank_account_balance` 仍是独立 read model。
- 下一步 freshness/barrier slice 不能把账户余额 readiness 当成 bank detail rows readiness。
- 后续 legacy contamination/removal 或 verification slice 应评估是否需要独立 `BankAccountBalanceReadModelRepositoryPort`。

## 测试覆盖

新增/更新：

- `tests/test_bank_details_sql_runtime.py::BankDetailSqlRepositoryTests::test_bank_detail_read_model_port_excludes_unrelated_read_model_methods`
  - 证明 port 只暴露 BankDetails read-side 所需方法，不暴露 `list_pending_invoice_rows` 等无关 read model 方法。
- `tests/test_bank_auto_tag_rules_api.py::BankAutoTagRulesApiTests::test_bank_detail_legacy_sql_helpers_delegate_to_application_service_boundary`
  - 证明 `server.py` 旧 helper 委托 application service，并且不会直接访问 poison repository。

回归覆盖：

- `tests.test_bank_details_sql_runtime` 全文件通过。
- `tests.test_bank_auto_tag_rules_api` 全文件通过。

## 七类测试映射

| 类别 | 是否适用 | 本轮处理 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改变分类规则、金额、状态转换、权限判断或业务语义。 |
| 2. Service-layer tests | 适用 | 新增 repository port contract 测试和 application service boundary 委托测试。 |
| 3. API contract tests | 适用 | 通过 `tests.test_bank_auto_tag_rules_api` 中现有 API/helper 回归保护 accounts/transactions read model shape。 |
| 4. Read model/cache/background job tests | 适用 | `tests.test_bank_details_sql_runtime` 覆盖 bank_detail SQL runtime、stale/refreshing/fresh、cache key/schema 和 refresh handler。 |
| 5. Frontend component and interaction tests | 不适用 | 本 slice 不改前端、API client 或 UI 状态。 |
| 6. End-to-end business-flow integration tests | 不适用 | 本 slice 不跨越真实导入/写入/worker drain；后续 freshness/barrier slice 再覆盖写后闭环。 |
| 7. Existing feature regression tests | 适用 | 完整 `test_bank_details_sql_runtime` 与 `test_bank_auto_tag_rules_api` 保护旧 filters/pagination/stale enqueue/auto-tag 规则链路。 |

## State Machine Impact

- 全局 workflow definition: changed。
  - 新增 Queue slice status `implementation-closed`，用于表示某个窄实现 slice 已关闭，但模块尚未闭环。
  - 已同步 `03-REFACTOR-STATE-MACHINE.md`、`MODULE-QUEUE.md`、`NEXT-PROMPT.md` 和 `04-master-goal-controller.md`。
- 模块 state definition: unchanged。
  - 已审阅 `docs/modules/read-models/state-machine.md`；fresh/missing/refreshing/stale/failed/unavailable 语义不变。
- 当前流转:
  - from `autonomous-continue-after-read-model-pilot-selection`
  - to `autonomous-continue-after-bank-detail-repository-port-extraction`
- Closed slice:
  - `read-models:bank-detail-repository-port-extraction` -> `implementation-closed`
- Module closure:
  - `bank_detail` remains `implementation-gap-open`; repository port/query boundary 只是第一步实现，不包含 freshness/barrier、legacy removal 或生产证据。
- Next prompt:
  - `read-models:bank-detail-refresh-freshness-operation-barrier`

## 验证结果

- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime -v` 通过，52 tests。
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api -v` 通过，36 tests。
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` 通过。

## 未测风险

- 未连接真实 PostgreSQL、Redis、RabbitMQ。
- 未执行生产 read-only SSH/HTTP SLO。
- 未证明 write -> dirty/outbox -> worker -> operation barrier fresh 的完整闭环；这是下一边界 `read-models:bank-detail-refresh-freshness-operation-barrier` 的目标。
- `server.py` 仍保留若干 bank_detail legacy helper，下一步必须继续移除或隔离，不能把本 slice 当成 legacy removal 完成。
