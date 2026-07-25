# Domain Events 与 Derived Lifecycle 模块边界与 I/O

日期：2026-07-25

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：derived lifecycle 只服务管理员设置重置与历史 ETC 修复两个显式维护入口；普通写、导入确认和周期 OA sync 都不借 lifecycle 做跨页 read-model fan-out。
- 当前缺口：无阻塞缺口；新增 event、domain 或 executor 时仍必须补 scope contract、执行器 wiring 和回归测试。
- 旧代码删除状态：`import_state_changed`、`import.fact.changed` worker bridge、普通 bank/category/settings callback、OA sync downstream fan-out、前端 `domainEvents.ts`、`useActiveFinanceDomainEvent.ts` 及业务 tag BroadcastChannel/window event 已删除。`DERIVED_DATA_EVENTS` 只保留 `etc_business_batch_changed`、`settings_reset_completed`。

## 职责边界

### 负责

- 两个显式维护事件、执行计划与它们声明的 read-model scopes。

### 不负责

- 不拥有源业务状态。
- 不直接写页面 read model payload。
- 不替代各模块 service 的业务校验。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| Historical ETC repair event | 管理维护入口 | 必须提供精确月份，`include_all=false` |
| Settings reset event | admin-only data reset | 必须显式标记 `include_all=true`，保留权限、审计与进度合同 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| Dirty scope/outbox | runtime queue | 经 gateway 或等价事务合同 |
| Derived job | runtime worker/background job | 可观察、可失败恢复 |
| `etc_business_batch_changed` event | historical ETC repair | 仅按修复得到的精确月份输出维护计划；普通 ETC import、submit/revoke 不调用。 |
| `settings_reset_completed` event | admin data reset | reset canonical/state 完成并 reload runtime 后执行显式全域维护；不是普通 settings Drawer 保存路径。 |
| Import/OA/category/rule facts | 各 canonical owner | 只推进 canonical/source/rule version；消费页面在访问时比较版本并 enqueue 自己的精确 scope，不经过本模块。 |

## 持久化与投影

- Own read model：无。
- 影响 read model：可能影响全部 manifest read models。
- Service owner：`DerivedDataLifecycleService`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Backend service | `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py` |
| Executors | `*_derived_lifecycle_executor.py` files |
| Runtime / app wiring | `runtime_queue.py`、`read_model_refresh_gateway.py`、`runtime_worker_registry.py`、`runtime_worker_handlers.py`、`app/server.py` 的 lifecycle executor wiring |
| Tests | `tests/test_derived_data_lifecycle_service.py`、`tests/test_*_derived_lifecycle_executor.py`、`web/src/test/PageRouteHost.test.tsx` |

## 依赖方向

- 允许依赖：module-specific derived lifecycle executors, runtime queue。
- 必须通过：`Application._execute_explicit_maintenance_lifecycle(...)` 的显式维护入口与 event/scope contract。
- 禁止绕过：service 里散落手写 downstream SQL refresh；persist callback 逐个调用 read model producer；一个 domain executor 隐式刷新其它 read model domain；恢复 frontend finance/tag refresh event；把 ETC 批次/OA 状态事件冒充发票事实变化。

## 测试与验证

- `tests/test_derived_data_lifecycle_service.py`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_workbench_dirty_queue_wiring.py`
- `web/src/test/PageRouteHost.test.tsx`（旧前端刷新模块/业务 BroadcastChannel 删除守卫）

## 当前缺口和删除条件

- 新增 lifecycle event 必须先证明无法由页面访问 freshness 收敛，列出权限、审计、影响 read models 和 scope fan-out，并在 app 执行边界提供 executor 与回归测试。
- 如果未来再出现 import/OA/category/rule 普通写 fan-out、`import.fact.changed` worker bridge、`after_mutation` callback 或 executor 隐式刷新其它页面，视为边界回归。
