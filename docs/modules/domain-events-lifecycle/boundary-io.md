# Domain Events 与 Derived Lifecycle 模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：领域事件和 derived lifecycle 负责把业务写操作转成明确 downstream dirty scopes/jobs，不直接承载页面业务逻辑。
- 当前缺口：include_all/reset 类事件影响面大，新增事件必须有 scope contract 和测试。
- 旧代码删除条件：旧手写 fan-out 逻辑被 lifecycle/gateway 取代且测试覆盖。

## 职责边界

### 负责

- 领域事件类型、derived lifecycle 执行、跨 read model/worker dirty fan-out。
- 前端 domain event hook/API 的轻量提示和刷新协调。

### 不负责

- 不拥有源业务状态。
- 不直接写页面 read model payload。
- 不替代各模块 service 的业务校验。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Domain event | business service/write UoW | 事件必须包含足够 scope 信息 |
| include_all/reset event | settings/data reset/import | 必须显式标记大范围影响 |
| Frontend event state | `web/src/features/domainEvents.ts` | 只用于 UI 观察/刷新协调 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Dirty scope/outbox | runtime queue | 经 gateway 或等价事务合同 |
| Derived job | runtime worker/background job | 可观察、可失败恢复 |
| `bank_flow_rule_batch_changed` event | `bank-flow-rule-batches` / runtime workers | 只用于流水规则批量处理写入；必须 fan out 到 `bank_flow_rule_batch_read_model` 及 Workbench/relation/cost/search 下游，不能复用 `no_oa_bank_batch_changed` 表示 bank-flow 写入。 |
| Frontend refresh signal | pages | 不伪装 fresh |

## 持久化与投影

- Own read model：无。
- 影响 read model：可能影响全部 manifest read models。
- Service owner：`DerivedDataLifecycleService`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend | `web/src/features/domainEvents.ts`、`web/src/hooks/useActiveFinanceDomainEvent.ts` |
| Backend service | `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py` |
| Executors | `*_derived_lifecycle_executor.py` files |
| Runtime | `runtime_queue.py`、`read_model_refresh_gateway.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_derived_data_lifecycle_service.py`、`tests/test_*_derived_lifecycle_executor.py`、`web/src/test/domainEvents.test.ts` |

## 依赖方向

- 允许依赖：module-specific derived lifecycle executors, runtime queue。
- 必须通过：explicit event/scope contract。
- 禁止绕过：service 里散落手写 downstream SQL refresh；frontend event 直接改业务 state。

## 测试与验证

- `tests/test_derived_data_lifecycle_service.py`
- `web/src/test/domainEvents.test.ts`

## 当前缺口和删除条件

- 新增 lifecycle event 必须列出影响 read models 和 scope fan-out。
