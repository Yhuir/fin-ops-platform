# Read Model Bank Detail And Bank Account Balance Contract

**日期:** 2026-06-23
**Boundary:** `read-models:bank-detail-and-bank-account-balance-contract`
**状态:** `closed-autonomous`
**范围:** 银行明细与账户余额 read model 合同守卫；不改 SQL、worker、route、API shape、前端行为、Go/Fiber、Go Worker 或生产状态。

## 执行结论

本轮审阅了 read-models 与 bank-details 模块文档、状态机、测试矩阵、Workbench 上一轮分析、`BankDetailsApplicationService`、`BankTransactionTagReadFacade`、`BankDetailReadModelRefreshService`、`BankAccountBalanceReadModelRefreshService`、银行明细/账户余额 projection 和 `PostgresReadModelRepository` 对应 port。

当前代码已具备以下有效边界：

- `bank_detail:all` 是 fan-out 控制 scope；`BankDetailReadModelRefreshService` 收到 `all` 时通过 projection builder 枚举月份 shard，再经 `ReadModelRefreshGateway.enqueue_many("bank_detail", ...)` 投递月份 refresh，并完成 `all` dirty scope，不把 `all` 作为页面可读 parent freshness proof。
- 银行明细页面无界查询通过 `bank_detail_scope_keys_for_range(...)` 解析为已有月份 shard；没有月份 shard 时才保留 `all` 作为 empty/missing 判断入口。
- `BankDetailsApplicationService` 在 bank detail scope summary fresh 后继续校验当前自动标签规则版本；不一致时返回 stale 并补投 refresh。
- `BankTransactionTagReadFacade` 只通过 bank detail repository port 读取 downstream 标签事实，非 fresh 时只补投 blocking scope，fresh payload 中 missing transaction id 不阻断 freshness。
- 账户余额有独立 projection、refresh event、scope summary、storage table 和 list/save repository port；刷新入口只接受 `bank_account_balance:all`。页面交易数量可以按筛选从 bank detail rows 统计，但余额金额、余额 freshness 和 balance read model status 不能从 bank detail rows 派生。
- 前端自动标签规则保存/重应用后等待 `operationBarrierTargets("bank_detail", scopeKeys)`，不把前端 domain event 当作 read model fresh 证明。

本轮不改运行时代码，只把该边界在 manifest/test 层加硬：

- `bank_detail` 与 `bank_account_balance` 必须保持独立 `scope_type`、event、repository port 和 test owner。
- 两者都保持 `partitioned_scoped_incremental` 目标策略、`self_managed_freshness` 查询合同、`fan_out_command` all-scope 语义和 `gateway_force_refresh` 强制刷新入口。
- `bank_account_balance` 的 manifest test owner 修正为 `tests/test_bank_account_balance_read_model.py`，避免账户余额合同只被 bank detail SQL runtime owner 隐含覆盖。

## 改动前影响分析

### 1. 模块范围

- 目标模块: `read-models`
- 关联页面模块: `bank-details`
- 子边界: `bank_detail`、`bank_account_balance`
- 本次改动类型: manifest owner refinement + contract guard
- 是否改变业务行为: 否
- 是否改变 API response shape: 否
- 是否改变 SQL 查询或写入: 否
- 是否改变 worker refresh: 否
- 是否进入 Go / Fiber / Go Worker candidate: 否

### 2. 合同矩阵

| Contract | `bank_detail` | `bank_account_balance` | 本轮守卫 |
| --- | --- | --- | --- |
| scope type | `bank_detail` | `bank_account_balance` | manifest test |
| refresh event | `bank_detail.read_model.refresh` | `bank_account_balance.read_model.refresh` | existing parity test |
| query owner | `BankDetailsApplicationService` | `BankDetailsApplicationService` | manifest test |
| permission owner | `bank_details_api_session` | `bank_details_api_session` | manifest test |
| projection strategy | `partitioned_scoped_incremental` | `partitioned_scoped_incremental` | manifest test |
| all scope | fan-out command, page reads month shards | fan-out command for controlled refresh, query status from balance summary | manifest test + existing runtime tests |
| repository ports | bank detail scope/list/tag/save/mark ports | balance summary/list/save ports | manifest test requires disjoint sets |
| test owner | bank detail SQL runtime tests | account balance read model tests | manifest test |

## Legacy 退役与污染防护

| Legacy / pollution risk | 当前状态 | 本轮处理 | 后续 |
| --- | --- | --- | --- |
| 把 `bank_detail:all` 当页面 freshness proof | 已由 repository/runtime tests 覆盖 | manifest 明确 all scope 为 fan-out command | 后续 legacy-read-path-removal slice 查旧 read path |
| 下游 non-fresh 依赖自动补投 `bank_detail:all` | 已有 runtime/gateway/facade tests | 本轮不改运行时代码 | 后续继续保留 targeted tests |
| 账户余额从 bank detail rows 聚合替代 | 状态机禁止；余额独立表/summary/list/save | manifest 使 balance port 与 bank detail port 不相交 | 后续若改账户列表 SQL，必须跑账户余额 read model tests |
| 自动标签规则版本 stale 伪 fresh | Application service 已校验 `bank_auto_tag_rules_version` | analysis 记录，不重复实现 | 后续改 rules/source version 时扩展业务测试 |
| 前端保存后只靠 domain event | 页面已有 operation barrier wait | analysis 记录，不改前端 | 后续 UI 变更必须保留 barrier |

## 七类测试映射

| 类别 | 是否适用 | 本轮覆盖 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 不改分类、候选、余额计算或状态流转业务规则 |
| 2. Service-layer tests | 适用 | manifest guard 锁定 query owner、permission owner、repository port owner |
| 3. API contract tests | 不适用 | 无 HTTP shape 或 status code 变化 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_bank_detail_and_balance_manifest_keep_separate_contracts` 锁定 scope/projection/all/force-refresh/port/test owner 合同 |
| 5. Frontend component and interaction tests | 不适用 | 无前端行为变化；既有 BankDetailsPage tests 继续保护 operation barrier 和 stale/refreshing UI |
| 6. End-to-end business-flow integration tests | 不适用 | 本轮不触发 import/worker/write 链路 |
| 7. Existing feature regression tests | 适用 | 既有 bank details SQL runtime、account balance read model 和 runtime worker tests 保持为后续必要验证集 |

## 环境与验证限制

- 本地 `PGSQL_URL`: 不可用。
- staging 数据库: 不可用。
- 是否需要真实 PostgreSQL: 否，本轮是 manifest/test guard。
- 是否需要真实 worker/outbox/readiness: 否。
- 是否会写生产数据: 否。
- 生产验证: 不适用。
- Secret handling: 未读取、未记录 secret。

## 状态机影响

- 全局 `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`: 本轮未新增、重命名或改变 workflow state/transition/guard，故不改全局状态机定义。
- `docs/modules/read-models/state-machine.md`: 不改变共享 read model 状态语义，既有 fresh/refreshing/stale/fan-out-only 禁止状态仍适用。
- `docs/modules/bank-details/state-machine.md`: 添加变更记录，说明本轮只是合同守卫加硬，不改变业务状态、UI 状态、read model 状态或 worker 状态。

## 后续边界

下一步推进 `read-models:pending-invoice-and-oa-pending-payment-contract`：

- 聚焦 pending invoice 与 OA pending payment 的 page-first-screen scope、bare-all 禁止语义、relation source versions 和 production fail-closed 合同。
- 继续优先 contract/guard/analysis，不做大规模 SQL 拆分、Go/Fiber 或 Go Worker 实现。
