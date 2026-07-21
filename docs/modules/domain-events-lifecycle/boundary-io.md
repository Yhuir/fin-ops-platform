# Domain Events 与 Derived Lifecycle 模块边界与 I/O

日期：2026-07-19

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：领域事件和 derived lifecycle 负责把业务写操作转成明确 downstream dirty scopes/jobs，不直接承载页面业务逻辑。
- 当前缺口：无阻塞缺口；新增 event、domain 或 executor 时仍必须补 scope contract、执行器 wiring 和回归测试。
- 旧代码删除状态：`import_state_changed` 已成为通用导入持久化后的唯一派生刷新事件；`Application` / runtime worker 中旧手写 import-state downstream fan-out 已移除，`workbench_read_model` executor 和 workbench scope invalidation helper 都不再隐藏刷新 invoice usage collection。无生产调用方的 `etc_oa_submitted` / `etc_oa_revoked` 事件、domain/job mapping 已删除。

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
| `import_state_changed` event | import persistence callbacks / runtime import worker | 导入 facts 保存后必须通过该 event fan out 到 workbench、relation、invoice lifecycle、pending invoice、invoice usage collection、bank detail/balance、bank-flow rule batches、cost 和 search；具体 scope 由 per-domain override 表达，禁止在 persist callback 手写逐个 downstream refresh；bank detail 输出必须保留 `import_facts_changed` reason 合同。 |
| invoice usage collection dirty scope | `input_invoice_usage` / `output_invoice_collection` / `oa_pending_payment` workers | 只能作为显式 derived lifecycle domain 输出；不得挂在 `workbench_read_model` executor 的隐藏副作用里。 |
| `bank_flow_rule_batch_changed` event | `bank-flow-rule-batches` / runtime workers | 只用于流水规则批量处理写入；必须 fan out 到 `bank_flow_rule_batch_read_model` 及 Workbench/relation/cost/search 下游，不能复用 `no_oa_bank_batch_changed` 表示 bank-flow 写入。 |
| `bank_transaction_category_changed` event | bank detail category mutation | legacy/non-UoW 分类路径按精确月份输出 `bank_flow_rule_batch_read_model`；现代 Turnover bank-row category UoW 必须在同一业务事务直接批量写等价 `bank_flow_rule_batch` dirty/outbox，不能等事务后补偿。 |
| `bank_auto_tag_rules_changed` event | bank details automatic tag rule writer | 除 bank detail/no-OA/workbench/cost/search 外必须输出 `bank_flow_rule_batch_read_model`；无可证明的精确月份时允许 `all` fan-out，不能遗漏未来批次资格重算。 |
| `etc_import_confirmed` event | ETC import worker / application service | 仅在 existing canonical invoice 元数据真实变化时按精确月份、`include_all=false` 输出 Workbench/relation/matching、invoice lifecycle、tax 和 search；不得直接投递 cost 或 historical repair。Cost 只能在对应 Workbench 月 generation 成功发布后由 `workbench_shard_published` 收敛；历史修复只能走显式运维事件。 |
| `etc_business_batch_status_changed` event | ETC manual submitted / draft revoke | 只按 business batch scope 与成员发票日期计算精确月份，输出 Workbench、matching 和 search；不得直投 relation、invoice lifecycle、tax、cost 或 historical repair。Cost 仅因 Workbench 成功发布而有序收敛一次。 |
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
| Runtime / app wiring | `runtime_queue.py`、`read_model_refresh_gateway.py`、`runtime_worker_registry.py`、`runtime_worker_handlers.py`、`app/server.py` 的 lifecycle executor wiring |
| Tests | `tests/test_derived_data_lifecycle_service.py`、`tests/test_*_derived_lifecycle_executor.py`、`web/src/test/domainEvents.test.ts` |

## 依赖方向

- 允许依赖：module-specific derived lifecycle executors, runtime queue。
- 必须通过：explicit event/scope contract。
- 禁止绕过：service 里散落手写 downstream SQL refresh；persist callback 逐个调用 read model producer；一个 domain executor 隐式刷新其它 read model domain；frontend event 直接改业务 state；把 ETC 批次/OA 状态事件冒充发票事实变化。

## 测试与验证

- `tests/test_derived_data_lifecycle_service.py`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_workbench_dirty_queue_wiring.py`
- `web/src/test/domainEvents.test.ts`

## 当前缺口和删除条件

- 新增 lifecycle event 必须列出影响 read models 和 scope fan-out，并在 app/runtime 两个执行边界都有 executor 或明确 skipped contract。
- 如果未来再出现手写 import-state fan-out、`workbench_read_model` executor 隐式刷新 invoice usage collection、或 runtime 缺失已声明 domain executor，视为边界回归。
