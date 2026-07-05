# Domain Events 与 Derived Lifecycle 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 前端 domain event 只做同 session / cross-tab 刷新提示，不作为数据事实源。
- 后端 `DerivedDataLifecycleService` 是跨页面派生数据影响面的规划入口；真实 dirty scope、outbox、readiness 和 worker 完成状态仍由 runtime/read model 边界证明。
- 新增 backend lifecycle event 或 frontend finance event 时，必须先补 characterization/regression test，再改调用点。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-07-05 - Import-state lifecycle close 与隐藏 I/O 移除

- 目标：完成 Domain Events 与 Derived Lifecycle 边界 close，移除导入持久化后的旧手写 downstream fan-out，并让 invoice usage collection / OA pending payment 读模型刷新成为显式 lifecycle domain。
- 影响范围：`DerivedDataLifecycleService` 事件/域映射、`Application._execute_derived_data_lifecycle_event(...)` executor wiring、`_RuntimeWorkerDerivedLifecycle` runtime executor wiring、导入持久化回调、后端 lifecycle / runtime worker / workbench regression tests。
- 关键决策：新增 `import_state_changed` 作为导入 facts 保存后的唯一派生刷新事件；per-domain scope override 只表达不同 read model 的 scope 差异，不再由 persist callback 逐个调用 producer；Application 与 runtime worker 都显式保留 bank detail 的 `import_facts_changed` reason 合同；`workbench_read_model` executor 和 workbench scope invalidation helper 都不再隐式刷新 `input_invoice_usage`、`output_invoice_collection` 或 `oa_pending_payment`；`bank_flow_rule_batch_read_model` 在 runtime worker lifecycle 中补齐 executor，避免声明域被 skipped。
- 文档影响：`README.md`、`boundary-io.md`、`tests.md`、`state-machine.md`、`e2e-coverage.md` 已更新 close 状态、I/O 禁止项、测试矩阵和回归风险。
- 测试覆盖：`tests/test_derived_data_lifecycle_service.py` 覆盖 `import_state_changed` 与新增 invoice usage collection domains；`tests/test_runtime_worker_read_model_refresh_scopes.py` 覆盖 import-state 走 search producer、invoice usage collection dirty scopes、bank account balance producer、bank-flow runtime executor；`tests/test_workbench_dirty_queue_wiring.py` 覆盖 Application import-state lifecycle scope override、bank detail reason 合同和 relation metadata 只刷新指定 invoice usage scope type；`tests/test_platform_runtime_boundary_guards.py` 禁止 workbench scope invalidation 隐式调用 invoice usage collection 刷新；`tests/test_workbench_sql_runtime.py` 覆盖 import-state month/all、skip unaffected output collection、bank detail/balance scopes。
- 验证命令：`python3 -m py_compile backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py backend/src/fin_ops_platform/services/runtime_worker_handlers.py backend/src/fin_ops_platform/app/server.py tests/test_workbench_dirty_queue_wiring.py tests/test_platform_runtime_boundary_guards.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring.WorkbenchDirtyQueueWiringTests.test_import_state_persistence_uses_lifecycle_domain_scope_overrides -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_dirty_queue_wiring.WorkbenchDirtyQueueWiringTests.test_pair_relation_lifecycle_metadata_limits_downstream_refreshes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_scope_invalidation_does_not_refresh_invoice_usage_domains -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_bank_detail_for_transaction_month_scopes -v`。
- 未测风险：本轮不证明每个页面对每个 lifecycle event 的 Browser UI 状态；页面级 stale/fresh/loading/error 仍由各页面模块维护。
- 后续事项：新增 event 或新增 read model domain 时，必须同时补 app/runtime executor wiring、scope contract、后端 mapping tests 和对应页面模块回归。

## 2026-06-24 - Invoice lifecycle derived lifecycle executor boundary

- 目标：将 `invoice_lifecycle_read_model` derived lifecycle 执行逻辑从 `Application` helper 抽到显式 `InvoiceLifecycleDerivedLifecycleExecutor`。
- 影响范围：后端 derived lifecycle executor wiring、invoice lifecycle read model refresh enqueue callback、platform runtime boundary guard；不改变 `DerivedDataLifecycleService` event/domain plan 合同或前端 domain event 合同。
- 关键决策：`Application` 只负责把 `invoice_lifecycle_read_model` domain 映射到 executor，并注入 gateway-backed refresh callback；executor 保持 scope/reason/metadata/result shape，与 workbench relation explicit executor 模式一致。
- 文档影响：同步 read-models/domain-events 模块实施记录和测试矩阵；状态机定义不变。
- 测试覆盖：`tests/test_invoice_lifecycle_derived_lifecycle_executor.py` 覆盖 executor 合同；`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_invoice_lifecycle_derived_lifecycle_uses_explicit_executor_boundary` 防止 app-owned helper 回归；`tests/test_derived_data_lifecycle_service.py` 继续覆盖 domain plan/order。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-derived-lifecycle-executor-port-extraction.md`。
- 未测风险：本轮不证明每个页面在 invoice lifecycle event 后的 UI stale/fresh 行为；仍由页面/read-model freshness 和 worker readiness 证明。

## 2026-06-11 - 测试闭环矩阵、状态机与事件合同补强

- 目标：执行测试闭环 master goal 的 domain-events-lifecycle 模块轮次，审计后端 derived lifecycle、前端 finance domain event、页面订阅和跨页面刷新边界。
- 影响范围：`tests/test_derived_data_lifecycle_service.py`、`web/src/test/domainEvents.test.ts`、本模块 `tests.md`、`state-machine.md`、`implementation-notes.md`。
- 关键决策：本模块保护“事件规划和刷新提示合同”，不把前端事件当事实源；页面/API/read model/worker 的具体 stale/fresh/loading/error 行为由对应页面模块继续闭环。
- 文档影响：补齐影响面清单、后端 event 影响图、前端 event 影响图、七类测试适用性、历史 bug 回归库、关键 smoke flows、验证命令和未测风险。
- 测试覆盖：新增后端 characterization test，确保每个声明的 `DERIVED_DATA_EVENTS` 都能生成 JSON 可序列化且不删除 protected target 的 plan；新增前端 finance domain event contract guard，防止事件名改动破坏页面监听。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_runtime_worker_read_model_refresh_scopes -v`；`cd web && npm test -- --run src/test/domainEvents.test.ts src/test/useActiveFinanceDomainEvent.test.tsx`。
- 未测风险：本模块不证明每个页面对每个 event 的 UI 反馈完整，后续由各页面模块补前端交互和关键业务流 regression。
- 后续事项：下一模块继续处理 `reconciliation-workbench`。
