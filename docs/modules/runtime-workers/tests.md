# Runtime Worker 测试矩阵


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_read_model_refresh_gateway.py` | read model scope contract 属于刷新边界业务规则，覆盖合法/非法 scope。 |
| 2. Service-layer tests | 适用 | `tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` | 覆盖 `_RuntimeWorkerDerivedLifecycle` 通过统一 gateway 入队，以及旧 runtime scope contract 检查/清理。 |
| 3. API contract tests | 不适用 | N/A | 本阶段不改变 HTTP/API contract。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_runtime_worker_read_model_refresh_scopes.py` | 覆盖 worker lifecycle 不再投递非法成本统计 dirty/outbox scope。 |
| 5. Frontend component and interaction tests | 不适用 | N/A | 本阶段不改前端交互。 |
| 6. End-to-end business-flow integration tests | 按需适用 | `tests/test_runtime_worker_read_model_refresh_scopes.py` | 当前以 lifecycle 边界测试覆盖 ETC/导入等 worker 触发链路的核心入队行为。 |
| 7. Existing feature regression tests | 适用 | `tests/test_platform_runtime_boundary_guards.py` | 覆盖 worker 不依赖 Application/auth/HTTP 边界，非成本统计 scope 保持原样，并防止 app/service/tool/script producer 绕过 `ReadModelRefreshGateway` 直接调用 read model refresh queue。 |

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v
```

## 未测风险

- 未覆盖完整 import worker 处理真实文件到 read model worker 完成投影的端到端链路；当前通过 lifecycle/gateway/architecture guard 锁住入队合同。
